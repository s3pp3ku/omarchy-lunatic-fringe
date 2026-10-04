#!/usr/bin/python
"""Screensaver selection and a reversible, one-line user idle-plugin adapter."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

PLUGIN_ID = 's3pp3ku.omavoid'


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


class Controller:
    def __init__(self, home=None):
        self.home = Path(home) if home else Path.home()
        self.config = self.home/'.config/omavoid/screensaver.json'
        self.state = self.home/'.local/state/omavoid/integration.json'
        self.plugins = self.home/'.config/omarchy/plugins'
        self.root = self.plugins/PLUGIN_ID
        self.shell_config = self.home/'.config/omarchy/shell.json'

    def mode(self):
        try:
            mode=json.loads(self.config.read_text()).get('mode')
            return mode if mode in ('stock','omavoid') else 'stock'
        except (OSError,ValueError,AttributeError):
            return 'stock'

    def appearance(self):
        defaults={'icon':'white','game':'teal'}
        try:
            data=json.loads((self.home/'.config/omavoid/appearance.json').read_text())
            for role in defaults:
                if data.get(role) in ('white','teal','theme'): defaults[role]=data[role]
        except (OSError,ValueError,AttributeError): pass
        return defaults

    def set_appearance(self,role,value):
        if role not in ('icon','game') or value not in ('white','teal','theme'):
            raise ValueError('Unknown appearance selection')
        data=self.appearance();data[role]=value
        atomic_json(self.home/'.config/omavoid/appearance.json',data)
        return self.status()

    def status(self):
        return dict(mode=self.mode(), integrated=self.state.exists(), appearance=self.appearance())

    def choose(self, mode):
        if mode not in ('stock','omavoid'): raise ValueError('Choose stock or omavoid')
        self.integrate()
        atomic_json(self.config, {'version':1,'mode':mode})
        return self.status()

    def routing_line(self, indent='    '):
        relative='.config/omarchy/plugins/'+PLUGIN_ID+'/scripts/control.py'
        command=('[[ $(omarchy-shell lock isLocked 2>/dev/null) == "true" ]] || '
                 '{ if [[ -f "$HOME/'+relative+'" ]]; then '
                 '/usr/bin/python "$HOME/'+relative+'" idle; '
                 'else omarchy-launch-screensaver; fi; }')
        return indent+'runProcess(screensaverProcess, "screensaver", '+json.dumps(command)+')'

    def active_clone(self):
        config=json.loads(self.shell_config.read_text())
        enabled={entry['id'] for entry in config.get('plugins',[]) if isinstance(entry,dict) and 'id' in entry}
        enabled-=set(config.get('disabledPlugins',[]))
        clones=[]
        for manifest in self.plugins.glob('*/manifest.json'):
            try: data=json.loads(manifest.read_text())
            except (OSError,ValueError): continue
            if data.get('id') in enabled and data.get('omarchy',{}).get('clonedFrom')=='omarchy.idle':
                clones.append(manifest.parent)
        if len(clones)>1: raise RuntimeError('Multiple idle clones enabled; choose one before installing Omarchy: Lunatic Fringe.')
        return clones[0] if clones else None

    def integrate(self):
        if not (self.root/'game/fringe.py').is_file():
            raise RuntimeError('Install this plugin first; see README.md.')
        if self.state.exists():
            state=json.loads(self.state.read_text())
            service=Path(state['service'])
            if state['routed_line'] in service.read_text().splitlines(): return
            raise RuntimeError('Idle adapter changed since installation. Run restore before reinstalling.')
        clone=self.active_clone()
        created=False
        if clone is None:
            result=subprocess.run(['omarchy','plugin','clone','omarchy.idle'],capture_output=True,text=True)
            clone=self.active_clone()
            if clone is None:
                raise RuntimeError('Unable to clone the idle service: '+(result.stderr or result.stdout).strip())
            created=True
        service=clone/'Service.qml'
        original=service.read_text()
        candidates=[line for line in original.splitlines() if 'runProcess(screensaverProcess, "screensaver",' in line]
        if len(candidates)!=1: raise RuntimeError('Unsupported idle service. No idle code changed.')
        old=candidates[0]
        match=re.fullmatch(r'(\s*)runProcess\(screensaverProcess, "screensaver", (".*")\)',old)
        if not match: raise RuntimeError('Unsupported screensaver launch syntax. No idle code changed.')
        command=json.loads(match[2])
        guard='[[ $(omarchy-shell lock isLocked 2>/dev/null) == "true" ]] || '
        legacy=str(self.home/'.local/bin/lunatic-cyber')+' idle'
        if command not in (guard+'omarchy-launch-screensaver',guard+legacy):
            raise RuntimeError('Existing custom screensaver command found; leave it intact and integrate manually.')
        routed=self.routing_line(match[1])
        backup=self.home/'.local/state/omavoid/backups'/('idle-'+str(time.time_ns())+'.qml')
        backup.parent.mkdir(parents=True,exist_ok=True)
        backup.write_text(original)
        atomic_json(self.state, dict(version=1,service=str(service),original_line=old,
                                    routed_line=routed,backup=str(backup),created_clone=created))
        try:
            service.write_text(original.replace(old,routed,1))
        except Exception:
            self.state.unlink(missing_ok=True)
            raise
        if not self.config.exists(): atomic_json(self.config,{'version':1,'mode':'stock'})

    def restore(self):
        atomic_json(self.config,{'version':1,'mode':'stock'})
        if not self.state.exists(): return self.status()
        state=json.loads(self.state.read_text())
        service=Path(state['service'])
        contents=service.read_text()
        if state['routed_line'] in contents.splitlines():
            service.write_text(contents.replace(state['routed_line'],state['original_line'],1))
        elif state['original_line'] not in contents.splitlines():
            raise RuntimeError('Idle adapter was edited; backup retained. Restore its launch line manually.')
        self.state.unlink()
        return self.status()

    def command(self, selected):
        if selected=='omavoid':
            return ['/bin/bash',str(self.root/'bin/omavoid')]
        return ['omarchy-launch-screensaver','force']

    def launch(self, selected):
        subprocess.Popen(self.command(selected),start_new_session=True,
                         stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return self.status()

    def idle(self):
        # Existing screen-lock ownership and timeout logic stay in Omarchy.
        disabled=subprocess.run(['omarchy-toggle-enabled','screensaver-off'],stdout=subprocess.DEVNULL).returncode==0
        if disabled: return
        result=subprocess.run(['omarchy-shell','lock','isLocked'],capture_output=True,text=True)
        if result.stdout.strip()=='true': return
        command=self.command(self.mode())
        if self.mode()=='stock': command=['omarchy-launch-screensaver']
        os.execvp(command[0],command)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['status','toggle','stock','omavoid','integrate','restore','idle','play','preview','appearance'])
    parser.add_argument('role',nargs='?',choices=['icon','game'])
    parser.add_argument('palette',nargs='?',choices=['white','teal','theme'])
    args=parser.parse_args()
    controller=Controller()
    try:
        if args.action=='idle':
            controller.idle();return
        if args.action in ('play','preview'):
            result=controller.launch('omavoid' if args.action=='play' else controller.mode())
        elif args.action=='status': result=controller.status()
        else:
            lock=controller.home/'.local/state/omavoid/selector.lock'
            lock.parent.mkdir(parents=True,exist_ok=True)
            with lock.open('a') as stream:
                fcntl.flock(stream,fcntl.LOCK_EX)
                if args.action=='appearance': result=controller.set_appearance(args.role,args.palette)
                elif args.action=='restore': result=controller.restore()
                elif args.action=='integrate': controller.integrate();result=controller.status()
                else:
                    selected=('stock' if controller.mode()=='omavoid' else 'omavoid') if args.action=='toggle' else args.action
                    result=controller.choose(selected)
        print(json.dumps(result))
    except (OSError,ValueError,RuntimeError,KeyError) as error:
        print(json.dumps(dict(mode=controller.mode(),error=str(error))))
        return 1

if __name__=='__main__': sys.exit(main())
