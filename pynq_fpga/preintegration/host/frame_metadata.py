"""Carry historical display state with its BGR0 frame, independent of MMIO.

24 RGB888 words occupy the first row's reserved OSD border pixels. This is a
decoded reception association, never an exposure timestamp. XOR detects a
single-word corruption; it is not a cryptographic integrity guarantee.
"""
from functools import reduce
from operator import xor
import struct
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if not (HERE/'qei_quality.py').is_file():
    sys.path.insert(0, str(HERE.parents[1]/'host'))
from qei_quality import raw_fault_reasons
from tactical_state import state_from_registers

MAGIC=0xD3A95C
FORMAT=0x030018
WORDS=24


def checked(value,bits,name):
    if type(value) is not int or not 0<=value<(1<<bits):
        raise ValueError(f'{name} must be uint{bits}')
    return value


def chunks(value,bits):
    return [(value>>shift)&0xffffff for shift in range(0,bits,24)]


def signed(value,bits):
    return value-(1<<bits) if value&(1<<(bits-1)) else value


def encode(association):
    if association.get('valid') is not True:raise ValueError('valid frame association required')
    raw=association['registers'];ages=association['sample_age_ms']
    frame=checked(association['frame_id'],32,'frame id')
    epoch=checked(association['epoch'],16,'snapshot epoch')
    ticks=checked(association['estimated_frame_pl_ticks64'],64,'frame PL time')
    def fresh(name):return bool(raw[name+'_META']&0x80000000) and 0<=ages[name.lower()]<200
    distance_valid=fresh('US') and not ((raw['US_DATA']>>12)&15)
    speed_valid=False;speed=0
    estimate=association.get('clock_anchor',{}).get('display_estimate') or {}
    value=estimate.get('travelled_mm')
    odometry_valid=bool(estimate.get('available') is True and estimate.get('estimated') is True and
                        type(value) in (int,float) and math.isfinite(value) and 0<=value<(1<<47))
    displacement=[0,0]
    path=int(value*65536) if odometry_valid else 0
    paths=[path,path]
    risk=raw['RISK_STATE']
    risk_valid=fresh('RISK')
    flags=((raw['US_DATA']&0xfff) | int(distance_valid)<<12 | int(speed_valid)<<13 |
           int(odometry_valid)<<14 | ((risk>>1)&3 if risk_valid else 3)<<15 |
           (risk&1 if risk_valid else 1)<<17 | 1<<18)
    payload=[MAGIC,FORMAT,frame&0xffffff,(epoch<<8)|(frame>>24),flags,
             *chunks(speed&0xffffffff,32),*chunks((sum(displacement)//2)&((1<<64)-1),64),
             *chunks(sum(paths)//2,64),(risk>>16)&0xffff,*chunks(ticks,64)]
    state=state_from_registers(raw,ticks)
    association['ultrasonic_processing']=state
    trend={'unknown':0,'stable':1,'approaching':2,'receding':3}[state['trend']]
    feature=((state['filtered_mm'] or 0) | int(state['filter_valid'])<<12 | trend<<13 |
             int(state['trend_valid'])<<15 | state['ir_mask']<<16 | int(state['ir_valid'])<<18 |
             int(state['car_locked'])<<19 | int(state['car_valid'])<<20 |
             int(association.get('tactical_enabled',True))<<21)
    payload += [feature,*chunks(state['source_ticks'],32),*chunks(state['support_start_ticks'],32),
                state['sample_sequence'] | state['sample_count']<<16]
    assert len(payload)==WORDS-1
    return payload+[reduce(xor,payload,0xffffff)]


def decode(words):
    if len(words)!=WORDS:raise ValueError('24 metadata words required')
    for word in words:checked(word,24,'metadata word')
    if words[:2]!=[MAGIC,FORMAT] or reduce(xor,words,0)!=0xffffff:
        raise ValueError('metadata magic/version/checksum mismatch')
    if words[4]>>19 or not words[4]&(1<<18) or words[4]&(1<<13) or words[6]>>8 or words[9]>>16 or words[12]>>16 or words[13]>>16 or words[16]>>16:
        raise ValueError('metadata reserved bits must be zero')
    if words[17]>>22 or words[19]>>8 or words[21]>>8 or words[22]>>18:
        raise ValueError('display metadata reserved bits must be zero')
    def combine(start,count):return sum(words[start+i]<<(24*i) for i in range(count))
    return {'frame_id':words[2]|((words[3]&255)<<24),'epoch':words[3]>>8,
            'distance_mm':words[4]&4095,'distance_valid':bool(words[4]&1<<12),
            'speed_valid':bool(words[4]&1<<13),'odometry_valid':bool(words[4]&1<<14),'mileage_estimated':bool(words[4]&1<<18),
            'risk_level':(words[4]>>15)&3,'risk_stop':bool(words[4]&1<<17),
            'speed_q16':signed(combine(5,2),32),'displacement_q16':signed(combine(7,3),64),
            'path_q16':combine(10,3),'risk_reasons':words[13],
            'estimated_frame_pl_ticks64':combine(14,3),
            'filtered_mm':words[17]&4095,'filter_valid':bool(words[17]&1<<12),
            'trend_state':(words[17]>>13)&3,'trend_valid':bool(words[17]&1<<15),
            'ir_mask':(words[17]>>16)&3,'ir_valid':bool(words[17]&1<<18),
            'car_locked':bool(words[17]&1<<19),'car_valid':bool(words[17]&1<<20),
            'tactical_enabled':bool(words[17]&1<<21),
            'filter_latest_ts':combine(18,2),'filter_oldest_ts':combine(20,2),
            'filter_source_seq':words[22]&65535,'filter_sample_count':(words[22]>>16)&3}


def prefix_bgr0(words):
    """Validate and pack only the reserved 96 bytes, before DMA allocation."""
    words = list(words)
    decode(words)
    return struct.pack('<24I', *words)


def stamp_bgr0(frame,association,*,width=640,height=480):
    if type(width) is not int or type(height) is not int or width<WORDS or height<1:
        raise ValueError('frame needs at least 24 pixels in its first row')
    if len(frame)!=width*height*4:raise ValueError('BGR0 frame size mismatch')
    output=bytearray(frame)
    output[:WORDS*4] = prefix_bgr0(encode(association))
    return bytes(output)
