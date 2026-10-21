"""Bounded video publication and clock-qualified intents; never touches MMIO."""
from collections import deque
from dataclasses import dataclass
import copy
import math
import secrets
import threading
import time
from wireless_policy import VideoPolicy


@dataclass(frozen=True)
class EncodedFrame:
    frame_id: int
    captured_ns: int
    raw: bytes
    processed: bytes | None
    historical: dict


class VideoHub:
    def __init__(self):
        self.condition=threading.Condition();self.latest=None;self.pair=None
        self.view='processed';self.snapshot_requested=False;self.closed=False
        self.error=None;self.fault_since_ns=0;self.counts={'captured':0,'processed':0,'encoded':0,'sent':0,
                                    'camera_dropped':0,'decode_dropped':0,'encode_dropped':0,'published':0}
        self.start_ns=time.monotonic_ns();self.times={};self.bytes_sent=0
        self.rate_events={};self.cpu_sample=None
        self.first_event_ns={}
        self.minute_counts={};self.cpu_totals=[0.,0.,0.,0.]
        self.policy=VideoPolicy()
    def set_view(self,view):
        if view not in ('raw','processed'):raise ValueError('invalid video view')
        with self.condition:self.view=view
    def needs_encode(self):
        with self.condition:return self.view=='processed' or self.snapshot_requested
    def observe(self,name,duration_ms=None,amount=1):
        with self.condition:
            self.counts[name]=self.counts.get(name,0)+amount
            if name in ('captured','processed','encoded','published','sent'):
                events=self.rate_events.setdefault(name,deque(maxlen=7200));now=time.monotonic_ns()
                if amount>0:self.first_event_ns.setdefault(name,now)
                for _ in range(amount):events.append(now)
                minute=int((now-self.start_ns)//60_000_000_000)
                bucket=self.minute_counts.setdefault(minute,{'captured':0,'processed':0,'encoded':0,'sent':0})
                bucket[name]=bucket.get(name,0)+amount
                for old in tuple(self.minute_counts):
                    if old<minute-119:del self.minute_counts[old]
            if duration_ms is not None:self.times.setdefault(name,deque(maxlen=4096)).append(duration_ms)
    def publish(self,frame):
        if not frame.raw.startswith(b'\xff\xd8') or (frame.processed is not None and not frame.processed.startswith(b'\xff\xd8')):
            raise ValueError('invalid raw JPEG')
        with self.condition:
            if self.closed:
                return False
            if frame.captured_ns<=self.fault_since_ns:
                self.counts['stale_publication_dropped']=self.counts.get('stale_publication_dropped',0)+1
                self.counts['fault_boundary_publication_rejected']=self.counts.get('fault_boundary_publication_rejected',0)+1
                return False
            if self.latest is not None and frame.frame_id<=self.latest.frame_id:
                raise ValueError('repeated or out-of-order frame publication')
            # Atomically preserve both images and the SAME historical identity.
            frame=EncodedFrame(frame.frame_id,frame.captured_ns,frame.raw,frame.processed,copy.deepcopy(frame.historical))
            self.latest=frame
            self.error=None
            if frame.processed is not None:
                self.pair=frame;self.snapshot_requested=False
            self.condition.notify_all()
            return True
    def set_error(self,error):
        with self.condition:
            if self.closed:return
            self.fault_since_ns=time.monotonic_ns()
            self.error=str(error);self.latest=None;self.pair=None
            self.condition.notify_all()
    def next(self,view,after,timeout=.5):
        deadline=time.monotonic()+timeout
        with self.condition:
            while not self.closed:
                f=self.latest
                if f is not None and f.frame_id>after and (view=='raw' or f.processed is not None):return f
                remaining=deadline-time.monotonic()
                if remaining<=0:return None
                self.condition.wait(remaining)
            return None
    def snapshot(self,timeout=1):
        deadline=time.monotonic()+timeout
        with self.condition:
            # Always freeze a newly completed pair, even after switching to raw.
            previous=self.latest.frame_id if self.latest else -1
            self.snapshot_requested=True
            while not self.closed:
                if self.pair is not None and self.pair.frame_id>previous:return self.pair
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('same-frame PL snapshot unavailable')
                self.condition.wait(remaining)
            raise RuntimeError(self.error or 'video stopped')
    def close(self,error=None):
        with self.condition:
            if self.closed:
                # A later cleanup failure may add the first terminal reason;
                # a repeated normal close must never erase an existing one.
                if error and self.error is None:self.error=error
                return
            self.closed=True;self.error=error;self.snapshot_requested=False
            self.condition.notify_all()
    def record_cpu(self,sample):
        with self.condition:
            self.cpu_sample=sample;duration=sample['interval_s']
            self.cpu_totals[0]+=sample['two_core_percent']*duration;self.cpu_totals[1]+=duration
            if sample['system_total_percent'] is not None:
                self.cpu_totals[2]+=sample['system_total_percent']*duration;self.cpu_totals[3]+=duration
    def stats(self):
        with self.condition:
            seconds=max(.001,(time.monotonic_ns()-self.start_ns)/1e9)
            percentiles={}
            for name,values in self.times.items():
                ordered=sorted(values)
                percentiles[name]={f'p{p}_ms':ordered[min(len(ordered)-1,math.ceil(len(ordered)*p/100)-1)] for p in (50,95,99)}
            return {'width':1280,'height':720,'nominal_fps':30,'jpeg_quality':self.policy.settings()['jpeg_quality'],
                    'output_policy':self.policy.settings(),
                    'subsampling':self.latest.historical.get('jpeg_subsampling','unknown') if self.latest else 'unknown',
                    'jpeg_profile':self.latest.historical.get('jpeg_profile','unknown') if self.latest else 'unknown',
                    'counts':dict(self.counts),
                    'fps_since_start':{k:self.counts[k]/seconds for k in ('captured','processed','encoded','published','sent')},
                    'first_event_ns':dict(self.first_event_ns),
                    'active_fps':{name:self.counts[name]/max(.001,(time.monotonic_ns()-stamp)/1e9)
                                  for name,stamp in self.first_event_ns.items()},
                    'active_fps_scope':'per_stage_first_event_to_now; includes recovery; not browser FPS',
                    'latency':percentiles,'view':self.view,'error':self.error,
                    'rolling_60s_fps':{name:sum(t>=time.monotonic_ns()-60_000_000_000 for t in stamps)/min(seconds,60)
                                      for name,stamps in self.rate_events.items()},
                    'process_cpu':self.cpu_sample,
                    'average_process_two_core_percent':self.cpu_totals[0]/self.cpu_totals[1] if self.cpu_totals[1] else None,
                    'average_system_total_percent':self.cpu_totals[2]/self.cpu_totals[3] if self.cpu_totals[3] else None,
                    'full_minute_fps':{str(m):{name:self.minute_counts.get(m,{}).get(name,0)/60
                                             for name in ('captured','processed','encoded','published','sent')}
                                       for m in range(max(0,int(seconds//60)-119),int(seconds//60))},
                    'minute_history_scope':'last_120_full_minutes_since_service_start; no warmup exclusion',
                    'browser_rtt_scope':'client_reported_ack_roundtrip_not_wheel_stop',
                    'sent_payload_mbps':self.bytes_sent*8/seconds/1e6,
                    'hardware_performance_validated':False}


class IntentMailbox:
    """One latest intent plus a priority STOP, consumed only by control owner."""
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.lock=threading.Lock();self.pending=None;self.stop_pending=False
        self.sequence=0
    def submit(self,left,right,age_upper_ms=0):
        with self.lock:
            now=self.clock()
            self.sequence+=1;self.pending=(self.sequence,left,right,now,now+(100-age_upper_ms)/1000)
    def stop(self):
        with self.lock:self.pending=None;self.stop_pending=True
    def consume(self):
        with self.lock:
            if self.stop_pending:
                self.stop_pending=False;self.pending=None;return 'stop',None
            value=self.pending;self.pending=None
            if value is None:return None,None
            if self.clock()>=value[4]:return 'stop',None
            return 'intent',value[:3]


class ControlGate:
    """One WS owner. Four-timestamp sync bounds uncertainty; old packets fail shut."""
    def __init__(self,mailbox,*,clock=time.monotonic,motion_allowed=False):
        self.mailbox=mailbox;self.clock=clock;self.motion_allowed=motion_allowed
        self.lock=threading.RLock();self.owner=None;self.sessions={};self.rejected=0
        self.last_event={'reason':'startup_no_owner','server_ms':self.clock()*1000}
    def revoke(self,reason):
        with self.lock:
            self.owner=None;self.mailbox.stop()
            self.last_event={'reason':str(reason),'server_ms':self.clock()*1000}
    def status(self):
        with self.lock:return {'connected':len(self.sessions),'owned':self.owner is not None,
            'rejected':self.rejected,'motion_allowed':self.motion_allowed,'last_event':dict(self.last_event)}
    def connect(self,key):
        with self.lock:
            if len(self.sessions)>=8:raise ValueError('too many control connections')
            self.sessions[key]={'seq':-1,'sync':None,'challenge':None}
    def challenge(self,key):
        with self.lock:
            nonce=secrets.token_hex(12);stamp=self.clock()*1000
            self.sessions[key]['challenge']=(nonce,stamp)
            return {'type':'sync','nonce':nonce,'server_ms':stamp}
    def disconnect(self,key):
        with self.lock:
            if self.owner==key:self.revoke('controller_disconnected')
            self.sessions.pop(key,None)
    def maintain(self):
        with self.lock:
            if self.owner is None:return
            s=self.sessions.get(self.owner);now=self.clock()*1000
            if (s is None or s['sync'] is None or now-s['sync'][2]>3000 or
                    now-s.get('last_intent_ms',-math.inf)>=250):
                self.revoke('clock_sync_expired' if s is None or s['sync'] is None or now-s['sync'][2]>3000 else 'intent_lease_expired_250ms')
    @staticmethod
    def number(value):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError('finite timestamp required')
        return float(value)
    def message(self,key,payload):
        with self.lock:
            if not isinstance(payload,dict) or key not in self.sessions:raise ValueError('invalid session/message')
            s=self.sessions[key];kind=payload.get('type');now=self.clock()*1000
            try:
                if kind=='sync':
                    challenge=s['challenge']
                    if challenge is None or payload.get('nonce')!=challenge[0]:raise ValueError('sync nonce mismatch')
                    c2=self.number(payload.get('received_ms'));c3=self.number(payload.get('sent_ms'))
                    s1=challenge[1];rtt=now-s1-(c3-c2)
                    if not 0<=c3-c2<=50 or not 0<=rtt<=50:raise ValueError('clock uncertainty exceeds limit')
                    offset=((s1-c2)+(now-c3))/2
                    old=s['sync']
                    if old is not None and abs(offset-old[0])>old[1]+rtt/2+5:raise ValueError('client clock jumped')
                    s['sync']=(offset,rtt/2,now);s['challenge']=None
                    return {'type':'synced','uncertainty_ms':rtt/2}
                if kind=='stop':
                    self.revoke('operator_stop');return {'type':'ack','stopped':True}
                sync=s['sync']
                if sync is None or now-sync[2]>3000:raise ValueError('clock sync expired')
                if kind=='claim':
                    age=now-(self.number(payload.get('client_ms'))+sync[0])
                    if age+sync[1]>100 or age-sync[1]<-5:raise ValueError('stale/future claim')
                    if self.owner not in (None,key):raise ValueError('control is owned by another connection')
                    self.mailbox.stop();self.owner=key;s['last_intent_ms']=now
                    self.last_event={'reason':'controller_claimed','server_ms':now}
                    return {'type':'claimed','motion_allowed':self.motion_allowed}
                self.maintain()
                if kind!='intent' or self.owner!=key:raise ValueError('claim control first')
                seq=payload.get('seq');left=payload.get('left');right=payload.get('right')
                if any(type(x) is not int for x in (seq,left,right)):raise ValueError('integer intent fields required')
                if seq<=s['seq']:raise ValueError('replayed/out-of-order intent')
                if not -2400<=left<=2400 or not -2400<=right<=2400:raise ValueError('PWM out of range')
                age=now-(self.number(payload.get('client_ms'))+sync[0])
                if age+sync[1]>100 or age-sync[1]<-5:raise ValueError('stale/future intent')
                if not self.motion_allowed and (left or right):raise ValueError('LAB_ONLY prohibits nonzero PWM')
                s['seq']=seq;s['last_intent_ms']=now;self.mailbox.submit(left,right,max(0,age+sync[1]))
                return {'type':'ack','seq':seq,'received_ms':now}
            except (ValueError,TypeError) as exc:
                self.rejected+=1
                if self.owner==key:self.revoke('invalid_intent: '+str(exc))
                raise
