#!/usr/bin/python
"""Build a release without personal state, git internals or generated cache files."""
import hashlib
import json
from pathlib import Path
import tarfile
import zipfile

root=Path(__file__).resolve().parents[1]
version=json.loads((root/'manifest.json').read_text())['version']
name='omarchy-lunatic-fringe-'+version
dist=root/'dist';dist.mkdir(exist_ok=True)
files=sorted(path for path in root.rglob('*') if path.is_file()
             and path.name != 'AGENT_HANDOFF.md'
             and not any(part in ('dist','.git','__pycache__') for part in path.relative_to(root).parts)
             and path.suffix!='.pyc')
if any(path.is_symlink() for path in files): raise SystemExit('Refusing symlinks in release')
with tarfile.open(dist/(name+'.tar.gz'),'w:gz') as archive:
    for path in files: archive.add(path,arcname=name+'/'+str(path.relative_to(root)),recursive=False)
with zipfile.ZipFile(dist/(name+'.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
    for path in files: archive.write(path,arcname=name+'/'+str(path.relative_to(root)))
archives=[dist/(name+suffix) for suffix in ('.tar.gz','.zip')]
(dist/'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n' for path in archives))
for path in archives: print(path)
