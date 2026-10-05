#!/usr/bin/python
"""Omarchy: Lunatic Fringe: original procedural art and a roaming space combat simulation."""
import argparse
import math
import random
import time
from pathlib import Path
import cairo
import json
import signal
import textwrap
from appearance import palette
from campaign import Campaign, UPGRADES, BUILD_STATS, DIFFICULTIES, MISSIONS, FREE_PATROL_STAGE

TAU = math.tau
CYAN = (0.18, 1.0, 0.61)
PINK = (1.0, 0.16, 0.19)
GOLD = (1.0, 0.70, 0.22)
PURPLE = (0.57, 0.34, 1.0)
WORLD = 5200
PALETTE = {}

def wrap(v):
    return (v + WORLD / 2) % WORLD - WORLD / 2

def delta(a, b):
    return wrap(a - b)

def color(c, rgb, alpha=1):
    c.set_source_rgba(*PALETTE.get(tuple(rgb),rgb), alpha)

def line(c, points, rgb, width=1, alpha=1, close=False):
    c.new_path()
    c.move_to(*points[0])
    for p in points[1:]:
        c.line_to(*p)
    if close:
        c.close_path()
    color(c, rgb, alpha)
    c.set_line_width(width)
    c.stroke()

def circle(c, x, y, radius, rgb, alpha=1, width=1):
    c.new_path()
    c.arc(x, y, radius, 0, TAU)
    color(c, rgb, alpha)
    c.set_line_width(width)
    c.stroke()

