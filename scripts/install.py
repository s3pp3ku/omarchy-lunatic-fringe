#!/usr/bin/python
"""Install the local release; native git installation is also supported."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from control import Controller, PLUGIN_ID, atomic_json


def check_dependencies():
    import cairo
    import gi
    gi.require_version('Gtk','3.0')
    gi.require_version('Gst','1.0')
    from gi.repository import Gtk, Gst
    Gst.init(None)
    if not Gst.ElementFactory.find('playbin'):
        raise RuntimeError('Missing GStreamer playback plugins.')
    for command in ('omarchy','omarchy-shell','flock','bash'):
        if not shutil.which(command): raise RuntimeError('Missing dependency: '+command)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--select',choices=['stock','omavoid'])
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    check_dependencies()
    root=Path(__file__).resolve().parents[1]
    subprocess.run(['omarchy','plugin','validate',str(root)],check=True)
    if args.check:
        print('Dependencies and plugin manifest OK');return
    c=Controller()
    backups=c.home/'.local/state/omavoid/backups'
    backups.mkdir(parents=True,exist_ok=True)
    if c.shell_config.exists():
        shutil.copy2(c.shell_config,backups/('shell-'+str(time.time_ns())+'.json'))
    if root!=c.root.resolve():
        if (c.root/'.git').exists():
            raise RuntimeError('Installed plugin is git-managed; update it with omarchy plugin update '+PLUGIN_ID)
        shutil.copytree(root,c.root,dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc','dist'))
    launcher=c.home/'.local/bin/omavoid'
    launcher.parent.mkdir(parents=True,exist_ok=True)
    installed='#!/bin/bash\nexec /bin/bash "$HOME/.config/omarchy/plugins/'+PLUGIN_ID+'/bin/omavoid" "$@"\n'
    record=c.home/'.local/state/omavoid/launcher-backup.json'
    if not record.exists():
        previous={'kind':'absent'}
        if launcher.is_symlink(): previous={'kind':'symlink','target':os.readlink(launcher)}
        elif launcher.exists(): previous={'kind':'file','text':launcher.read_text(),'mode':launcher.stat().st_mode&0o777}
        atomic_json(record,dict(previous=previous,installed=installed))
    if launcher.is_symlink(): launcher.unlink()
    launcher.write_text(installed);launcher.chmod(0o755)
    c.integrate()
    if args.select: c.choose(args.select)
    subprocess.run(['omarchy-shell','shell','rescanPlugins'],check=True,stdout=subprocess.DEVNULL)
    # Registry discovery can be asynchronous immediately after copying files.
    for attempt in range(30):
        result=subprocess.run(['omarchy-shell','shell','enablePlugin',PLUGIN_ID,'{"section":"right"}'],capture_output=True,text=True)
        if result.returncode==0 and result.stdout.strip()=='ok': break
        time.sleep(.1)
    else: raise RuntimeError('Plugin copied but shell did not enable it: '+result.stdout+result.stderr)
    print('Omarchy: Lunatic Fringe installed. Selected screensaver: '+c.mode())
    print('Bar: left-click opens settings; right-click plays; middle-click previews.')

if __name__=='__main__':
    try: main()
    except Exception as error:
        print('Install: '+str(error),file=sys.stderr);sys.exit(1)
