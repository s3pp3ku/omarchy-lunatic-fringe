#!/usr/bin/python
"""Restore only our adapter line and launcher; retain saves and user settings."""
import json
from pathlib import Path
import shutil
import subprocess
from control import Controller, PLUGIN_ID

c=Controller()
c.restore()
subprocess.run(['omarchy-shell','shell','disablePlugin',PLUGIN_ID],check=True)
record=c.home/'.local/state/omavoid/launcher-backup.json'
launcher=c.home/'.local/bin/omavoid'
if record.exists():
    data=json.loads(record.read_text())
    if launcher.is_file() and not launcher.is_symlink() and launcher.read_text()==data['installed']:
        launcher.unlink()
        old=data['previous']
        if old['kind']=='symlink': launcher.symlink_to(old['target'])
        elif old['kind']=='file': launcher.write_text(old['text']);launcher.chmod(old['mode'])
        record.unlink()
# Remove only the canonical plugin folder after adapter restoration succeeded.
if c.root.name!=PLUGIN_ID or c.root.parent!=c.plugins: raise RuntimeError('Unexpected plugin path')
if c.root.exists(): shutil.rmtree(c.root)
print('Omarchy: Lunatic Fringe plugin removed. Campaign saves, controls and backups retained.')
