"""Original synthesized arcade effects, played through a bounded GStreamer pool."""
import array
import json
import math
import os
import random
import sys
import tempfile
import time
import wave
from pathlib import Path

RATE = 22050
EFFECTS = {'laser':.13, 'twin':.16, 'scatter':.20, 'plasma':.30,
           'hit':.18, 'collision':.25, 'rock_crash':.32, 'metal_crash':.38,
           'ricochet':.12, 'rock_break':.46, 'explosion':.62,
           'pickup':.18, 'upgrade':.45, 'mission':.7, 'dock':.28}
VARIANTS=3
WEAPONS={'laser','twin','scatter','plasma'}

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
                freq=880*math.exp(-t*16)+145
                phase+=math.tau*freq*pitch/RATE
                value=.34*math.sin(phase)+.07*math.sin(phase*2.01)+noise*.035*math.exp(-t*90)
            elif name=='twin':
                # Two detuned oscillators with a delayed second barrel.
                freq=760*math.exp(-t*15)+125
                phase+=math.tau*freq*pitch/RATE
                value=.27*math.sin(phase)+(.18*math.sin(phase*1.075) if t>.022 else 0)+noise*.025
            elif name=='scatter':
                freq=430*math.exp(-t*12)+65
                phase+=math.tau*freq*pitch/RATE
                value=.27*math.sin(phase)+filtered*.55+noise*.10*math.exp(-t*30)
            else:
                freq=260*math.exp(-t*7)+58
                phase+=math.tau*freq*pitch/RATE
                value=.34*math.sin(phase)+.12*math.sin(phase*2+2*math.sin(t*65))+filtered*.16
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
        gain=.20 if name in WEAPONS else .48
        result.append(int(max(-1,min(1,value*envelope))*gain*32767))
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