def text(c, x, y, label, size=12, rgb=CYAN, alpha=1):
    c.select_font_face('monospace', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    c.set_font_size(size)
    color(c, rgb, alpha)
    c.move_to(x, y)
    c.show_text(label)

def segment_hit(x0,y0,x1,y1,cx,cy,radius):
    """Earliest contact along a short wrapped-world projectile segment."""
    dx,dy=delta(x1,x0),delta(y1,y0)
    fx,fy=delta(x0,cx),delta(y0,cy)
    a=dx*dx+dy*dy
    c=fx*fx+fy*fy-radius*radius
    if c<=0: return 0.
    if a<1e-12: return None
    b=2*(fx*dx+fy*dy)
    disc=b*b-4*a*c
    if disc<0: return None
    t=(-b-math.sqrt(disc))/(2*a)
    return t if 0<=t<=1 else None

def load_fire_keys(path):
    try:
        keys=json.loads(Path(path).read_text()).get('fire')
        if not isinstance(keys,list) or not keys or not all(isinstance(k,str) and k and len(k)<40 for k in keys):
            raise ValueError('invalid fire keys')
        return set(keys)
    except (OSError,ValueError,TypeError,AttributeError):
        return {'Control_L'}

class SpriteAtlas:
    """Render regions of the original RGB sheet, without modifying the asset.

    Runtime color-keying suppresses the RGB sheet's dark matte and preserves glows.
    Region coordinates deliberately exclude captions and neighboring sprites.
    """
    regions = {
        'player': (326, 451, 68, 69),
        'red': (25, 660, 72, 67),
        'interceptor': (185, 660, 70, 67),
        'violet': (337, 667, 69, 62),
        'relay': (490, 649, 106, 95),
        'rock0': (26, 757, 86, 73),
        'rock1': (126, 765, 73, 66),
        'rock2': (216, 757, 88, 77),
        'rock3': (319, 769, 61, 61),
        'shot-green': (25, 875, 33, 26),
        'shot-red': (77, 875, 37, 26),
        'burst': (259, 855, 68, 64),
        'spark': (337, 851, 71, 73),
    }

    def __init__(self):
        sheet = cairo.ImageSurface.create_from_png(str(Path(__file__).parent / 'assets' / 'arcade-sheet.png'))
        self.sprites = {}
        for name, (sx, sy, sw, sh) in self.regions.items():
            sprite = cairo.ImageSurface(cairo.FORMAT_ARGB32, sw, sh)
            ctx = cairo.Context(sprite)
            ctx.set_source_surface(sheet, -sx, -sy)
            ctx.paint()
            sprite.flush()
            data = sprite.get_data()
            stride = sprite.get_stride()
            # The supplied sheet is RGB, not a transparent sprite atlas. Apply
            # a soft dark color key in memory, keeping the source PNG intact.
            import sys
            for y in range(sh):
                for x in range(sw):
                    offset = y * stride + x * 4
                    pixel = int.from_bytes(data[offset:offset+4], sys.byteorder)
                    r, g, b = (pixel >> 16) & 255, (pixel >> 8) & 255, pixel & 255
                    alpha = max(0, min(255, int((max(r,g,b)-12)*255/16)))
                    value = (alpha<<24) | ((r*alpha//255)<<16) | ((g*alpha//255)<<8) | (b*alpha//255)
                    data[offset:offset+4] = value.to_bytes(4, sys.byteorder)
            sprite.mark_dirty()
            self.sprites[name] = sprite

    def draw(self, c, name, x, y, size, angle=0, alpha=1):
        sprite = self.sprites[name]
        sw, sh = sprite.get_width(), sprite.get_height()
        c.save()
        c.translate(x, y)
        c.rotate(angle)
        scale = size / max(sw, sh)
        c.scale(scale, scale)
        c.set_source_surface(sprite, -sw / 2, -sh / 2)
        c.get_source().set_filter(cairo.FILTER_BILINEAR)
        if name in ('shot-green','spark'):
            color(c,CYAN,alpha)
            c.mask_surface(sprite,-sw/2,-sh/2)
        else:
            c.paint_with_alpha(alpha)
        c.restore()

class Simulation:
    def __init__(self, seed=None, save_path=None):
        self.atlas = SpriteAtlas()
        self.save_path = save_path
        self.sound = None
        self.sound_on_auto = False
        self.briefing = False
        self.replay_confirm = False
        self.fire_keys = {'Control_L'}
        self.palette_clock=0.
        self.palette_values=palette(Path.home())
        self.intro_elapsed = 0.
        self.intro_fade = 0.
        self.hit_grace = 0.
        self.hit_flash = 0.
        self.contact_grace = 0.
        self.was_docked = False
        self.rock_hp = {}
        self.destroyed_rocks = set()
        self.campaign = Campaign()  # Attract mode never changes the pilot's save.
        self.pilot_started = False
        self.shop = False
        self.navigate_home = False
        self.notice = ''
        self.notice_until = 0.
        self.save_clock = 0.
        self.salvage = []
        self.pickups = []
        self.weapon_mode = 'pulse'
        self.weapon_buffs = {'rapid':0.,'spread':0.,'flame':0.,'pierce':0.}
        self.shield_charge = 0.
        self.beacons = [(-1250., -650.), (1350., -450.), (450., 1500.)]
        self.scan = 0.
        self.scan_target = None
        self.respawn_shield = 3.
        self.boss_spawned = False
        self.free_boss_due = None
        self.free_boss_count = 0
        self.free_boss_names = ('AUR GATEKEEPER', 'DOOMSCROLL LEVIATHAN', 'BUILD PIPELINE BREAKER', 'COMMENT SECTION MK II', 'THE KERNEL PANIC')
        self.explosions = []
        self.rng = random.Random(seed)
        r = self.rng
        self.t = 0
        self.player = dict(x=0., y=-260., vx=65., vy=0., a=-0.4, hp=100., fuel=100., shot=0.)
        self.camera = [self.player['x'], self.player['y']]
        self.camera_velocity = [0., 0.]
        self.trail = []
        self.trail_clock = 0.
        self.auto = True
        self.returning = False
        self.keys = set()
        self.score = 0
        self.kills = 0
        self.bullets = []
        self.particles = []
        self.enemies = []
        self.stars = [(r.random(), r.random(), r.uniform(.12, 1), r.choice([(0.65, .78, 1.0), PURPLE, (0.85, .9, 1.0)])) for _ in range(700)]
        self.rocks = [(r.uniform(-2600,2600), r.uniform(-2600,2600), r.uniform(18,65), [r.uniform(.65,1.2) for _ in range(9)]) for _ in range(65)]
        self.planets = [(-850, -620, 145, PURPLE), (1300, 900, 220, CYAN), (-1650,1450,105,PINK)]
        self.rocks = [rock for rock in self.rocks if math.hypot(rock[0],rock[1])>240
                      and all(math.hypot(delta(rock[0],x),delta(rock[1],y))>180 for x,y in self.beacons)]
        for _ in range(self.settings['population']):
            self.spawn()

    @property
    def settings(self):
        return DIFFICULTIES[self.campaign.difficulty]

    def sound_event(self,name):
        if self.sound and self.pilot_started and not self.auto:
            self.sound.play(name)

    def cycle_difficulty(self):
        self.take_control()
        old=self.settings['hull']
        names=list(DIFFICULTIES)
        self.campaign.difficulty=names[(names.index(self.campaign.difficulty)+1)%3]
        ratio=self.settings['hull']/old
        for enemy in self.enemies:
            enemy['hp']*=ratio
            enemy['maxhp']*=ratio
        self.hit_grace=0.
        desired=self.settings['population']+min(3,self.campaign.stage)
        ordinary=[e for e in self.enemies if not e['boss']]
        while len(ordinary)>desired:
            enemy=ordinary.pop();self.enemies.remove(enemy)
        for _ in range(max(0,desired-len(ordinary))): self.spawn()
        self.notify('Difficulty: '+self.campaign.difficulty.upper())
        self.persist()

    def toggle_mute(self):
        self.take_control()
        self.campaign.muted=not self.campaign.muted
        if self.sound:
            self.sound.muted=self.campaign.muted
            if self.sound.muted: self.sound.hush()
            elif self.pilot_started and (not self.auto or self.sound_on_auto): self.sound.start_music()
        self.notify('Sound and music muted' if self.campaign.muted else 'Sound and music on')
        self.persist()

    def damage_player(self,amount):
        p=self.player
        if self.respawn_shield>0 or self.hit_grace>0 or math.hypot(p['x'],p['y'])<145:
            return False
        amount*=self.settings['damage']
        amount*=1-.055*self.campaign.stats['armor']
        if self.shield_charge>0:
            absorbed=min(self.shield_charge,amount)
            self.shield_charge-=absorbed
            amount-=absorbed
        if amount<=0:
            self.hit_grace=max(self.hit_grace,.08)
            self.sound_event('shield')
            return True
        p['hp']-=amount
        self.hit_grace=self.settings['grace']
        self.hit_flash=.24
        self.sound_event('hit')
        self.burst(p['x'],p['y'],PINK,8)
        return True

    def resolve_contacts(self):
        p=self.player
        obstacles=[(rock[0],rock[1],rock[2]*.82,None) for i,rock in enumerate(self.rocks) if i not in self.destroyed_rocks]
        obstacles += [(e['x'],e['y'],e['radius'],e) for e in self.enemies if e['hp']>0]
        for x,y,r,enemy in obstacles:
            dx,dy=delta(p['x'],x),delta(p['y'],y)
            distance=math.hypot(dx,dy)
            limit=r+21
            if distance>=limit: continue
            nx,ny=(dx/distance,dy/distance) if distance>.001 else (math.cos(p['a']),math.sin(p['a']))
            p['x']=wrap(x+nx*(limit+1));p['y']=wrap(y+ny*(limit+1))
            approach=p['vx']*nx+p['vy']*ny
            if approach<0:
                p['vx']-=1.45*approach*nx;p['vy']-=1.45*approach*ny
            if enemy:
                enemy['a']=math.atan2(-ny,-nx)
            if self.contact_grace<=0:
                self.damage_player(min(18,5+max(0,-approach)*.025))
                if enemy: enemy['hp']-=1
                self.sound_event('metal_crash' if enemy else 'rock_crash')
                self.burst(p['x']-nx*20,p['y']-ny*20,GOLD,10)
                self.contact_grace=.65

    def spawn(self, boss=False):
        r, p = self.rng, self.player
        a, d = r.random()*TAU, r.uniform(700,1300)
        endgame=self.campaign.free_roam
        tier = min(12, self.campaign.stage + (self.kills//14 if endgame else 0))
        kind = 2 if boss else r.randrange(min(3, 1+self.campaign.stage))
        hp = ((160+min(12,self.kills//14)*24) if boss and endgame else 135 if boss else 3+tier*2+(3 if kind==2 else 0))*self.settings['hull']
        self.enemies.append(dict(x=wrap(p['x']+math.cos(a)*d), y=wrap(p['y']+math.sin(a)*d),
                                 a=a, hp=hp, maxhp=hp, shot=r.uniform(.3,3), kind=kind,
                                 boss_name=(self.free_boss_names[self.free_boss_count%len(self.free_boss_names)] if boss and endgame else 'COMMENT SECTION'),
                                 boss=boss, tier=tier, radius=(78 if endgame else 65) if boss else 25))

    def notify(self, message):
        self.notice, self.notice_until = message, self.t+6

    def persist(self):
        if self.pilot_started:
            self.campaign.save()

    def take_control(self):
        if not self.pilot_started:
            self.campaign = Campaign(self.save_path)
            self.pilot_started = True
            self.enemies.clear()
            self.bullets.clear()
            self.salvage.clear()
            self.pickups.clear()
            self.weapon_buffs={key:0. for key in self.weapon_buffs}
            self.shield_charge=0.
            self.trail.clear()
            self.kills = 0
            self.score = 0
            self.scan = 0.
            self.boss_spawned = False
            self.free_boss_due=self.t+self.rng.uniform(35,55) if self.campaign.free_roam else None
            self.returning = False
            self.player.update(x=0., y=-90., vx=0., vy=0., hp=self.campaign.max_hull, fuel=100.)
            self.camera = [0., -90.]
            self.respawn_shield = self.settings['shield']
            self.shield_charge=3.+self.campaign.stats['shielding']*2
            self.intro_fade = .5
            self.was_docked = True
            if self.sound: self.sound.muted=self.campaign.muted
            for _ in range(self.settings['population']+min(3,self.campaign.stage)):
                self.spawn()
            self.briefing=self.campaign.awaiting_briefing or self.campaign.free_roam
            if self.campaign.error: self.notify(self.campaign.error)
        self.auto = False
        if self.sound and not self.sound.muted:
            self.sound.start_music()

    def change_music_volume(self, delta):
        self.take_control()
        if self.sound:
            value=self.sound.adjust_music(delta)
            self.notify(f'Music volume: {round(value*100)}%')

    def objective_event(self, kind):
        free=self.campaign.free_roam
        completed=self.campaign.contract[0] if free else self.campaign.mission[0]
        reward=self.campaign.contract[4] if free else self.campaign.mission[4]
        if self.campaign.event(kind):
            self.notify(('CONTRACT COMPLETE  +'+str(reward)+' CR  //  ' if free else 'Complete: ')+completed)
            self.sound_event('mission')
            if not free:
                self.salvage.clear()  # Old chapter drops cannot complete a new mission.
            self.scan=0.
            self.scan_target=None
            self.navigate_home=False
            if self.pilot_started and not free:
                self.briefing=True
                self.keys.clear()
            elif not self.pilot_started:
                self.campaign.awaiting_briefing=False
            self.persist()

    def launch_chapter(self):
        if self.replay_confirm:
            self.replay_story()
            return
        self.campaign.awaiting_briefing=False
        self.briefing=False
        self.keys.clear()
        self.bullets.clear()
        self.respawn_shield=max(self.respawn_shield,3.)
        if self.campaign.free_roam and self.free_boss_due is None:
            self.boss_spawned=False
            self.free_boss_due=self.t+self.rng.uniform(30,45)
        self.persist()

    def replay_story(self):
        # Explicitly requested from the briefing; equipment and credits survive.
        self.campaign.stage=0
        self.campaign.progress=0
        self.campaign.relays=[]
        self.campaign.awaiting_briefing=False
        self.replay_confirm=False
        self.briefing=False
        self.shop=False
        self.enemies.clear();self.bullets.clear();self.salvage.clear();self.pickups.clear();self.trail.clear()
        self.kills=0;self.scan=0.;self.scan_target=None;self.boss_spawned=False
        self.navigate_home=False;self.returning=False;self.keys.clear()
        self.player.update(x=0.,y=-90.,vx=0.,vy=0.,hp=self.campaign.max_hull,fuel=100.)
        self.camera=[0.,-90.];self.respawn_shield=self.settings['shield']
        self.shield_charge=3.+self.campaign.stats['shielding']*2
        for _ in range(self.settings['population']): self.spawn()
        self.notify('Mission 1 / Let the Agents Cook')
        self.persist()

    def waypoint(self):
        if self.navigate_home:
            return 0.,0.,'HOME / WORKSHOP'
        if self.campaign.free_roam and self.campaign.contract[2]=='relays':
            i=self.campaign.free_relay_target;xy=self.beacons[i]
            return xy[0],xy[1],f'MIRROR {i+1}'
        kind = self.campaign.mission[2]
        if kind == 'relays':
            choices = [(i,xy) for i,xy in enumerate(self.beacons) if i not in self.campaign.relays]
            if choices:
                i,xy = min(choices, key=lambda item: math.hypot(delta(item[1][0],self.player['x']),delta(item[1][1],self.player['y'])))
                return xy[0],xy[1],f'MIRROR {i+1}'
        if kind == 'salvage' and self.salvage:
            core = min(self.salvage,key=lambda q:math.hypot(delta(q[0],self.player['x']),delta(q[1],self.player['y'])))
            return core[0],core[1],'SIGNED PACKAGE'
        if kind == 'salvage' and self.enemies:
            enemy=min(self.enemies,key=lambda e:math.hypot(delta(e['x'],self.player['x']),delta(e['y'],self.player['y'])))
            return enemy['x'],enemy['y'],'PACKAGE CARRIER'
        if self.campaign.free_roam and any(e['boss'] for e in self.enemies):
            boss=next(e for e in self.enemies if e['boss'])
            return boss['x'],boss['y'],boss['boss_name']
        if kind == 'boss':
            boss = next((e for e in self.enemies if e['boss']),None)
            if boss:
                return boss['x'],boss['y'],'COMMENT SECTION'
        return 0.,0.,'HOME / WORKSHOP'

    def toggle_shop(self):
        self.take_control()
        if self.shop:
            self.shop = False
        elif math.hypot(self.player['x'],self.player['y']) < 145:
            self.shop = True
            self.keys.clear()
        else:
            self.notify('Press H for the HOME waypoint. U opens the workshop within 145m of the relay.')

    def purchase(self, key):
        if not self.shop:
            return
        category = {'1':'weapon','2':'hull','3':'drive','4':'magnet'}.get(key)
        if category:
            old_max = self.campaign.max_hull
            result=self.campaign.buy(category)
            self.notify(result)
            if result.startswith('Installed:'): self.sound_event('upgrade')
            self.player['hp'] += self.campaign.max_hull-old_max
            self.persist()

    def buy_build_stat(self,key):
        if not self.shop: return
        category={'5':'firepower','6':'volley','7':'armor','8':'engine','9':'shielding','0':'scavenger'}.get(key)
        if category:
            result=self.campaign.buy_stat(category)
            self.notify(result)
            if result.startswith('Build tuned:'): self.sound_event('upgrade')
            self.persist()

    def reset_build(self):
        self.notify(self.campaign.reset_build())
        self.persist()

    def cycle_weapon(self):
        self.take_control()
        weapons=('pulse','cannon','flame','scatter','laser')
        self.weapon_mode=weapons[(weapons.index(self.weapon_mode)+1)%len(weapons)]
        self.notify('Weapon // '+self.weapon_mode.upper())

    def burst(self, x, y, rgb, n=25):
        if n >= 25:
            self.explosions.append([x, y, .7, rgb == CYAN])
        for _ in range(n):
            a = self.rng.random()*TAU
            s = self.rng.uniform(30,240)
            self.particles.append([x,y,math.cos(a)*s,math.sin(a)*s,self.rng.uniform(.3,1.2),rgb])

    def drop_loot(self,x,y,boss=False):
        scavenger=self.campaign.stats['scavenger']
        types=('rapid','spread','flame','pierce','health','shield')
        if boss:
            drops=['health','shield',self.rng.choice(types[:4])]
            if self.rng.random()<.55: drops.append(self.rng.choice(types[:4]))
        elif self.rng.random()<min(.82,.34+scavenger*.055):
            drops=[self.rng.choices(types,weights=(2,2,1.3,1.4,1.1,1.1),k=1)[0]]
            if scavenger>=4 and self.rng.random()<.28: drops.append(self.rng.choice(types))
        else:
            drops=[]
        for kind in drops:
            angle=self.rng.random()*TAU;distance=self.rng.uniform(12,50)
            self.pickups.append({'x':wrap(x+math.cos(angle)*distance),'y':wrap(y+math.sin(angle)*distance),
                                 'kind':kind,'life':24.,'phase':self.rng.random()*TAU})

    def update_pickups(self,dt):
        p=self.player;scavenger=self.campaign.stats['scavenger']
        attraction=100+scavenger*75
        labels={'rapid':'RAPID FIRE','spread':'WIDE VOLLEY','flame':'FLAME ROUND','pierce':'PIERCING LASER',
                'health':'HULL RESTORED','shield':'SHIELD CHARGED'}
        for orb in self.pickups[:]:
            orb['life']-=dt;orb['phase']+=dt*3
            dx,dy=delta(p['x'],orb['x']),delta(p['y'],orb['y'])
            distance=math.hypot(dx,dy)
            if distance<attraction and distance>1:
                step=min(distance-48,(320+max(0,attraction-distance)*1.8)*dt)
                orb['x']=wrap(orb['x']+dx/distance*step);orb['y']=wrap(orb['y']+dy/distance*step)
                distance=math.hypot(delta(p['x'],orb['x']),delta(p['y'],orb['y']))
            if distance<52:
                kind=orb['kind'];self.pickups.remove(orb)
                self.sound_event('health' if kind=='health' else 'shield' if kind=='shield' else 'buff')
                if kind=='health':
                    self.player['hp']=min(self.campaign.max_hull,self.player['hp']+self.campaign.max_hull*.42)
                    if self.player['hp']>=self.campaign.max_hull*.98: self.shield_charge=min(8+self.campaign.stats['shielding']*5,self.shield_charge+5)
                elif kind=='shield':
                    self.shield_charge=min(8+self.campaign.stats['shielding']*5,self.shield_charge+10+self.campaign.stats['shielding']*2)
                else:
                    self.weapon_buffs[kind]=min(40.,self.weapon_buffs[kind]+14+self.campaign.stats['scavenger']*1.5)
                self.notify('PICKUP // '+labels[kind])
            elif orb['life']<=0:
                self.pickups.remove(orb)
        self.pickups=self.pickups[-48:]

    def press_control(self, key):
        key = key.lower() if len(key) == 1 else key
        if key not in {'Up', 'Down', 'Left', 'Right', 'w', 'a', 's', 'd'} | self.fire_keys:
            return False
        self.take_control()
        if not self.shop and not self.briefing:
            self.keys.add(key)
        return True

    def fire(self, ship, enemy=False):
        tier=0 if enemy else self.campaign.levels['weapon']
        if enemy:
            mode='enemy'
            angles=[-.28,-.14,0,.14,.28] if ship.get('boss') else ([-.13,0,.13] if ship.get('kind')==2 else [0])
            speed=510*self.settings['speed'];damage=12 if ship.get('boss') else 6+ship.get('tier',0)
            life=1.8;pierce=0
        else:
            mode='flame' if self.weapon_buffs['flame']>0 else self.weapon_mode
            volley=self.campaign.stats['volley']+int(self.weapon_buffs['spread']>0)*2
            power=self.campaign.stats['firepower']*.55
            if mode=='pulse':
                count=min(9,(1 if tier==0 else 2 if tier==1 else 3)+volley)
                angles=[(i-(count-1)/2)*.095 for i in range(count)]
                speed=1050 if tier>=3 else 880;damage=(3+max(0,tier-3) if tier>=3 else 1)+power;life=1.8;pierce=0
            elif mode=='cannon':
                angles=[0.];speed=680;damage=5+power;life=2.2;pierce=2
            elif mode=='flame':
                count=min(9,5+volley)
                angles=[(i-(count-1)/2)*.17 for i in range(count)]
                speed=440;damage=1.2+power*.35;life=.55;pierce=5
            elif mode=='scatter':
                count=min(11,7+volley)
                angles=[(i-(count-1)/2)*.115 for i in range(count)]
                speed=760;damage=1.4+power*.4;life=1.35;pierce=0
            else:  # Fast piercing laser beam.
                angles=[0.];speed=1450;damage=3.2+power;life=1.7;pierce=3
            if self.weapon_buffs['pierce']>0: pierce+=2
            self.sound_event({'pulse':'laser','cannon':'cannon','flame':'flame','scatter':'scatter','laser':'plasma'}[mode])
        for index,offset in enumerate(angles):
            a=ship['a']+offset
            side=(-8 if index%2==0 else 8) if mode=='pulse' and tier==1 else 0
            self.bullets.append([ship['x']+math.cos(a)*28-math.sin(a)*side,
                                 ship['y']+math.sin(a)*28+math.cos(a)*side,
                                 math.cos(a)*speed+ship.get('vx',0)*.35,
                                 math.sin(a)*speed+ship.get('vy',0)*.35,
                                 life,enemy,damage,mode,pierce,set()])

    def step(self, dt):
        self.palette_clock+=dt
        if self.palette_clock>=1:
            self.palette_clock=0.
            self.palette_values=palette(Path.home())
        self.intro_elapsed += dt
        self.intro_fade = max(0.,self.intro_fade-dt)
        if self.shop or self.briefing or self.campaign.awaiting_briefing:
            return
        self.hit_grace=max(0.,self.hit_grace-dt)
        self.hit_flash=max(0.,self.hit_flash-dt)
        self.contact_grace=max(0.,self.contact_grace-dt)
        for kind in self.weapon_buffs:
            self.weapon_buffs[kind]=max(0.,self.weapon_buffs[kind]-dt)
        self.t += dt
        self.respawn_shield = max(0., self.respawn_shield-dt)
        self.save_clock += dt
        if self.save_clock >= 10:
            self.save_clock = 0.
            self.persist()
        for effect in self.explosions:
            effect[2] -= dt
        self.explosions = [effect for effect in self.explosions if effect[2] > 0]
        p, keys = self.player, self.keys
        shield_max=8.+self.campaign.stats['shielding']*5
        self.shield_charge=min(shield_max,self.shield_charge+dt*(.35+self.campaign.stats['shielding']*.16))
        p['shot'] -= dt
        target = min(self.enemies, key=lambda e: delta(e['x'],p['x'])**2+delta(e['y'],p['y'])**2, default={'x':0.,'y':0.})
        dock = math.hypot(p['x'],p['y']) < 145
        if dock and not self.was_docked: self.sound_event('dock')
        self.was_docked=dock
        if dock:
            p['hp'] = min(self.campaign.max_hull,p['hp']+dt*26)
            p['fuel'] = min(100,p['fuel']+dt*35)
        if p['hp'] < self.campaign.max_hull*.38 or p['fuel'] < 23:
            self.returning = True
        if p['hp'] >= self.campaign.max_hull*.98 and p['fuel'] >= 98:
            self.returning = False
        returning = self.returning
        if self.auto:
            kind = self.campaign.mission[2]
            navigating = self.navigate_home or kind in ('relays','home') or (kind=='salvage' and self.salvage)
            tx,ty = (0,0) if returning else (self.waypoint()[:2] if navigating else (target['x'], target['y']))
            aim = math.atan2(delta(ty,p['y']),delta(tx,p['x']))
            error = (aim-p['a']+math.pi)%TAU-math.pi
            p['a'] += max(-2.7*dt,min(2.7*dt,error))
            distance = math.hypot(delta(tx,p['x']),delta(ty,p['y']))
            thrust = int(distance > (40 if returning or navigating else 360))
            if not returning and not navigating and distance<230:
                thrust = -1
            shooting = not returning and abs(error)<.18 and distance<820
        else:
            p['a'] += (int('Right' in keys or 'd' in keys)-int('Left' in keys or 'a' in keys))*3.4*dt
            thrust = int('Up' in keys or 'w' in keys)-int('Down' in keys or 's' in keys)
            shooting = True  # Primary weapon autofires during manual flight.
        if thrust and p['fuel'] > 0:
            acceleration = (300+55*self.campaign.levels['drive']+48*self.campaign.stats['engine'])*thrust
            p['vx'] += math.cos(p['a'])*acceleration*dt
            p['vy'] += math.sin(p['a'])*acceleration*dt
            p['fuel'] = max(0,p['fuel']-dt*1.4)
            if self.rng.random()<dt*100:
                self.particles.append([p['x']-math.cos(p['a'])*25*thrust,p['y']-math.sin(p['a'])*25*thrust,-math.cos(p['a'])*100*thrust,-math.sin(p['a'])*100*thrust,.8,CYAN])
        drag = math.exp(-dt*(3 if (self.auto and ((dock and returning) or (navigating and distance<100))) else .65))
        p['vx'] *= drag
        p['vy'] *= drag
        max_speed=720*(1+.065*self.campaign.stats['engine'])
        velocity=math.hypot(p['vx'],p['vy'])
        if velocity>max_speed:
            p['vx']*=max_speed/velocity;p['vy']*=max_speed/velocity
        p['x'] = wrap(p['x']+p['vx']*dt)
        p['y'] = wrap(p['y']+p['vy']*dt)
        if shooting and p['shot']<=0:
            self.fire(p)
            weapon_level=self.campaign.levels['weapon']
            cooldown={'pulse':max(.075,(.20,.19,.17,.13)[min(weapon_level,3)]-.012*max(0,weapon_level-3)),
                      'cannon':.34,'flame':.27,'scatter':.31,'laser':.19}[('flame' if self.weapon_buffs['flame']>0 else self.weapon_mode)]
            p['shot']=cooldown*(.56 if self.weapon_buffs['rapid']>0 else 1.)
        for e in self.enemies:
            dx,dy=delta(p['x'],e['x']),delta(p['y'],e['y'])
            d=math.hypot(dx,dy)
            aim=math.atan2(dy,dx)
            e['a'] += max(-dt*1.7,min(dt*1.7,(aim-e['a']+math.pi)%TAU-math.pi))
            speed=(75 if e['boss'] else (110,185,80)[e['kind']]*(1+.055*e['tier']))*self.settings['speed']
            if d<230:
                e['a'] += dt*1.8
            e['x']=wrap(e['x']+math.cos(e['a'])*speed*dt)
            e['y']=wrap(e['y']+math.sin(e['a'])*speed*dt)
            e['shot']-=dt
            if d<700 and e['shot']<0 and not dock:
                self.fire(e,True)
                e['shot']=(.8 if e['boss'] else self.rng.uniform(1.4,3.5)/(1+.15*e['tier']))*self.settings['fire']
        self.resolve_contacts()
        for bullet in self.bullets:
            x0,y0=bullet[:2]
            bullet[0]=wrap(x0+bullet[2]*dt)
            bullet[1]=wrap(y0+bullet[3]*dt)
            bullet[4]-=dt
            if bullet[4]<=0: continue
            hits=[]
            mode=bullet[7] if len(bullet)>7 else 'pulse'
            seen=bullet[9] if len(bullet)>9 else set()
            for index,(x,y,r,_) in enumerate(self.rocks):
                if index in self.destroyed_rocks or ('rock',index) in seen: continue
                hit=segment_hit(x0,y0,bullet[0],bullet[1],x,y,r*.82+(9 if mode=='flame' else 5 if mode=='cannon' else 0))
                if hit is not None: hits.append((hit,'rock',index))
            for enemy in ([p] if bullet[5] else self.enemies):
                if enemy['hp']<=0: continue
                if ('ship',id(enemy)) in seen: continue
                hit=segment_hit(x0,y0,bullet[0],bullet[1],enemy['x'],enemy['y'],enemy.get('radius',21)+(14 if mode=='flame' else 6 if mode=='cannon' else 0))
                if hit is not None: hits.append((hit,'ship',enemy))
            if not hits: continue
            _,kind,target=min(hits,key=lambda item:item[0])
            if len(bullet)>9:
                seen.add(('rock',target) if kind=='rock' else ('ship',id(target)))
            if len(bullet)<=8 or bullet[8]<=0: bullet[4]=0
            else: bullet[8]-=1
            if kind=='rock':
                rock=self.rocks[target]
                self.rock_hp[target]=self.rock_hp.get(target,math.ceil(rock[2]/13))-bullet[6]
                self.burst(rock[0],rock[1],GOLD,5)
                self.sound_event('ricochet')
                if self.rock_hp[target]<=0:
                    self.destroyed_rocks.add(target)
                    self.burst(rock[0],rock[1],GOLD,25)
                    self.sound_event('rock_break')
            elif bullet[5]:
                self.damage_player(bullet[6])
            else:
                target['hp']-=bullet[6]
                self.burst(target['x'],target['y'],GOLD,6)
        for e in self.enemies[:]:
            if e['hp']<=0:
                self.burst(e['x'],e['y'],PINK,35)
                self.sound_event('explosion')
                self.enemies.remove(e)
                self.score+=250
                self.kills+=1
                free_boss=e['boss'] and self.campaign.free_roam
                self.campaign.credits += (1200 if free_boss else 500) if e['boss'] else 60+15*e['tier']
                self.salvage.append([e['x'],e['y'],self.t])
                self.drop_loot(e['x'],e['y'],e['boss'])
                if e['boss']: self.campaign.add_stat_points(1)
                contract_before=self.campaign.free_contract
                self.objective_event('boss' if e['boss'] else 'kills')
                if not e['boss']:
                    self.spawn()
                elif free_boss:
                    self.boss_spawned=False
                    self.free_boss_count+=1
                    self.free_boss_due=self.t+self.rng.uniform(max(24,62-min(32,self.kills*.5)),max(30,82-min(32,self.kills*.5)))
                    if self.campaign.free_contract==contract_before:
                        self.notify('Flagship down // +1,200 CR // next incursion incoming')
        if self.campaign.awaiting_briefing: return
        if self.campaign.mission[2]=='boss' and not self.boss_spawned:
            self.spawn(boss=True)
            self.boss_spawned = True
        if self.campaign.free_roam and not self.boss_spawned and self.free_boss_due is not None and self.t>=self.free_boss_due:
            self.spawn(boss=True)
            self.boss_spawned=True
            self.notify('BOSS INBOUND // '+self.free_boss_names[self.free_boss_count%len(self.free_boss_names)])
        for core in self.salvage[:]:
            if self.campaign.awaiting_briefing or core not in self.salvage: break
            distance=math.hypot(delta(p['x'],core[0]),delta(p['y'],core[1]))
            magnet=self.campaign.levels['magnet']
            radius=(0,150,245,365,510)[magnet]+self.campaign.stats['scavenger']*45
            if magnet and 65<distance<radius:
                speed=min(1000,210+magnet*135+(radius-distance)*1.4)
                step=min(distance-55,speed*dt)
                core[0]=wrap(core[0]+delta(p['x'],core[0])/distance*step)
                core[1]=wrap(core[1]+delta(p['y'],core[1])/distance*step)
                distance=math.hypot(delta(p['x'],core[0]),delta(p['y'],core[1]))
            if distance < 65:
                self.salvage.remove(core)
                self.sound_event('pickup')
                self.campaign.credits += 30
                self.objective_event('salvage')
        self.salvage = self.salvage[-40:]
        self.update_pickups(dt)
        if self.campaign.awaiting_briefing: return
        free_relay=self.campaign.free_roam and self.campaign.contract[2]=='relays'
        if self.campaign.mission[2]=='relays' or free_relay:
            valid=(self.campaign.free_relay_target,) if free_relay else tuple(i for i in range(len(self.beacons)) if i not in self.campaign.relays)
            nearby = next((i for i in valid if math.hypot(delta(self.beacons[i][0],p['x']),delta(self.beacons[i][1],p['y']))<120),None)
            if nearby != self.scan_target:
                self.scan = 0.
                self.scan_target = nearby
            if nearby is not None:
                self.scan += dt
                if self.scan >= 4:
                    if free_relay:
                        self.campaign.free_relay_target=(nearby+1)%len(self.beacons)
                    else:
                        self.campaign.relays.append(nearby)
                    self.objective_event('relays')
                    self.scan = 0.
                    self.persist()
        if dock and not self.pilot_started:
            self.objective_event('home')
        self.bullets=[b for b in self.bullets if b[4]>0]
        for q in self.particles:
            q[0]=wrap(q[0]+q[2]*dt)
            q[1]=wrap(q[1]+q[3]*dt)
            q[4]-=dt
        self.particles=[q for q in self.particles if q[4]>0][-500:]
        if p['hp']<=0 or p['fuel']<=0:
            self.burst(p['x'],p['y'],CYAN,70)
            p.update(x=0.,y=-80.,vx=0.,vy=0.,hp=self.campaign.max_hull,fuel=100.)
            self.camera = [p['x'], p['y']]
            self.trail.clear()
            self.respawn_shield = self.settings['shield']
            self.shield_charge=3.+self.campaign.stats['shielding']*2
            self.sound_event('explosion')
            self.campaign.credits = max(0,self.campaign.credits-100)
            self.notify('Emergency recall // 100 credits recovery fee. Upgrades retained.')
            self.persist()

        # A trailing camera lets the ship slide ahead during acceleration and
        # bank visibly through turns. Unwrapped coordinates keep stars continuous.
        follow = 1 - math.exp(-dt * 3.0)
        for axis, key in enumerate(('x', 'y')):
            movement = delta(p[key], self.camera[axis]) * follow
            self.camera[axis] += movement
            self.camera_velocity[axis] = movement / dt if dt else 0.
        self.trail_clock += dt
        if self.trail_clock >= 1/60:
            self.trail_clock %= 1/60
            if math.hypot(p['vx'], p['vy']) > 25:
                self.trail.append([p['x']-math.cos(p['a'])*25,
                                   p['y']-math.sin(p['a'])*25, self.t])
        self.trail = [point for point in self.trail if self.t-point[2] < 1.5][-100:]

    def draw(self,c,w,h):
        PALETTE.update({CYAN:self.palette_values['primary'],PURPLE:self.palette_values['secondary'],GOLD:self.palette_values['gold']})
        c.set_source_rgb(.006,.009,.022)
        c.paint()
        p=self.player
        # Brighter foreground stars move faster than the distant star layers.
        for sx,sy,z,rgb in self.stars:
            depth = .12 + z*.75
            x=(sx*w-self.camera[0]*depth)%w
            y=(sy*h-self.camera[1]*depth)%h
            vx,vy=self.camera_velocity
            streak = .035*z
            c.new_path();c.move_to(x,y);c.line_to(x+vx*streak,y+vy*streak)
            c.set_source_rgba(*rgb,.25+z*.5);c.set_line_width(1+z*.6);c.stroke()
            c.set_source_rgba(*rgb,.3+z*.55)
            c.arc(x,y,.55+z*.65,0,TAU)
            c.fill()
        def screen(x,y):
            return w/2+delta(x,self.camera[0]),h/2+delta(y,self.camera[1])
        for first,second in zip(self.trail,self.trail[1:]):
            fade = max(0,1-(self.t-second[2])/1.5)
            a,b=screen(*first[:2]),screen(*second[:2])
            if math.dist(a,b)<100:
                line(c,[a,b],CYAN,9,fade*.08)
                line(c,[a,b],CYAN,3,fade*.45)
        for px,py,r,rgb in self.planets:
            x,y=screen(px,py)
            if x < -r*2 or x>w+r*2 or y < -r*2 or y>h+r*2:
                continue
            grad=cairo.RadialGradient(x-r*.3,y-r*.3,0,x,y,r)
            grad.add_color_stop_rgb(0,*[v*.17 for v in rgb])
            grad.add_color_stop_rgb(1,.005,.007,.018)
            c.set_source(grad)
            c.arc(x,y,r,0,TAU)
            c.fill()
            circle(c,x,y,r,rgb,.5)
            c.save()
            c.translate(x,y)
            c.rotate(-.38)
            c.scale(1,.28)
            circle(c,0,0,r*1.5,rgb,.22,2)
            c.restore()
            for offset in [-.5,0,.5]:
                c.save()
                c.translate(x,y+offset*r)
                c.scale(1,.18)
                circle(c,0,0,r*math.sqrt(1-offset*offset),rgb,.13)
                c.restore()
        for rock_index, (rx,ry,r,shape) in enumerate(self.rocks):
            if rock_index in self.destroyed_rocks: continue
            x,y=screen(rx,ry)
            if -r<x<w+r and -r<y<h+r:
                self.atlas.draw(c, 'rock'+str(rock_index%4), x, y, r*2.2, self.t*.025+rock_index)
        bx,by=screen(0,0)
        if -200<bx<w+200 and -200<by<h+200:
            circle(c,bx,by,145,CYAN,.10)
            self.atlas.draw(c, 'relay', bx, by, 185, self.t*.1)
            text(c,bx-63,by+120,'OMARCHY // RELAY',11,CYAN,.7)
        for core in self.salvage:
            x,y=screen(core[0],core[1])
            magnet=self.campaign.levels['magnet']
            radius=(0,150,245,365,510)[magnet]+self.campaign.stats['scavenger']*45
            distance=math.hypot(delta(self.player['x'],core[0]),delta(self.player['y'],core[1]))
            if magnet and distance<radius*.7:
                sx,sy=screen(self.player['x'],self.player['y'])
                line(c,[(x,y),(sx,sy)],GOLD,1,.18*(1-distance/(radius*.7)))
            circle(c,x,y,12+math.sin(self.t*4)*2,GOLD,.8,2)
            line(c,[(x-5,y),(x,y-5),(x+5,y),(x,y+5)],GOLD,2,1,True)
        pickup_colors={'rapid':GOLD,'spread':PURPLE,'flame':PINK,'pierce':CYAN,'health':(1.,.28,.34),'shield':(.35,.62,1.)}
        pickup_marks={'rapid':'R','spread':'S','flame':'F','pierce':'P','health':'+','shield':'+'}
        for orb in self.pickups:
            x,y=screen(orb['x'],orb['y']);rgb=pickup_colors[orb['kind']]
            pulse=math.sin(orb['phase'])*2
            circle(c,x,y,11+pulse,rgb,.24,7)
            circle(c,x,y,8+pulse,rgb,.9,1.5)
            text(c,x-3.5,y+4,pickup_marks[orb['kind']],10,rgb)
        if self.campaign.stage>=2:
            for i,(wx,wy) in enumerate(self.beacons):
                x,y=screen(wx,wy)
                active_relay=self.campaign.free_roam and self.campaign.contract[2]=='relays' and i==self.campaign.free_relay_target
                rgb=CYAN if i in self.campaign.relays or active_relay else GOLD
                circle(c,x,y,65,rgb,.4,2)
                self.atlas.draw(c,'relay',x,y,85,-self.t*.2)
                text(c,x-42,y+87,f'MIRROR {i+1}',12,rgb)
                if self.scan_target==i and self.scan>0:
                    text(c,x-42,y+104,f'LINK {self.scan/4:.0%}',12,GOLD)
        wx,wy,label=self.waypoint()
        dx,dy=delta(wx,p['x']),delta(wy,p['y'])
        boss_active=self.campaign.free_roam and any(e['boss'] for e in self.enemies)
        if math.hypot(dx,dy)>170 and (self.navigate_home or self.campaign.mission[2] not in ('kills','endless') or boss_active):
            angle=math.atan2(dy,dx)
            x=w/2+math.cos(angle)*min(w*.36,350)
            y=h/2+math.sin(angle)*min(h*.28,210)
            c.save(); c.translate(x,y); c.rotate(angle)
            line(c,[(-9,-6),(0,0),(-9,6)],GOLD,2,.8)
            c.restore()
            text(c,x-65,y+22,f'{label} {math.hypot(dx,dy):.0f}m',10,GOLD,.8)
        for b in self.bullets:
            x,y=screen(b[0],b[1])
            mode=b[7] if len(b)>7 else 'pulse'
            rgb=PINK if b[5] else {'pulse':CYAN,'cannon':GOLD,'flame':PINK,'scatter':PURPLE,'laser':(1.,.9,.72)}.get(mode,CYAN)
            width=8 if mode=='flame' else 6 if mode=='cannon' else 4 if mode=='laser' else 3
            pts=[(x,y),(x-b[2]*(.042 if mode=='flame' else .032),y-b[3]*(.042 if mode=='flame' else .032))]
            line(c,pts,rgb,width*2,.16)
            line(c,pts,rgb,width*.45,.95)
            circle(c,x,y,width*.6,rgb,.95)
        for q in self.particles:
            x,y=screen(q[0],q[1])
            line(c,[(x,y),(x-q[2]*.025,y-q[3]*.025)],q[5],2,min(1,q[4]*2))
        for ex,ey,life,green in self.explosions:
            x,y=screen(ex,ey)
            self.atlas.draw(c, 'spark' if green else 'burst', x, y, 55+(1-life/.7)*110, self.t*.25, min(1,life*3))
        for e in self.enemies:
            x,y=screen(e['x'],e['y'])
            if -60<x<w+60 and -60<y<h+60:
                if e['boss']:
                    self.atlas.draw(c,'relay',x,y,145,e['a'])
                    text(c,x-60,y-90,e.get('boss_name','COMMENT SECTION'),12,PINK)
                else:
                    self.ship(c,x,y,e['a'],(PINK,GOLD,PURPLE)[e['kind']],e['kind'])
                if e['hp']<e['maxhp'] or e['boss']:
                    line(c,[(x-25,y-42),(x-25+50*max(0,e['hp'])/e['maxhp'],y-42)],PINK,3,.8)
        ship_x,ship_y=screen(p['x'],p['y'])
        self.ship(c,ship_x,ship_y,p['a'],CYAN,-1)
        circle(c,ship_x,ship_y,36,PINK if self.hit_flash>0 else CYAN,.8 if self.hit_flash>0 else (.45 if self.respawn_shield>0 or self.hit_grace>0 else .10),2)
        self.draw_hud(c,w,h)
        self.draw_campaign(c,w,h)

    def objective_text(self):
        if self.campaign.free_roam:
            title,_,kind,goal,_=self.campaign.contract
            if kind=='relays':
                return f'{title}  //  MIRROR {self.campaign.free_relay_target+1}'
            return f'{title}  {self.campaign.progress}/{goal}'
        _,_,kind,goal,_=self.campaign.mission
        return {
            'kills':f'Doomscroll drones  {self.campaign.progress}/{goal}',
            'salvage':f'Signed packages  {self.campaign.progress}/{goal}',
            'relays':f'Mirrors online  {len(self.campaign.relays)}/3',
            'boss':'Defeat the Comment Section',
            'home':'Return home / ENTER deploys release',
            'endless':'Still shipping  /  Free patrol',
        }[kind]

    def draw_hud(self,c,w,h):
        p=self.player
        c.save()
        c.translate(math.sin(self.t*.03)*4,math.cos(self.t*.04)*3)
        text(c,28,31,'OMARCHY: LUNATIC FRINGE',12,CYAN,.6)
        text(c,28,54,(f'{self.campaign.stage+1}/{len(MISSIONS)}  ' if not self.campaign.free_roam else 'FREE  ')+self.objective_text(),12,(.77,.85,.88),.9)
        text(c,w-170,31,f'{self.campaign.credits:,} CR',12,GOLD,.8)
        for i,(label,fraction,rgb) in enumerate([
                ('SHLD',self.shield_charge/max(1,8+self.campaign.stats['shielding']*5),(.35,.62,1.)),
                ('HULL',max(0,p['hp'])/self.campaign.max_hull,PINK if p['hp']<self.campaign.max_hull*.3 else CYAN),
                ('FUEL',p['fuel']/100,PURPLE)]):
            y=h-82+i*18
            text(c,28,y+4,label,9,rgb,.7)
            line(c,[(70,y),(215,y)],rgb,4,.12)
            line(c,[(70,y),(70+145*fraction,y)],rgb,4,.85)
        active=[f'{name.upper()} {round(value)}s' for name,value in self.weapon_buffs.items() if value>0]
        text(c,28,h-100,'Q  '+self.weapon_mode.upper()+('  //  '+'  '.join(active[:2]) if active else ''),9,GOLD if active else CYAN,.72)
        text(c,28,h-17,'TAB  Briefing',9,(.65,.75,.8),.5)
        if math.hypot(p['x'],p['y'])<145 and self.pilot_started:
            text(c,245,h-45,'U  Workshop / Repairing',10,CYAN,.65)
        # Compact radar; no sector label or decorative readouts.
        rx,ry=w-84,h-84
        circle(c,rx,ry,56,CYAN,.22)
        line(c,[(rx-56,ry),(rx+56,ry)],CYAN,1,.1)
        line(c,[(rx,ry-56),(rx,ry+56)],CYAN,1,.1)
        for enemy,rgb in [(e,PINK) for e in self.enemies]+[({'x':0,'y':0},CYAN)]:
            dx,dy=delta(enemy['x'],p['x'])*.025,delta(enemy['y'],p['y'])*.025
            if math.hypot(dx,dy)<53:
                color(c,rgb,.8);c.rectangle(rx+dx-1.5,ry+dy-1.5,3,3);c.fill()
        circle(c,rx,ry,2,CYAN,.8)
        c.restore()
        if self.notice_until>self.t and not self.shop and not self.briefing:
            lines=textwrap.wrap(self.notice,width=max(30,int((w-360)/6.5)))
            for row,fragment in enumerate(lines[:2]):
                text(c,28,83+row*15,fragment,11,GOLD,min(1,self.notice_until-self.t))
        if self.campaign.error:
            text(c,28,h-90,self.campaign.error,10,PINK)
        # The title fades away after six seconds, or immediately upon takeover.
        alpha=min(1,max(0,6-self.intro_elapsed)) if not self.pilot_started else self.intro_fade/.5
        if alpha>0 and not self.shop and not self.briefing:
            size=min(58,(w-64)/13.5)
            c.select_font_face('monospace',cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_NORMAL)
            c.set_font_size(size)
            title='OMARCHY: LUNATIC FRINGE'
            width=c.text_extents(title).width
            text(c,(w-width)/2,h*.30,title,size,CYAN,alpha)
            subtitle='S T I L L   S H I P P I N G'
            text(c,w/2-138,h*.30+35,subtitle,15,(.7,.82,.87),alpha*.75)
            text(c,w/2-174,h*.30+76,'W / ARROWS  Fly     WEAPONS  AUTOFIRE',13,CYAN,alpha*.8)
            text(c,w/2-174,h*.30+102,'TAB  Briefing      F2  Difficulty',11,(.7,.82,.87),alpha*.7)
        if self.briefing:
            self.draw_briefing(c,w,h)

    def draw_briefing(self,c,w,h):
        color(c,(.003,.008,.018),.95);c.paint()
        pw=min(700,w-60);x=(w-pw)/2;y=max(25,(h-530)/2)
        free_patrol=self.campaign.free_roam and not self.campaign.awaiting_briefing
        heading='FREE PATROL / ACTIVE CONTRACT' if free_patrol else 'CAMPAIGN COMPLETE' if self.campaign.free_roam else 'MISSION BRIEFING'
        if self.campaign.awaiting_briefing and not self.campaign.free_roam:
            heading=f'MISSION {self.campaign.stage} COMPLETE'
        if self.replay_confirm: heading='REPLAY THE STORY?'
        text(c,x,y+32,heading,24,CYAN)
        mission_title,mission_desc=(self.campaign.contract[0],self.campaign.contract[1]) if self.campaign.free_roam else (self.campaign.mission[0],self.campaign.mission[1])
        text(c,x,y+66,mission_title,15,GOLD)
        for i,fragment in enumerate(textwrap.wrap(mission_desc,width=int(pw/7.4))):
            text(c,x,y+98+i*20,fragment,12,(.75,.84,.88))
        text(c,x,y+190,self.objective_text(),13,CYAN)
        if self.campaign.awaiting_briefing: return
        if self.campaign.mission[2]=='relays' or (self.campaign.free_roam and self.campaign.contract[2]=='relays'):
            relay_text='Hold within 120m of the active mirror for four seconds.' if self.campaign.free_roam else 'Hold within 120m of each mirror for four continuous seconds.'
            text(c,x,y+214,relay_text,11,CYAN,.8)
        text(c,x,y+255,'F2  '+self.campaign.difficulty.upper()+' DIFFICULTY',14,GOLD)
        desc={'easy':'Reduced damage, fewer enemies, slower volleys. Start here.',
              'normal':'Balanced pressure and moderate protection between hits.',
              'hard':'Stronger enemies, faster volleys, short hit protection.'}[self.campaign.difficulty]
        text(c,x,y+278,desc,11,(.75,.84,.88))
        text(c,x,y+310,'AUDIO  '+('OFF' if self.campaign.muted else 'ON')+f'   MUSIC {round(self.sound.music_volume*100) if self.sound else 0}%',12,CYAN)
        if self.sound and (self.sound.error or self.sound.music_error):
            message='Audio device unavailable; gameplay continues silently.' if self.sound.error else 'Music playback unavailable; effects still work.'
            text(c,x,y+329,message,10,PINK)
        controls=['W / UP forward    S / DOWN reverse    A / D or LEFT / RIGHT turn',
                  'Weapons autofire while piloting    H home    U workshop',
                  'M audio on/off    - / = music volume    P autopilot',
                  'ESC exit    TAB resume']
        for i,fragment in enumerate(controls):
            text(c,x,y+373+i*24,fragment,11,(.75,.84,.88))
        if self.replay_confirm:
            text(c,x,y+465,'ENTER restart from Mission 1, keeping credits and upgrades. ESC cancel.',11,GOLD)
        elif self.campaign.awaiting_briefing:
            label='ENTER launch next mission' if not self.campaign.free_roam else 'ENTER free patrol  /  R replay story (keep upgrades)'
            text(c,x,y+465,label,12,GOLD)
        else:
            text(c,x,y+465,'R replay story (keep upgrades)  /  TAB return',11,CYAN,.7)

    def draw_campaign(self,c,w,h):
        if not self.shop:
            return
        color(c,(0.,.004,.01),.87)
        c.paint()
        pw=min(960,w-32)
        ph=min(620,h-32)
        x,y=(w-pw)/2,(h-ph)/2
        color(c,(.014,.038,.038),1)
        c.rectangle(x,y,pw,ph)
        c.fill()
        line(c,[(x,y),(x+pw,y),(x+pw,y+ph),(x,y+ph)],CYAN,1,.75,True)
        text(c,x+26,y+37,'OMARCHY // RELAY WORKSHOP',20,CYAN)
        text(c,x+26,y+63,'FLIGHT PAUSED  /  SPEND CREDITS OR SHAPE A BUILD',11,CYAN,.6)
        text(c,x+26,y+94,f'CREDITS  {self.campaign.credits:06d}',14,GOLD)
        text(c,x+pw*.52,y+94,f'BUILD POINTS  {self.campaign.stat_points} READY  /  {self.campaign.stat_points_spent}/18 SPENT',12,GOLD)
        split=x+pw*.49
        line(c,[(split,y+110),(split,y+ph-42)],CYAN,1,.24)
        text(c,x+26,y+126,'CREDIT UPGRADES',11,CYAN,.7)
        text(c,split+18,y+126,'FLIGHT BUILD  /  MAX 18 POINTS TOTAL',11,CYAN,.7)
        descriptions={
            'weapon':'More barrels, triple damage, then faster and stronger overclocks.',
            'hull':'Adds 35 hull for early tiers, then 25 per overclock.',
            'drive':'Improves forward AND reverse thrust by 55 per tier.',
            'magnet':'Credit motes curve in from farther away at each level.',
        }
        upgrade_gap=min(77,(ph-178)/4)
        for i,(key,(name,tiers,costs)) in enumerate(UPGRADES.items()):
            level=self.campaign.levels[key]
            yy=y+159+i*upgrade_gap
            text(c,x+26,yy,f'[{i+1}] {name}',12,CYAN)
            offer='MAXIMUM TIER' if level>=len(costs) else f'{tiers[level+1]} / {costs[level]} CR'
            text(c,x+26,yy+19,f'{tiers[level]}  ->  {offer}',10,GOLD if level<len(costs) else CYAN)
            text(c,x+26,yy+37,descriptions[key],9,(.65,.8,.75),.8)
        point_keys=('5','6','7','8','9','0')
        stat_gap=min(51,(ph-190)/6)
        for i,(key,(name,description)) in enumerate(BUILD_STATS.items()):
            level=self.campaign.stats[key];yy=y+158+i*stat_gap
            text(c,split+18,yy,f'[{point_keys[i]}] {name}  {level}/6',11,CYAN if level<6 else GOLD)
            text(c,split+18,yy+17,description,9,(.68,.8,.78),.85)
            line(c,[(split+18,yy+28),(min(x+pw-25,split+18+level*22),yy+28)],GOLD,3,.82)
        if self.notice_until>self.t:
            text(c,x+26,y+ph-58,self.notice[:int((pw-52)/7)],11,GOLD)
        text(c,x+26,y+ph-28,'1-4 INSTALL UPGRADES    5-0 SPEND POINTS    T RESET BUILD    U / ESC RETURN',10,CYAN,.8)

    def ship(self,c,x,y,a,rgb,kind):
        if kind == -1:
            # Use the maintainer-supplied rounded Omawing sprite, facing right.
            # Its original mint/white art remains intact across game palettes.
            self.atlas.draw(c, 'player', x, y, 68, a)
        else:
            name = ('red', 'interceptor', 'violet')[kind]
            self.atlas.draw(c, name, x, y, (62, 58, 64)[kind], a + math.pi/2)

def main():
    parser=argparse.ArgumentParser(prog='omarchy-lunatic-fringe')
    parser.add_argument('--render',type=Path,help='Render a deterministic PNG without a display')
    parser.add_argument('--preview',action='store_true',help='Run in a normal window')
    parser.add_argument('--seconds',type=float,default=0,help='Close automatically after this many seconds')
    parser.add_argument('--app-id',default='org.omarchy.screensaver')
    parser.add_argument('--sound-check',action='store_true',help='Play a short effects check during the preview')
    parser.add_argument('--music',action='store_true',help='Play soundtrack during a user-launched game')
    args=parser.parse_args()
    if args.render:
        sim=Simulation(42)
        for _ in range(900):
            sim.step(1/60)
        surface=cairo.ImageSurface(cairo.FORMAT_RGB24,1600,900)
        sim.draw(cairo.Context(surface),1600,900)
        surface.write_to_png(str(args.render))
        return
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,Gdk,GLib
    if args.preview:
        args.app_id = 'org.omarchy.omavoid-preview'
    GLib.set_prgname(args.app_id)
    windows=[]
    started=time.monotonic()
    display=Gdk.Display.get_default()
    if display is None:
        raise SystemExit('A Wayland or X11 desktop session is required.')
    from sound import SoundBank
    shared=Simulation(save_path=Path.home()/'.local/state/omavoid/campaign.json')
    shared.fire_keys=load_fire_keys(Path.home()/'.config/omavoid/controls.json')
    shared.sound=SoundBank(Path.home()/'.cache/omavoid/sfx',Path.home()/'.config/omavoid/audio.json')
    shared.sound_on_auto=args.music
    if args.music:
        shared.sound.muted=Campaign(shared.save_path).muted
        if not shared.sound.muted: shared.sound.start_music()
    def quit_all(*_):
        if args.sound_check:
            print('Audio check: '+(shared.sound.error or shared.sound.music_error or 'no playback errors'),flush=True)
        shared.persist()
        shared.sound.close()
        Gtk.main_quit()
        return True
    class Saver(Gtk.Window):
        def __init__(self,monitor):
            super().__init__(title='Omarchy: Lunatic Fringe')
            self.sim=shared
            self.last=time.monotonic()
            self.pointer=None
            self.p_held=False
            self.action_held=set()
            self.set_default_size(1280,800)
            self.set_wmclass(args.app_id,args.app_id)
            self.area=Gtk.DrawingArea()
            self.add(self.area)
            self.area.connect('draw',lambda area,ctx:self.sim.draw(ctx,area.get_allocated_width(),area.get_allocated_height()))
            self.connect('delete-event',quit_all)
            self.connect('key-press-event',self.key)
            self.connect('key-release-event',self.release)
            self.add_events(Gdk.EventMask.POINTER_MOTION_MASK|Gdk.EventMask.BUTTON_PRESS_MASK)
            self.connect('motion-notify-event',self.motion)
            self.connect('button-press-event',lambda *_: quit_all() if self.sim.auto else True)
            self.connect('focus-out-event',lambda *_: self.sim.keys.clear())
            if not args.preview:
                self.fullscreen_on_monitor(Gdk.Screen.get_default(),monitor)
            self.show_all()
            self.get_window().set_cursor(Gdk.Cursor.new_for_display(display,Gdk.CursorType.BLANK_CURSOR))
        def key(self,_,event):
            key=Gdk.keyval_name(event.keyval)
            key=key.lower() if len(key)==1 else key
            if key=='Escape':
                if self.sim.replay_confirm:
                    self.sim.replay_confirm=False
                elif self.sim.campaign.awaiting_briefing:
                    quit_all()
                elif self.sim.briefing:
                    self.sim.briefing=False
                elif self.sim.shop:
                    self.sim.shop=False
                else:
                    quit_all()
            elif key in {'Return','r','Tab','F2','m','u','h','q','t','1','2','3','4','5','6','7','8','9','0','minus','equal','plus','KP_Subtract','KP_Add'}:
                if key not in self.action_held:
                    if key=='Return':
                        if self.sim.briefing: self.sim.launch_chapter()
                        elif math.hypot(self.sim.player['x'],self.sim.player['y'])<145:
                            self.sim.objective_event('home')
                    elif key=='r':
                        if self.sim.briefing: self.sim.replay_confirm=True
                    elif key=='Tab':
                        was_started=self.sim.pilot_started
                        self.sim.take_control()
                        self.sim.shop=False
                        self.sim.briefing=True if not was_started or self.sim.campaign.awaiting_briefing else not self.sim.briefing
                        self.sim.keys.clear()
                    elif key=='F2': self.sim.cycle_difficulty()
                    elif key=='m': self.sim.toggle_mute()
                    elif key in {'minus','KP_Subtract'}: self.sim.change_music_volume(-.03)
                    elif key in {'equal','plus','KP_Add'}: self.sim.change_music_volume(.03)
                    elif key=='u':
                        if not self.sim.briefing: self.sim.toggle_shop()
                    elif key=='h':
                        self.sim.take_control()
                        self.sim.navigate_home=not self.sim.navigate_home
                    elif key=='q': self.sim.cycle_weapon()
                    elif key=='t' and self.sim.shop: self.sim.reset_build()
                    elif key in {'1','2','3','4'}: self.sim.purchase(key)
                    elif key in {'5','6','7','8','9','0'}: self.sim.buy_build_stat(key)
                self.action_held.add(key)
            elif key.lower()=='p':
                if not self.p_held:
                    if self.sim.auto:
                        self.sim.take_control()
                    elif not self.sim.shop and not self.sim.briefing:
                        self.sim.auto=True
                        if not self.sim.sound_on_auto: self.sim.sound.hush()
                    self.sim.keys.clear()
                self.p_held=True
            elif key in {'Shift_L','Shift_R','Control_R','Alt_L','Alt_R','Caps_Lock'}:
                pass
            elif self.sim.press_control(key):
                pass
            else:
                if self.sim.auto: quit_all()
            return True
        def release(self,_,event):
            key=Gdk.keyval_name(event.keyval)
            key=key.lower() if len(key)==1 else key
            self.sim.keys.discard(key)
            self.action_held.discard(key)
            if key.lower()=='p':
                self.p_held=False
        def motion(self,_,event):
            pos=(event.x_root,event.y_root)
            if self.sim.auto and self.pointer and time.monotonic()-started>2 and math.dist(pos,self.pointer)>8:
                quit_all()
            if self.pointer is None or time.monotonic()-started<=2:
                self.pointer=pos
    for monitor in range(1 if args.preview else display.get_n_monitors()):
        windows.append(Saver(monitor))
    def tick():
        now=time.monotonic()
        if args.seconds and now-started>=args.seconds:
            quit_all()
            return False
        dt=min(.05,now-windows[0].last)
        windows[0].last=now
        for _ in range(2):
            shared.step(dt/2)
        shared.sound.poll()
        for window in windows:
            window.area.queue_draw()
        return True
    if args.sound_check:
        from sound import EFFECTS
        def check_effect(name):
            shared.sound.play(name)
            return False
        for index,name in enumerate(EFFECTS):
            GLib.timeout_add(300+index*750,check_effect,name)
    GLib.timeout_add(16,tick)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, quit_all)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, quit_all)
    Gtk.main()

if __name__=='__main__':
    main()
