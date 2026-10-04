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
from campaign import Campaign, UPGRADES, DIFFICULTIES, MISSIONS

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
        self.beacons = [(-1250., -650.), (1350., -450.), (450., 1500.)]
        self.scan = 0.
        self.scan_target = None
        self.respawn_shield = 3.
        self.boss_spawned = False
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
        self.notify('Sound muted' if self.campaign.muted else 'Sound on')
        self.persist()

    def damage_player(self,amount):
        p=self.player
        if self.respawn_shield>0 or self.hit_grace>0 or math.hypot(p['x'],p['y'])<145:
            return False
        p['hp']-=amount*self.settings['damage']
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
        tier = min(8, self.campaign.stage + (self.kills//20 if self.campaign.stage==5 else 0))
        kind = 2 if boss else r.randrange(min(3, 1+self.campaign.stage))
        hp = (100 if boss else 3+tier*2+(3 if kind==2 else 0))*self.settings['hull']
        self.enemies.append(dict(x=wrap(p['x']+math.cos(a)*d), y=wrap(p['y']+math.sin(a)*d),
                                 a=a, hp=hp, maxhp=hp, shot=r.uniform(.3,3), kind=kind,
                                 boss=boss, tier=tier, radius=65 if boss else 25))

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
            self.trail.clear()
            self.kills = 0
            self.score = 0
            self.scan = 0.
            self.boss_spawned = False
            self.returning = False
            self.player.update(x=0., y=-90., vx=0., vy=0., hp=self.campaign.max_hull, fuel=100.)
            self.camera = [0., -90.]
            self.respawn_shield = self.settings['shield']
            self.intro_fade = .5
            self.was_docked = True
            if self.sound: self.sound.muted=self.campaign.muted
            for _ in range(self.settings['population']+min(3,self.campaign.stage)):
                self.spawn()
            self.briefing=self.campaign.awaiting_briefing or self.campaign.stage==5
            if self.campaign.error: self.notify(self.campaign.error)
        self.auto = False

    def objective_event(self, kind):
        completed=self.campaign.mission[0]
        if self.campaign.event(kind):
            self.notify('Complete: '+completed)
            self.sound_event('mission')
            self.salvage.clear()  # Old chapter drops cannot complete a new mission.
            self.scan=0.
            self.scan_target=None
            self.navigate_home=False
            if self.pilot_started:
                self.briefing=True
                self.keys.clear()
            else:
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
        self.enemies.clear();self.bullets.clear();self.salvage.clear();self.trail.clear()
        self.kills=0;self.scan=0.;self.scan_target=None;self.boss_spawned=False
        self.navigate_home=False;self.returning=False;self.keys.clear()
        self.player.update(x=0.,y=-90.,vx=0.,vy=0.,hp=self.campaign.max_hull,fuel=100.)
        self.camera=[0.,-90.];self.respawn_shield=self.settings['shield']
        for _ in range(self.settings['population']): self.spawn()
        self.notify('Mission 1 / Let the Agents Cook')
        self.persist()

    def waypoint(self):
        if self.navigate_home:
            return 0.,0.,'HOME / WORKSHOP'
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
        category = {'1':'weapon','2':'hull','3':'drive'}.get(key)
        if category:
            old_max = self.campaign.max_hull
            result=self.campaign.buy(category)
            self.notify(result)
            if result.startswith('Installed:'): self.sound_event('upgrade')
            self.player['hp'] += self.campaign.max_hull-old_max
            self.persist()

    def burst(self, x, y, rgb, n=25):
        if n >= 25:
            self.explosions.append([x, y, .7, rgb == CYAN])
        for _ in range(n):
            a = self.rng.random()*TAU
            s = self.rng.uniform(30,240)
            self.particles.append([x,y,math.cos(a)*s,math.sin(a)*s,self.rng.uniform(.3,1.2),rgb])

    def press_control(self, key):
        key = key.lower() if len(key) == 1 else key
        if key not in {'Up', 'Down', 'Left', 'Right', 'w', 'a', 's', 'd'} | self.fire_keys:
            return False
        self.take_control()
        if not self.shop and not self.briefing:
            self.keys.add(key)
        return True

    def fire(self, ship, enemy=False):
        tier = 0 if enemy else self.campaign.levels['weapon']
        if not enemy: self.sound_event(('laser','twin','scatter','plasma')[tier])
        angles = [-.16,0,.16] if tier>=2 else ([0,0] if tier==1 else [0])
        if enemy and (ship['boss'] or ship['kind']==2):
            angles = [-.28,-.14,0,.14,.28] if ship['boss'] else [-.13,0,.13]
        for index,offset in enumerate(angles):
            a = ship['a']+offset
            side = (-8 if index==0 else 8) if tier==1 else 0
            speed = 510*self.settings['speed'] if enemy else (1050 if tier==3 else 800)
            damage = (12 if ship.get('boss') else 6+ship.get('tier',0)) if enemy else (3 if tier==3 else 1)
            self.bullets.append([ship['x']+math.cos(a)*28-math.sin(a)*side,
                                 ship['y']+math.sin(a)*28+math.cos(a)*side,
                                 math.cos(a)*speed+ship.get('vx',0)*.35,
                                 math.sin(a)*speed+ship.get('vy',0)*.35,
                                 1.8,enemy,damage])

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
            shooting = bool(self.fire_keys & keys)
        if thrust and p['fuel'] > 0:
            acceleration = (300+55*self.campaign.levels['drive'])*thrust
            p['vx'] += math.cos(p['a'])*acceleration*dt
            p['vy'] += math.sin(p['a'])*acceleration*dt
            p['fuel'] = max(0,p['fuel']-dt*1.4)
            if self.rng.random()<dt*100:
                self.particles.append([p['x']-math.cos(p['a'])*25*thrust,p['y']-math.sin(p['a'])*25*thrust,-math.cos(p['a'])*100*thrust,-math.sin(p['a'])*100*thrust,.8,CYAN])
        drag = math.exp(-dt*(3 if (self.auto and ((dock and returning) or (navigating and distance<100))) else .65))
        p['vx'] *= drag
        p['vy'] *= drag
        p['x'] = wrap(p['x']+p['vx']*dt)
        p['y'] = wrap(p['y']+p['vy']*dt)
        if shooting and p['shot']<=0:
            self.fire(p)
            p['shot']=(.20,.19,.17,.13)[self.campaign.levels['weapon']]
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
            for index,(x,y,r,_) in enumerate(self.rocks):
                if index in self.destroyed_rocks: continue
                hit=segment_hit(x0,y0,bullet[0],bullet[1],x,y,r*.82)
                if hit is not None: hits.append((hit,'rock',index))
            for enemy in ([p] if bullet[5] else self.enemies):
                if enemy['hp']<=0: continue
                hit=segment_hit(x0,y0,bullet[0],bullet[1],enemy['x'],enemy['y'],enemy.get('radius',21))
                if hit is not None: hits.append((hit,'ship',enemy))
            if not hits: continue
            _,kind,target=min(hits,key=lambda item:item[0])
            bullet[4]=0
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
                self.campaign.credits += 500 if e['boss'] else 60+15*e['tier']
                self.salvage.append([e['x'],e['y'],self.t])
                self.objective_event('boss' if e['boss'] else 'kills')
                if not e['boss']:
                    self.spawn()
        if self.campaign.awaiting_briefing: return
        if self.campaign.mission[2]=='boss' and not self.boss_spawned:
            self.spawn(boss=True)
            self.boss_spawned = True
        for core in self.salvage[:]:
            if self.campaign.awaiting_briefing or core not in self.salvage: break
            if math.hypot(delta(core[0],p['x']),delta(core[1],p['y'])) < 65:
                self.salvage.remove(core)
                self.sound_event('pickup')
                self.campaign.credits += 30
                self.objective_event('salvage')
        self.salvage = self.salvage[-40:]
        if self.campaign.awaiting_briefing: return
        if self.campaign.mission[2]=='relays':
            nearby = next((i for i,xy in enumerate(self.beacons) if i not in self.campaign.relays and math.hypot(delta(xy[0],p['x']),delta(xy[1],p['y']))<120),None)
            if nearby != self.scan_target:
                self.scan = 0.
                self.scan_target = nearby
            if nearby is not None:
                self.scan += dt
                if self.scan >= 4:
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
            circle(c,x,y,12+math.sin(self.t*4)*2,GOLD,.8,2)
            line(c,[(x-5,y),(x,y-5),(x+5,y),(x,y+5)],GOLD,2,1,True)
        if self.campaign.stage>=2:
            for i,(wx,wy) in enumerate(self.beacons):
                x,y=screen(wx,wy)
                rgb=CYAN if i in self.campaign.relays else GOLD
                circle(c,x,y,65,rgb,.4,2)
                self.atlas.draw(c,'relay',x,y,85,-self.t*.2)
                text(c,x-42,y+87,f'MIRROR {i+1}',12,rgb)
                if self.scan_target==i and self.scan>0:
                    text(c,x-42,y+104,f'LINK {self.scan/4:.0%}',12,GOLD)
        wx,wy,label=self.waypoint()
        dx,dy=delta(wx,p['x']),delta(wy,p['y'])
        if math.hypot(dx,dy)>170 and (self.navigate_home or self.campaign.mission[2] not in ('kills','endless')):
            angle=math.atan2(dy,dx)
            x=w/2+math.cos(angle)*min(w*.36,350)
            y=h/2+math.sin(angle)*min(h*.28,210)
            c.save(); c.translate(x,y); c.rotate(angle)
            line(c,[(-9,-6),(0,0),(-9,6)],GOLD,2,.8)
            c.restore()
            text(c,x-65,y+22,f'{label} {math.hypot(dx,dy):.0f}m',10,GOLD,.8)
        for b in self.bullets:
            x,y=screen(b[0],b[1])
            rgb=PINK if b[5] else CYAN
            pts=[(x,y),(x-b[2]*.026,y-b[3]*.026)]
            line(c,pts,rgb,7,.10)
            line(c,pts,rgb,2,.65)
            self.atlas.draw(c, 'shot-red' if b[5] else 'shot-green', x, y, 24, math.atan2(b[3],b[2]))
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
                    text(c,x-60,y-90,'COMMENT SECTION',12,PINK)
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
        text(c,28,54,(f'{self.campaign.stage+1}/5  ' if self.campaign.stage<5 else '')+self.objective_text(),12,(.77,.85,.88),.9)
        text(c,w-170,31,f'{self.campaign.credits:,} CR',12,GOLD,.8)
        for i,(label,fraction,rgb) in enumerate([
                ('HULL',max(0,p['hp'])/self.campaign.max_hull,PINK if p['hp']<self.campaign.max_hull*.3 else CYAN),
                ('FUEL',p['fuel']/100,PURPLE)]):
            y=h-65+i*20
            text(c,28,y+4,label,9,rgb,.7)
            line(c,[(70,y),(215,y)],rgb,4,.12)
            line(c,[(70,y),(70+145*fraction,y)],rgb,4,.85)
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
            text(c,w/2-174,h*.30+76,'W / ARROWS  Fly     LEFT CTRL  Fire',13,CYAN,alpha*.8)
            text(c,w/2-174,h*.30+102,'TAB  Briefing      F2  Difficulty',11,(.7,.82,.87),alpha*.7)
        if self.briefing:
            self.draw_briefing(c,w,h)

    def draw_briefing(self,c,w,h):
        color(c,(.003,.008,.018),.95);c.paint()
        pw=min(700,w-60);x=(w-pw)/2;y=max(25,(h-530)/2)
        heading='CAMPAIGN COMPLETE' if self.campaign.stage==5 else 'MISSION BRIEFING'
        if self.campaign.awaiting_briefing and self.campaign.stage<5:
            heading=f'MISSION {self.campaign.stage} COMPLETE'
        if self.replay_confirm: heading='REPLAY THE STORY?'
        text(c,x,y+32,heading,24,CYAN)
        text(c,x,y+66,self.campaign.mission[0],15,GOLD)
        for i,fragment in enumerate(textwrap.wrap(self.campaign.mission[1],width=int(pw/7.4))):
            text(c,x,y+98+i*20,fragment,12,(.75,.84,.88))
        text(c,x,y+190,self.objective_text(),13,CYAN)
        if self.campaign.awaiting_briefing: return
        if self.campaign.mission[2]=='relays':
            text(c,x,y+214,'Hold within 120m of each mirror for four continuous seconds.',11,CYAN,.8)
        text(c,x,y+255,'F2  '+self.campaign.difficulty.upper()+' DIFFICULTY',14,GOLD)
        desc={'easy':'Reduced damage, fewer enemies, slower volleys. Start here.',
              'normal':'Balanced pressure and moderate protection between hits.',
              'hard':'Stronger enemies, faster volleys, short hit protection.'}[self.campaign.difficulty]
        text(c,x,y+278,desc,11,(.75,.84,.88))
        text(c,x,y+310,'M  Sound: '+('OFF' if self.campaign.muted else 'ON'),12,CYAN)
        if self.sound and self.sound.error:
            text(c,x,y+329,'Audio device unavailable; gameplay continues silently.',10,PINK)
        controls=['W / UP forward    S / DOWN reverse    A / D or LEFT / RIGHT turn',
                  'LEFT CTRL fire    H home waypoint    U workshop at home',
                  'P autopilot    ESC exit    TAB resume']
        for i,fragment in enumerate(controls):
            text(c,x,y+373+i*24,fragment,11,(.75,.84,.88))
        if self.replay_confirm:
            text(c,x,y+465,'ENTER restart from Mission 1, keeping credits and upgrades. ESC cancel.',11,GOLD)
        elif self.campaign.awaiting_briefing:
            label='ENTER launch next mission' if self.campaign.stage<5 else 'ENTER free patrol  /  R replay story (keep upgrades)'
            text(c,x,y+465,label,12,GOLD)
        else:
            text(c,x,y+465,'R replay story (keep upgrades)  /  TAB return',11,CYAN,.7)

    def draw_campaign(self,c,w,h):
        if not self.shop:
            return
        color(c,(0.,.004,.01),.87)
        c.paint()
        pw=min(740,w-48)
        ph=min(480,h-50)
        x,y=(w-pw)/2,(h-ph)/2
        color(c,(.014,.038,.038),1)
        c.rectangle(x,y,pw,ph)
        c.fill()
        line(c,[(x,y),(x+pw,y),(x+pw,y+ph),(x,y+ph)],CYAN,1,.75,True)
        text(c,x+26,y+37,'OMARCHY // RELAY WORKSHOP',20,CYAN)
        text(c,x+26,y+63,'FLIGHT PAUSED  /  FIT YOUR NEXT RELEASE',11,CYAN,.6)
        text(c,x+26,y+91,f'AVAILABLE CREDITS  {self.campaign.credits:06d}',15,GOLD)
        descriptions={
            'weapon':'More barrels, wider spread, then triple-damage plasma.',
            'hull':'Adds 35 maximum hull and repairs the added capacity.',
            'drive':'Improves forward AND reverse thrust by 55 per tier.',
        }
        for i,(key,(name,tiers,costs)) in enumerate(UPGRADES.items()):
            level=self.campaign.levels[key]
            yy=y+131+i*82
            text(c,x+26,yy,f'[{i+1}] {name}',14,CYAN)
            offer='MAXIMUM TIER' if level==3 else f'{tiers[level+1]} / {costs[level]} CR'
            text(c,x+26,yy+22,f'{tiers[level]}  ->  {offer}',12,GOLD if level<3 else CYAN)
            text(c,x+26,yy+42,descriptions[key],10,(.65,.8,.75),.8)
        if self.notice_until>self.t:
            text(c,x+26,y+ph-58,self.notice[:int((pw-52)/7)],11,GOLD)
        text(c,x+26,y+ph-28,'1 / 2 / 3 INSTALL     U / ESC RETURN TO FLIGHT',12,CYAN,.8)

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
    shared.sound=SoundBank(Path.home()/'.cache/omavoid/sfx')
    def quit_all(*_):
        if args.sound_check:
            print('Audio check: '+(shared.sound.error or 'no playback errors'),flush=True)
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
            elif key in {'Return','r','Tab','F2','m','u','h','1','2','3'}:
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
                    elif key=='u':
                        if not self.sim.briefing: self.sim.toggle_shop()
                    elif key=='h':
                        self.sim.take_control()
                        self.sim.navigate_home=not self.sim.navigate_home
                    else: self.sim.purchase(key)
                self.action_held.add(key)
            elif key.lower()=='p':
                if not self.p_held:
                    if self.sim.auto:
                        self.sim.take_control()
                    elif not self.sim.shop and not self.sim.briefing:
                        self.sim.auto=True
                        self.sim.sound.hush()
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
