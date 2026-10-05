"""Campaign progression and atomic, versioned local saves for Omarchy: Lunatic Fringe."""
import json
import os
from pathlib import Path

MISSIONS = [
    ('01 / LET THE AGENTS COOK', 'OMARCHY CONTROL: The Hater Fleet wants our agentic AI OS offline. Clear five Doomscroll drones from the mirror routes.', 'kills', 5, 400),
    ('02 / SHIP IT ANYWAY', 'PACMAN: Gatekeeper interceptors stole our signed agent packages. Recover four gold archives. We have a release to ship.', 'salvage', 4, 550),
    ('03 / TOUCH GRASS, SYNC MIRRORS', 'HYPRLAND: The fleet is flooding our mirrors with hot takes. Hold at each node for four seconds to restore the agent network.', 'relays', 3, 750),
    ('04 / THE COMMENT SECTION', 'SYSTEMD: Their flagship is broadcasting an endless flamewar. Defeat the Comment Section and break the blockade.', 'boss', 1, 1200),
    ('05 / MERGE TO MAIN', 'OMARCHY CONTROL: The blockade is broken. Bring the signed release home. The agents are ready; let Omarchy roll.', 'home', 1, 1000),
    ('06 / STILL SHIPPING', 'OMARCHY CONTROL: Agentic Omarchy is online. The Hater Fleet keeps posting; we keep shipping. Defend the mirrors from tougher waves.', 'endless', 0, 0),
]
FREE_CONTRACTS = [
    ('PACMAN / BUILD RECOVERY', 'Recover three signed agent builds from the Hater Fleet.', 'salvage', 3, 450),
    ('DOOMSCROLL / FEED CLEANUP', 'Clear eight Doomscroll drones from the mirror routes.', 'kills', 8, 600),
    ('HYPRLAND / MIRROR SYNC', 'Hold at the active mirror node for four seconds.', 'relays', 1, 700),
    ('SYSTEMD / BOSS HUNT', 'Hunt down the roaming flagship when it enters the sector.', 'boss', 1, 900),
    ('OMARCHY / SHIP IT', 'Clear another wave of Hater Fleet interceptors.', 'kills', 12, 850),
]
DIFFICULTIES = {
    'easy': dict(damage=.38, fire=1.65, hull=.8, speed=.78, grace=.85, shield=8., population=5),
    'normal': dict(damage=.65, fire=1.25, hull=1., speed=.9, grace=.55, shield=6., population=7),
    'hard': dict(damage=1., fire=1., hull=1.25, speed=1., grace=.3, shield=4., population=9),
}
UPGRADES = {
    'weapon': ('PACMAN ARSENAL', ('Single pulse', 'Twin pulse', 'Tri-spread', 'Plasma lance', 'Plasma overclock I', 'Plasma overclock II', 'Plasma overclock III'), (350, 800, 1500, 2400, 3600, 5200)),
    'hull': ('KERNEL HARDENING', ('100 hull', '135 hull', '170 hull', '205 hull', '230 hull', '255 hull', '280 hull'), (300, 650, 1100, 1900, 3100, 4800)),
    'drive': ('HYPRDRIVE', ('Standard', 'Boost I', 'Boost II', 'Boost III', 'Boost IV', 'Boost V', 'Boost VI'), (250, 550, 950, 1600, 2600, 4100)),
    'magnet': ('PACMAN CREDIT MAGNET', ('Offline', 'Mote Magnet I', 'Mote Magnet II', 'Mote Magnet III', 'Mote Magnet IV'), (300, 700, 1450, 2800)),
}

class Campaign:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.awaiting_briefing = False
        self.difficulty = 'easy'
        self.muted = False
        self.stage = 0
        self.progress = 0
        self.credits = 0
        self.levels = dict(weapon=0, hull=0, drive=0, magnet=0)
        self.relays = []
        self.free_contract = 0
        self.free_relay_target = 0
        self.error = ''
        if self.path and self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if data.get('version') != 1:
                    raise ValueError('unsupported save version')
                def integer(value, low, high):
                    if type(value) is not int or not low <= value <= high:
                        raise ValueError('invalid save value')
                    return value
                stage = integer(data['stage'], 0, len(MISSIONS)-1)
                progress = integer(data['progress'], 0, 1000000)
                credits = integer(data['credits'], 0, 100000000)
                saved_levels=data.get('levels',{})
                if not isinstance(saved_levels,dict):
                    raise ValueError('invalid upgrade levels')
                levels = {key: integer(saved_levels.get(key,0), 0, len(UPGRADES[key][2])) for key in UPGRADES}
                relays = data.get('relays', [])
                if not isinstance(relays, list) or any(type(i) is not int or i not in range(3) for i in relays):
                    raise ValueError('invalid relay state')
                difficulty=data.get('difficulty','easy')
                if difficulty not in DIFFICULTIES: raise ValueError('invalid difficulty')
                self.awaiting_briefing=data.get('awaiting_briefing',False) is True
                self.difficulty=difficulty
                self.muted=data.get('muted',False) is True
                self.stage, self.progress, self.credits = stage, progress, credits
                self.levels, self.relays = levels, list(set(relays))
                self.free_contract=integer(data.get('free_contract',0),0,len(FREE_CONTRACTS)-1)
                self.free_relay_target=integer(data.get('free_relay_target',0),0,2)
            except (OSError, ValueError, KeyError, TypeError):
                self.error = 'Save could not be read; this flight starts a new campaign.'

    @property
    def mission(self):
        return MISSIONS[self.stage]

    @property
    def contract(self):
        return FREE_CONTRACTS[self.free_contract]

    @property
    def max_hull(self):
        level=self.levels['hull']
        return 100 + 35*min(level,3) + 25*max(0,level-3)

    def save(self):
        if not self.path:
            return
        data = dict(version=1, awaiting_briefing=self.awaiting_briefing, difficulty=self.difficulty, muted=self.muted, stage=self.stage, progress=self.progress,
                    credits=self.credits, levels=self.levels, relays=self.relays,
                    free_contract=self.free_contract, free_relay_target=self.free_relay_target)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(data, indent=2)+'\n')
            os.replace(tmp, self.path)
            self.error = ''
        except OSError:
            self.error = 'Save unavailable. Progress is kept for this flight only.'

    def event(self, kind, amount=1):
        if self.awaiting_briefing:
            return False
        if self.stage == len(MISSIONS)-1:
            _,_,contract_kind,goal,reward=self.contract
            if kind != contract_kind:
                return False
            self.progress += amount
            if self.progress < goal:
                return False
            self.credits += reward
            self.progress=0
            self.free_contract=(self.free_contract+1)%len(FREE_CONTRACTS)
            return True
        if self.mission[2] != kind:
            return False
        self.progress += amount
        if self.progress < self.mission[3]:
            return False
        self.credits += self.mission[4]
        self.stage += 1
        self.awaiting_briefing = True
        self.progress = 0
        return True

    def buy(self, category):
        if category not in UPGRADES:
            return 'Unknown upgrade.'
        name, tiers, costs = UPGRADES[category]
        level = self.levels[category]
        if level >= len(costs):
            return name+' is fully upgraded.'
        if self.credits < costs[level]:
            return f'Need {costs[level]-self.credits} more credits.'
        self.credits -= costs[level]
        self.levels[category] += 1
        return 'Installed: '+tiers[level+1]