def write_music(directory):
    """Create a two-minute evolving cyberpunk arcade score in the user cache."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/'omarchy-afterburn.wav'
    if path.exists(): return path
    bpm=122.;beat=60./bpm;eighth=beat/2;bars=64;frames=int(RATE*beat*4*bars)
    # A 64-bar, four-part arc: low-key orbital intro, full pulse, bright run,
    # then a stripped build back into the opening. Modal chords keep it alien.
    chords=((50,57,60,64,69),(46,53,57,62,65),(43,50,53,57,62),(45,52,55,58,64),
            (48,55,59,62,66),(39,46,50,53,57),(41,48,52,55,60),(46,53,57,62,65))
    roots=(38,34,31,33,36,39,41,34)
    motif=((62,65,69,72,69,65,60,65),(60,63,67,70,67,63,58,63),
           (59,62,65,69,65,62,57,62),(57,60,64,67,64,60,55,60))
    def hz(note): return 440.*(2.**((note-69)/12.))
    audio=array.array('h');bass_phase=0.;motif_phase=0.
    for i in range(frames):
        t=i/RATE; beatpos=t/beat; beatno=int(beatpos); bar=beatno//4
        section=bar//16; chord_index=(bar//2+section)%len(chords);chord=chords[chord_index]
        eighthno=int(t/eighth);step=eighthno%8;local8=t-eighthno*eighth
        localbeat=t-beatno*beat;barbeat=beatno%4
        # Soft, wide synth chords slowly breathe beneath the arcade rhythm.
        swell=.68+.32*math.sin(math.tau*t/11.0)
        pad=0.
        for index,note in enumerate(chord[:4]):
            phase=math.tau*hz(note)*t+index*.37
            pad+=(math.sin(phase)+.24*math.sin(phase*2.003))*.009*swell
        # Rounded, syncopated bass pulses anchor the track without a lead squeal.
        bass_hits=(0,3,4,6) if section!=3 else (0,4,6)
        bass_env=math.exp(-local8*9.5) if step in bass_hits else 0.
        bass_note=roots[chord_index]-12
        bass_freq=hz(bass_note)
        bass_phase+=math.tau*bass_freq/RATE
        bass=(math.sin(bass_phase)+.22*math.sin(bass_phase*2.01))*bass_env*(.15 if section else .10)
        # Short, percussive digital notes appear in the middle sections only.
        motif_hits=(0,2,3,6) if section==2 else (0,4) if section==1 else ()
        motif_note=motif[(bar//4)%len(motif)][step]
        motif_freq=hz(motif_note)
        motif_phase+=math.tau*motif_freq/RATE
        motif_env=math.exp(-local8*17.) if step in motif_hits else 0.
        pluck=(math.sin(motif_phase)+.28*math.sin(motif_phase*2.01))*motif_env*(.047 if section==2 else .026)
        barbeat=beatno%4
        kick=0.
        if barbeat in (0,2) and section!=3 or barbeat==0:
            kick=math.sin(math.tau*(72-39*localbeat)*localbeat)*math.exp(-localbeat*25)*(.13 if section else .075)
        snare_gain=(.034 if section in (1,2) else .022 if section==3 else .012)
        snare=(snare_gain*math.sin(math.tau*185*localbeat)+.012*math.sin(math.tau*1550*localbeat))*math.exp(-localbeat*21) if barbeat in (1,3) and section else 0.
        hat_gain=.011 if section in (1,2) else .006 if section==3 else .003
        hat_local=t-eighthno*eighth
        hat=hat_gain*math.sin(math.tau*(1800+120*(step%2))*hat_local)*math.exp(-hat_local*48)
        if section==0 and step not in (0,4): hat=0.
        if section==3 and step in (1,3,5,7): hat=0.
        value=pad+pluck+bass+kick+snare+hat
        # Gentle stereo width comes from the chord bed, avoiding hard panning.
        width=sum(math.sin(math.tau*hz(note)*t+index*.37+.12) for index,note in enumerate(chord[:3]))*.003
        # Give the score enough body to remain audible under weapon and engine cues.
        left=max(-.8,min(.8,(value+width)*2.0));right=max(-.8,min(.8,(value-width)*2.0))
        audio.append(int(left*32767));audio.append(int(right*32767))
    if sys.byteorder!='little': audio.byteswap()
    with wave.open(str(path),'wb') as out:
        out.setparams((2,2,RATE,0,'NONE','not compressed'))
        out.writeframes(audio.tobytes())
    return path

class SoundBank:
    def __init__(self, directory, settings=None):
        self.voices=[];self.last={};self.muted=False;self.error='';self.variants={}
        self.music=None;self.music_uri='';self.music_error='';self.music_volume=.24
        self.settings=Path(settings) if settings else None
        if self.settings:
            try: self.music_volume=max(0.,min(.35,float(json.loads(self.settings.read_text()).get('music_volume',.24))))
            except (OSError,ValueError,TypeError,AttributeError): pass
        try:
            import gi
            gi.require_version('Gst','1.0')
            from gi.repository import Gst
            Gst.init(None)
            self.Gst=Gst
            self.directory=write_effects(Path(directory)/'v3')
            for _ in range(8):
                player=Gst.ElementFactory.make('playbin',None)
                sink=Gst.ElementFactory.make('fakesink',None)
                if player is None or sink is None: raise RuntimeError('Missing audio playback plugin')
                player.set_property('video-sink',sink)
                player.set_property('volume',.45)
                self.voices.append([player,0.])
            try:
                music_path=write_music(Path(directory).parent/'music'/'v4')
                self.music=Gst.ElementFactory.make('playbin',None)
                sink=Gst.ElementFactory.make('fakesink',None)
                if self.music is None or sink is None: raise RuntimeError('Missing music playback plugin')
                self.music.set_property('video-sink',sink)
                self.music_uri=music_path.as_uri()
                self.music.set_property('uri',self.music_uri)
                self.music.set_property('volume',self.music_volume)
                self.music.connect('about-to-finish',lambda player: player.set_property('uri',self.music_uri))
            except Exception as music_exc:
                self.music_error=str(music_exc);self.music=None
        except Exception as exc:
            self.error=str(exc)
            self.close()

    def play(self,name):
        if self.muted or self.error or name not in EFFECTS: return
        now=time.monotonic()
        if name in WEAPONS:
            if now-self.last.get('weapon',-10)<.28: return
            self.last['weapon']=now
        elif now-self.last.get(name,-10)<.12: return
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

    def start_music(self):
        if self.muted or self.music is None: return
        self.music.set_property('volume',self.music_volume)
        self.music.set_state(self.Gst.State.PLAYING)

    def adjust_music(self,delta):
        self.music_volume=max(0.,min(.35,round(self.music_volume+delta,2)))
        if self.music is not None: self.music.set_property('volume',self.music_volume)
        if self.settings:
            self.settings.parent.mkdir(parents=True,exist_ok=True)
            fd,name=tempfile.mkstemp(prefix='.audio-',dir=self.settings.parent)
            try:
                with os.fdopen(fd,'w') as stream: json.dump({'music_volume':self.music_volume},stream)
                os.replace(name,self.settings)
            finally:
                if os.path.exists(name): os.unlink(name)
        return self.music_volume

    def poll(self):
        for player,until in self.voices:
            bus=player.get_bus()
            message=bus.pop_filtered(self.Gst.MessageType.ERROR | self.Gst.MessageType.EOS)
            if message:
                if message.type==self.Gst.MessageType.ERROR:
                    self.error=str(message.parse_error()[0])
                player.set_state(self.Gst.State.NULL)

    def hush(self):
        if self.music is not None: self.music.set_state(self.Gst.State.NULL)
        for voice in self.voices:
            voice[0].set_state(self.Gst.State.NULL)
            voice[1]=0.

    def close(self):
        self.hush()
        if self.music is not None: self.music.set_state(self.Gst.State.NULL)
        self.music=None
        self.voices=[]
