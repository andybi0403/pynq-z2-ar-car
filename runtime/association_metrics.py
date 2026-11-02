"""Decoded-frame software timing statistics, without an exposure claim."""
import math
import threading
from collections import deque


def distribution(values):
    if not values:return {'count':0,'min':None,'max':None,'mean':None,'p50':None,'p95':None,'p99':None}
    ordered=sorted(values)
    return {'count':len(values),'min':ordered[0],'max':ordered[-1],
            'mean':sum(values)/len(values),
            **{f'p{p}':ordered[round((len(values)-1)*p/100)] for p in (50,95,99)}}


class AssociationMetrics:
    def __init__(self):
        self.lock=threading.Lock();self.frames=0;self.invalid=0
        self.last_id=-1;self.last_received=-1
        self.values={name:deque(maxlen=8192) for name in ('receive_to_submit_ms','snapshot_host_age_ms','clock_uncertainty_ms',
                     'us_age_ms','qei0_age_ms','qei1_age_ms','risk_age_ms')}
        self.aggregates={name:[0,None,None,0.] for name in self.values}
    def observe(self, event):
        with self.lock:
            frame_id,received=event['frame_id'],event['received_host_ns']
            if type(frame_id) is not int or frame_id<=self.last_id or type(received) is not int or received<=self.last_received:
                raise ValueError('frame identifiers and reception times must increase')
            self.last_id,self.last_received=frame_id,received;self.frames+=1
            if not event['valid']:
                self.invalid+=1;return
            values={name:event[name] for name in ('receive_to_submit_ms','snapshot_host_age_ms')}
            values['clock_uncertainty_ms']=event['clock_uncertainty_ns']/1e6
            values.update({name+'_age_ms':value for name,value in event['sample_age_ms'].items()})
            unavailable={name+'_age_ms' for name,value in event['sample_age_ms'].items()
                         if value is None and name in ('us','qei0','qei1','risk')
                         and name.upper()+'_META' in event.get('registers',{})
                         and not event['registers'][name.upper()+'_META'] & 0x80000000}
            if set(values)!=set(self.values) or any(
                    name not in unavailable and (type(v) not in (int,float) or not math.isfinite(v) or v<0)
                    for name,v in values.items()):
                raise ValueError('invalid association timing metrics')
            for name,value in values.items():
                if name in unavailable:continue
                self.values[name].append(value)
                aggregate=self.aggregates[name];aggregate[0]+=1;aggregate[3]+=value
                aggregate[1]=value if aggregate[1] is None else min(aggregate[1],value)
                aggregate[2]=value if aggregate[2] is None else max(aggregate[2],value)
    def summary(self):
        with self.lock:
            summaries={}
            for name,values in self.values.items():
                count,lo,hi,total=self.aggregates[name]
                summaries[name]={**distribution(values),'count':count,'min':lo,'max':hi,'mean':total/count if count else None,
                                 'window_count':len(values)}
            return {'scope':'decoded_frame_reception_to_submission_not_exposure_or_scanout',
                    'distribution_scope':'percentiles last_8192_valid_frames; count/min/max/mean cumulative',
                    'frames':self.frames,'invalid_associations':self.invalid,
                    **summaries}
