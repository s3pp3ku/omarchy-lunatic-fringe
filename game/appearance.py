"""Read Omarchy's current theme without modifying it; safe palette fallbacks."""
import json
import re
import tomllib
from pathlib import Path

TEAL=(.18,1.,.61)
VIOLET=(.57,.34,1.)
GOLD=(1.,.70,.22)


def rgb(value, fallback):
    if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value): return fallback
    return tuple(int(value[i:i+2],16)/255 for i in (1,3,5))


def preferences(home):
    defaults={'icon':'white','game':'teal'}
    try:
        data=json.loads((Path(home)/'.config/omavoid/appearance.json').read_text())
        for role in defaults:
            if data.get(role) in ('white','teal','theme'): defaults[role]=data[role]
    except (OSError,ValueError,AttributeError): pass
    return defaults


def palette(home):
    mode=preferences(home)['game']
    if mode=='white': return {'primary':(1.,1.,1.),'secondary':(.65,.75,.9),'gold':GOLD}
    values={'primary':TEAL,'secondary':VIOLET,'gold':GOLD}
    if mode!='theme': return values
    for relative in ('.local/state/omarchy/current/theme/colors.toml','.config/omarchy/current/theme/colors.toml'):
        try:
            with (Path(home)/relative).open('rb') as stream: colors=tomllib.load(stream)
            return {'primary':rgb(colors.get('accent'),TEAL),
                    'secondary':rgb(colors.get('cyan',colors.get('magenta')),VIOLET),
                    'gold':rgb(colors.get('yellow'),GOLD)}
        except (OSError,ValueError): continue
    return values
