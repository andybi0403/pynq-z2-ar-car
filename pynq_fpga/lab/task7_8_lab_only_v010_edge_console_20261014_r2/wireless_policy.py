"""Explicit output targets with bounded hysteresis; capture stays real 720p30."""
import math
import threading
import time


class VideoPolicy:
    FPS_OPTIONS=(30,25,24,20,15,10,5)
    QUALITY_OPTIONS=(95,85,75,65,55,45,35)
    LEVELS=((30,0),(24,5),(20,10),(15,20),(10,30))
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.lock=threading.RLock()
        self.mode='fixed';self.fps=30;self.quality=75;self.level=0
        self.changed=self.clock();self.good_since=None;self.bad=0;self.next_due=None
        self.reason='fixed_acceptance_720p30_Q75';self.transitions=0
        self.pressure={}
    def configure(self,payload):
        if not isinstance(payload,dict) or set(payload)-{'mode','fps','quality'}:raise ValueError('invalid video settings')
        mode=payload.get('mode');fps=payload.get('fps',30);quality=payload.get('quality',75)
        if mode not in ('fixed','manual','auto'):raise ValueError('mode must be fixed, manual or auto')
        if type(fps) is not int or fps not in self.FPS_OPTIONS:raise ValueError('unsupported output fps')
        if type(quality) is not int or quality not in self.QUALITY_OPTIONS:raise ValueError('unsupported JPEG quality')
        with self.lock:
            self.mode=mode;self.fps=30 if mode=='fixed' else fps;self.quality=75 if mode=='fixed' else quality
            self.level=0;self.bad=0;self.good_since=None;self.next_due=None;self.changed=self.clock()
            self.reason='operator_selected_'+mode
            self.pressure={}
            return self.settings()
    def settings(self):
        with self.lock:
            fps,delta=self.LEVELS[self.level] if self.mode=='auto' else (self.fps,0)
            return {'mode':self.mode,'width':1280,'height':720,'capture_fps':30,
                    'max_fps':self.fps,'max_quality':self.quality,
                    'output_fps':min(self.fps,fps),'jpeg_quality':max(35,self.quality-delta),
                    'level':self.level,'reason':self.reason,'transitions':self.transitions,
                    'fps_options':list(self.FPS_OPTIONS),'quality_options':list(self.QUALITY_OPTIONS),
                    'raw_quality_scope':'camera_native_JPEG; only output_fps is adjustable',
                    'fixed_acceptance':self.mode=='fixed'}
    def admit(self,now=None,force=False):
        with self.lock:
            if force:return True # Same-frame snapshot does not perturb the live cadence.
            now=self.clock() if now is None else now;period=1/self.settings()['output_fps']
            if self.next_due is None:self.next_due=now
            if now+1e-6<self.next_due:return False
            self.next_due=self.next_due+period if now-self.next_due<period else now+period
            return True
    def observe(self,*,cost_ms=None,backlogged=False,receiver=None,source='network'):
        with self.lock:
            if self.mode!='auto':return
            target=self.settings()['output_fps'];congested=bool(backlogged)
            if cost_ms is not None:
                if type(cost_ms) not in (int,float) or not math.isfinite(cost_ms) or cost_ms<0:return
                congested |= cost_ms>900/target
            if receiver is not None and receiver.get('visible',True):
                received=receiver.get('received_fps');drawn=receiver.get('drawn_fps')
                if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 or v>120 for v in (received,drawn)):
                    raise ValueError('invalid receiver frame rates')
                congested |= received<target*.8 or drawn<min(received,target)*.8
            now=self.clock()
            if receiver is not None:source='receiver'
            measured_congestion=congested
            if congested:self.pressure[source]=now+2
            congested=any(until>now for until in self.pressure.values())
            if congested:
                self.good_since=None
                # A cached receiver warning blocks recovery but cannot turn
                # many healthy network observations into new congestion evidence.
                if measured_congestion:self.bad+=1
                if measured_congestion and self.bad>=3 and now-self.changed>=1 and self.level<len(self.LEVELS)-1:
                    self.level+=1;self.changed=now;self.bad=0;self.next_due=None;self.transitions+=1
                    self.reason='measured_congestion_reduce_output'
            else:
                self.bad=0
                if self.good_since is None:self.good_since=now
                if self.level and now-self.good_since>=5 and now-self.changed>=5:
                    self.level-=1;self.changed=now;self.good_since=None;self.next_due=None;self.transitions+=1
                    self.reason='stable_recovery_increase_output'
