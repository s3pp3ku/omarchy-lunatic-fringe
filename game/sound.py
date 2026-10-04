"""Original synthesized arcade effects, played through a bounded GStreamer pool."""
import array
import math
import random
import sys
import time
import wave
from pathlib import Path

RATE = 22050
EFFECTS = {'laser':.13, 'twin':.16, 'scatter':.20, 'plasma':.30,
           'hit':.18, 'collision':.25, 'rock_crash':.32, 'metal_crash':.38,
           'ricochet':.12, 'rock_break':.46, 'explosion':.62,
           'pickup':.18, 'upgrade':.45, 'mission':.7, 'dock':.28}
VARIANTS=3

def samples(name, variant=0):
    rng=random.Random(19+variant*127+sum(map(ord,name)))
    duration=EFFECTS[name]
    result=array.array('h')
    phase=0.; overtone=0.; filtered=0.
    pitch=(1.,.94,1.065)[variant%VARIANTS]
    for i in range(int(RATE*duration)):
        t=i/RATE; u=t/duration
        envelope=min(1,t/.003)*(1-u)**1.5
        noise=rng.uniform(-1,1)
        filtered=filtered*.83+noise*.17
        if name in ('laser','twin','scatter','plasma'):
            if name=='laser':
                # Snappy electrical chirp plus an attack click.
                freq=1550*math.exp(-t*24)+170
                phase+=math.tau*freq*pitch/RATE
                value=.52*math.sin(phase)+.15*math.sin(phase*2.01)+noise*.2*math.exp(-t*90)
            elif name=='twin':
                # Two detuned oscillators with a delayed second barrel.
                freq=1250*math.exp(-t*19)+135
                phase+=math.tau*freq*pitch/RATE
                value=.36*math.sin(phase)+(.29*math.sin(phase*1.075) if t>.022 else 0)+noise*.08
            elif name=='scatter':
                freq=580*math.exp(-t*15)+70
                phase+=math.tau*freq*pitch/RATE
                value=.38*math.sin(phase)+filtered*.9+noise*.25*math.exp(-t*30)
            else:
                freq=320*math.exp(-t*8)+65
                phase+=math.tau*freq*pitch/RATE
                value=.5*math.sin(phase)+.22*math.sin(phase*2+3*math.sin(t*95))+filtered*.3
        elif name in ('explosion','collision','rock_crash','metal_crash','rock_break','hit','ricochet'):
            freq={'explosion':55,'collision':120,'rock_crash':75,'metal_crash':230,
                  'rock_break':60,'hit':190,'ricochet':1650}[name]*pitch
            phase+=math.tau*freq*(1-u*.7)/RATE
            if name=='metal_crash':
                value=.24*math.sin(phase)+.24*math.sin(phase*2.76)+.2*math.sin(phase*4.13)+noise*.2*math.exp(-t*15)
            elif name=='ricochet':
                value=.52*math.sin(phase)+.12*noise
            elif name in ('rock_crash','rock_break'):
                grit=(.4+.6*abs(math.sin(t*(85+variant*11))))
                value=filtered*.8+noise*.38*grit+.26*math.sin(phase)
            else:
                value=.43*math.sin(phase)+filtered*.7+noise*.16
        else:
            notes={'pickup':[880,1320], 'upgrade':[440,554,659,880],
                   'mission':[392,494,587,784,988], 'dock':[523,659,784]}[name]
            phase+=math.tau*notes[min(len(notes)-1,int(u*len(notes)))]*pitch/RATE
            value=math.sin(phase)*.65
        result.append(int(max(-1,min(1,value*envelope))*.48*32767))
    if sys.byteorder!='little': result.byteswap()
    return result.tobytes()

def write_effects(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for name in EFFECTS:
        for variant in range(VARIANTS):
            path=directory/(f'{name}-{variant}.wav')
            if not path.exists():
                with wave.open(str(path),'wb') as out:
                    out.setparams((1,2,RATE,0,'NONE','not compressed'))
                    out.writeframes(samples(name,variant))
    return directory

class SoundBank:
    def __init__(self, directory):
        self.voices=[];self.last={};self.muted=False;self.error='';self.variants={}
        try:
            import gi
            gi.require_version('Gst','1.0')
            from gi.repository import Gst
            Gst.init(None)
            self.Gst=Gst
            self.directory=write_effects(Path(directory)/'v2')
            for _ in range(8):
                player=Gst.ElementFactory.make('playbin',None)
                sink=Gst.ElementFactory.make('fakesink',None)
                if player is None or sink is None: raise RuntimeError('Missing audio playback plugin')
                player.set_property('video-sink',sink)
                player.set_property('volume',.45)
                self.voices.append([player,0.])
        except Exception as exc:
            self.error=str(exc)
            self.close()

    def play(self,name):
        if self.muted or self.error or name not in EFFECTS: return
        now=time.monotonic()
        if now-self.last.get(name,-10)<(.075 if name in ('laser','twin','scatter','plasma') else .12): return
        voice=next((v for v in self.voices if now>=v[1]),None)
        if voice is None:
            if name in ('laser','twin','scatter','plasma','ricochet'): return
            voice=min(self.voices,key=lambda v:v[1]) if self.voices else None
            if voice is None: return
        self.last[name]=now
        player=voice[0]
        player.set_state(self.Gst.State.NULL)
        variant=(self.variants.get(name,-1)+1)%VARIANTS
        self.variants[name]=variant
        player.set_property('uri',(self.directory/f'{name}-{variant}.wav').as_uri())
        if player.set_state(self.Gst.State.PLAYING)==self.Gst.StateChangeReturn.FAILURE:
            self.error='Audio device unavailable'
        voice[1]=now+EFFECTS[name]+.1

    def poll(self):
        for player,until in self.voices:
            bus=player.get_bus()
            message=bus.pop_filtered(self.Gst.MessageType.ERROR | self.Gst.MessageType.EOS)
            if message:
                if message.type==self.Gst.MessageType.ERROR:
                    self.error=str(message.parse_error()[0])
                player.set_state(self.Gst.State.NULL)

    def hush(self):
        for voice in self.voices:
            voice[0].set_state(self.Gst.State.NULL)
            voice[1]=0.

    def close(self):
        self.hush()
        self.voices=[]
