import sys
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parents[1]/"game"))
import json
import math
import tempfile
import unittest
from pathlib import Path
import cairo
from campaign import Campaign
from fringe import Simulation, segment_hit, load_fire_keys
from sound import samples, EFFECTS, RATE

class FlightTests(unittest.TestCase):
    def test_reverse_brakes_then_backs_away_while_firing(self):
        s=Simulation(1)
        s.take_control()
        s.player.update(x=0.,y=-300.,vx=300.,vy=0.,a=0.)
        s.press_control('Down');s.press_control('Control_L')
        for _ in range(30): s.step(1/60)
        self.assertLess(s.player['vx'],300)
        for _ in range(150): s.step(1/60)
        self.assertLess(s.player['vx'],-200)
        self.assertEqual(s.player['a'],0.)
        self.assertTrue(any(not b[5] and b[2]>500 for b in s.bullets))
        self.assertFalse(s.press_control('b'))

    def test_opposing_controls_cancel_acceleration(self):
        s=Simulation(2);s.take_control()
        s.player.update(vx=0.,vy=0.)
        s.press_control('Up');s.press_control('s');s.step(1/60)
        self.assertEqual(s.player['vx'],0.)
        self.assertEqual(s.player['vy'],0.)

    def test_weapon_tiers_and_hull(self):
        s=Simulation(3);s.take_control();s.shop=True
        s.campaign.credits=20000
        for tier,count in enumerate([1,2,3,3]):
            s.bullets.clear();s.fire(s.player)
            self.assertEqual(len(s.bullets),count)
            self.assertEqual(s.bullets[0][6],3 if tier==3 else 1)
            if tier<3:s.purchase('1')
        before=s.campaign.credits;s.purchase('1')
        self.assertEqual(before,s.campaign.credits)
        s.purchase('2')
        self.assertEqual(s.campaign.max_hull,135)
        self.assertEqual(s.player['hp'],135)
        before=s.t;s.step(2)
        self.assertEqual(s.t,before)

    def test_campaign_through_real_world_events_and_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.json'
            s=Simulation(5,save_path=path)
            s.step(.01);s.persist()
            self.assertFalse(path.exists(), 'attract mode must not save')
            s.take_control();s.respawn_shield=999;s.rocks=[]
            for _ in range(5):
                s.enemies[0]['hp']=0;s.step(1/120)
            self.assertEqual(s.campaign.stage,1)
            self.assertEqual(s.campaign.credits,700)
            self.assertTrue(s.campaign.awaiting_briefing)
            self.assertEqual(s.salvage,[])
            s.launch_chapter()
            # Mission 2 requires newly defeated ships and recovered packages.
            for _ in range(4):
                e=s.enemies[0];e['hp']=0
                s.step(1/120)
                core=s.salvage[-1]
                s.player.update(x=core[0],y=core[1],vx=0.,vy=0.)
                s.step(1/120)
            self.assertEqual(s.campaign.stage,2)
            s.launch_chapter()
            for xy in s.beacons:
                s.player.update(x=xy[0],y=xy[1],vx=0.,vy=0.)
                for _ in range(485):s.step(1/120)
            self.assertEqual(s.campaign.stage,3)
            s.launch_chapter()
            s.step(1/120)
            bosses=[e for e in s.enemies if e['boss']]
            self.assertEqual(len(bosses),1)
            bosses[0]['hp']=0;s.step(1/120)
            self.assertEqual(s.campaign.stage,4)
            s.launch_chapter()
            s.player.update(x=0.,y=0.,vx=0.,vy=0.)
            s.step(1/120)
            self.assertEqual(s.campaign.stage,4)
            s.objective_event('home')
            self.assertEqual(s.campaign.stage,5)
            restored=Campaign(path)
            self.assertEqual(restored.stage,5)
            self.assertEqual(len(restored.relays),3)
            self.assertEqual(restored.credits,s.campaign.credits)

    def test_shop_requires_home_and_save_resumes_upgrades(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.json'
            s=Simulation(6,save_path=path);s.take_control()
            s.player.update(x=1000.,y=1000.)
            s.toggle_shop();self.assertFalse(s.shop)
            s.player.update(x=0.,y=0.);s.toggle_shop()
            self.assertTrue(s.shop)
            s.campaign.credits=1000;s.purchase('1')
            restored=Simulation(7,save_path=path);restored.take_control()
            self.assertEqual(restored.campaign.levels['weapon'],1)
            self.assertEqual(restored.campaign.credits,650)

    def test_bad_save_and_insufficient_funds(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.json';path.write_text('{bad')
            c=Campaign(path)
            self.assertTrue(c.error)
            c.buy('weapon')
            self.assertEqual(c.levels['weapon'],0)
            self.assertEqual(c.credits,0)

    def test_all_mission_and_shop_screens_render(self):
        s=Simulation(8);s.take_control()
        for stage in range(6):
            s.campaign.stage=stage
            for size in [(1200,750),(1600,900)]:
                surface=cairo.ImageSurface(cairo.FORMAT_RGB24,*size)
                s.draw(cairo.Context(surface),*size)
        s.shop=True
        surface=cairo.ImageSurface(cairo.FORMAT_RGB24,1200,750)
        s.draw(cairo.Context(surface),1200,750)
        surface.write_to_png('/tmp/omavoid-workshop.png')

class PolishTests(unittest.TestCase):
    def pilot(self):
        s=Simulation(101);s.take_control()
        s.rocks=[];s.enemies=[]
        s.player.update(x=500.,y=500.,vx=0.,vy=0.,a=0.)
        s.respawn_shield=0
        return s

    def test_asteroid_bounce_and_hit_grace(self):
        s=self.pilot();s.rocks=[(550.,500.,40.,[1.]*9)]
        s.player['vx']=250
        hp=s.player['hp'];s.resolve_contacts()
        self.assertLess(s.player['vx'],0)
        self.assertLess(s.player['hp'],hp)
        self.assertGreaterEqual(math.hypot(s.player['x']-550,s.player['y']-500),40*.82+21)
        hp=s.player['hp'];s.damage_player(40)
        self.assertEqual(s.player['hp'],hp)

    def test_enemy_collision(self):
        s=self.pilot();s.spawn()
        e=s.enemies[0];e.update(x=520.,y=500.)
        hp=e['hp'];s.resolve_contacts()
        self.assertLess(e['hp'],hp)
        self.assertGreater(math.hypot(s.player['x']-520,s.player['y']-500),45)

    def test_asteroid_blocks_projectile_then_breaks(self):
        s=self.pilot();s.rocks=[(550.,500.,20.,[1.]*9)]
        s.spawn();e=s.enemies[0];e.update(x=620.,y=500.)
        hp=e['hp']
        s.bullets=[[500.,500.,3000.,0.,1.,False,5]]
        s.step(.05)
        self.assertIn(0,s.destroyed_rocks)
        self.assertEqual(e['hp'],hp)
        self.assertFalse(s.bullets)

    def test_swept_hit_across_world_seam(self):
        hit=segment_hit(2590,0,-2580,0,-2590,0,3)
        self.assertIsNotNone(hit)
        self.assertIsNone(segment_hit(0,0,100,0,50,100,4))

    def test_difficulty_damage_and_backward_compatible_save(self):
        s=self.pilot();damage=[]
        for difficulty in ('easy','normal','hard'):
            s.campaign.difficulty=difficulty;s.hit_grace=0;s.player['hp']=100
            s.damage_player(10);damage.append(100-s.player['hp'])
        self.assertLess(damage[0],damage[1]);self.assertLess(damage[1],damage[2])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.json'
            c=Campaign(path);c.save()
            data=json.loads(path.read_text());data.pop('difficulty');data.pop('muted')
            path.write_text(json.dumps(data));c=Campaign(path)
            self.assertEqual(c.difficulty,'easy')
            c.difficulty='hard';c.muted=True;c.save()
            restored=Campaign(path)
            self.assertEqual(restored.difficulty,'hard');self.assertTrue(restored.muted)

    def test_sound_events_silent_demo_and_manual_shot(self):
        class Recorder:
            def __init__(self):self.events=[];self.muted=False
            def play(self,event):self.events.append(event)
        s=Simulation(11);s.sound=Recorder();s.fire(s.player)
        self.assertEqual(s.sound.events,[])
        s.take_control();s.fire(s.player)
        self.assertEqual(s.sound.events,['laser'])

    def test_effects_are_finite_bounded_audio(self):
        import array
        for name,duration in EFFECTS.items():
            data=samples(name)
            self.assertEqual(len(data),int(RATE*duration)*2)
            values=array.array('h');values.frombytes(data)
            self.assertGreater(max(values),0)
            self.assertLess(max(abs(v) for v in values),32767)

    def test_intro_and_briefing_render_pause(self):
        s=Simulation(12)
        sf=cairo.ImageSurface(cairo.FORMAT_RGB24,1200,750)
        s.draw(cairo.Context(sf),1200,750)
        sf.write_to_png('/tmp/omavoid-intro.png')
        s.take_control();s.briefing=True
        now=s.t;s.step(.1);self.assertEqual(s.t,now)
        s.draw(cairo.Context(sf),1200,750)
        sf.write_to_png('/tmp/omavoid-briefing.png')

class ChapterTests(unittest.TestCase):
    def test_chapter_pauses_and_resumes_after_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.json'
            s=Simulation(4,save_path=path);s.take_control()
            for _ in range(5):s.objective_event('kills')
            self.assertTrue(s.briefing)
            before=s.t;s.step(5);self.assertEqual(before,s.t)
            s.objective_event('salvage');self.assertEqual(s.campaign.progress,0)
            restored=Simulation(5,save_path=path);restored.take_control()
            self.assertTrue(restored.briefing)
            restored.launch_chapter()
            self.assertFalse(restored.campaign.awaiting_briefing)
            restored.objective_event('salvage')
            self.assertEqual(restored.campaign.progress,1)

    def test_replay_retains_equipment_and_money(self):
        s=Simulation(6);s.take_control()
        s.campaign.stage=5;s.campaign.credits=900;s.campaign.levels['weapon']=2
        s.campaign.relays=[0,1,2]
        s.replay_confirm=True;s.launch_chapter()
        self.assertEqual(s.campaign.stage,0)
        self.assertEqual(s.campaign.credits,900)
        self.assertEqual(s.campaign.levels['weapon'],2)
        self.assertEqual(s.campaign.relays,[])

    def test_control_binding_can_be_configured(self):
        s=Simulation(7);s.take_control()
        self.assertTrue(s.press_control('Control_L'))
        self.assertFalse(s.press_control('space'))
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'controls.json';p.write_text('{"fire":["Control_L","space"]}')
            self.assertEqual(load_fire_keys(p),{'Control_L','space'})
            p.write_text('{"fire":[]}')
            self.assertEqual(load_fire_keys(p),{'Control_L'})

    def test_weapon_and_collision_sound_variants(self):
        import hashlib
        for name in ('laser','twin','scatter','plasma','rock_crash','metal_crash'):
            hashes={hashlib.sha256(samples(name,variant)).hexdigest() for variant in range(3)}
            self.assertEqual(len(hashes),3)
        hashes={hashlib.sha256(samples(name)).hexdigest() for name in ('laser','twin','scatter','plasma')}
        self.assertEqual(len(hashes),4)

if __name__=='__main__': unittest.main()
