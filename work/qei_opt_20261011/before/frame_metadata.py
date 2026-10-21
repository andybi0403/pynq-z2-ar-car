"""Carry historical display state with its BGR0 frame, independent of MMIO.

18 RGB888 words occupy the first row's reserved OSD border pixels. This is a
decoded reception association, never an exposure timestamp. XOR detects a
single-word corruption; it is not a cryptographic integrity guarantee.
"""
from functools import reduce
from operator import xor
import struct

MAGIC=0xD3A95C
FORMAT=0x010012
WORDS=18


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
    speed_valid=fresh('QEI0') and fresh('QEI1')
    speed=(signed(raw['QEI0_VEL'],32)+signed(raw['QEI1_VEL'],32))//2
    displacement=[];paths=[];odometry_valid=True
    for channel in range(2):
        prefix=f'ODOM{channel}_'
        displacement.append(signed(raw[prefix+'DISP_LO']|(raw[prefix+'DISP_HI']<<32),64))
        paths.append(raw[prefix+'PATH_LO']|(raw[prefix+'PATH_HI']<<32))
        odometry_valid &= raw[prefix+'META']&0xc0000000==0x80000000
    risk=raw['RISK_STATE']
    risk_valid=fresh('RISK')
    flags=((raw['US_DATA']&0xfff) | int(distance_valid)<<12 | int(speed_valid)<<13 |
           int(odometry_valid)<<14 | ((risk>>1)&3 if risk_valid else 3)<<15 |
           (risk&1 if risk_valid else 1)<<17)
    payload=[MAGIC,FORMAT,frame&0xffffff,(epoch<<8)|(frame>>24),flags,
             *chunks(speed&0xffffffff,32),*chunks((sum(displacement)//2)&((1<<64)-1),64),
             *chunks(sum(paths)//2,64),(risk>>16)&0xffff,*chunks(ticks,64)]
    assert len(payload)==WORDS-1
    return payload+[reduce(xor,payload,0xffffff)]


def decode(words):
    if len(words)!=WORDS:raise ValueError('18 metadata words required')
    for word in words:checked(word,24,'metadata word')
    if words[:2]!=[MAGIC,FORMAT] or reduce(xor,words,0)!=0xffffff:
        raise ValueError('metadata magic/version/checksum mismatch')
    if words[4]>>18 or words[6]>>8 or words[9]>>16 or words[12]>>16 or words[13]>>16 or words[16]>>16:
        raise ValueError('metadata reserved bits must be zero')
    def combine(start,count):return sum(words[start+i]<<(24*i) for i in range(count))
    return {'frame_id':words[2]|((words[3]&255)<<24),'epoch':words[3]>>8,
            'distance_mm':words[4]&4095,'distance_valid':bool(words[4]&1<<12),
            'speed_valid':bool(words[4]&1<<13),'odometry_valid':bool(words[4]&1<<14),
            'risk_level':(words[4]>>15)&3,'risk_stop':bool(words[4]&1<<17),
            'speed_q16':signed(combine(5,2),32),'displacement_q16':signed(combine(7,3),64),
            'path_q16':combine(10,3),'risk_reasons':words[13],
            'estimated_frame_pl_ticks64':combine(14,3)}


def prefix_bgr0(words):
    """Validate and pack only the reserved 72 bytes, before DMA allocation."""
    words = list(words)
    decode(words)
    return struct.pack('<18I', *words)


def stamp_bgr0(frame,association,*,width=640,height=480):
    if type(width) is not int or type(height) is not int or width<WORDS or height<1:
        raise ValueError('frame needs at least 18 pixels in its first row')
    if len(frame)!=width*height*4:raise ValueError('BGR0 frame size mismatch')
    output=bytearray(frame)
    output[:WORDS*4] = prefix_bgr0(encode(association))
    return bytes(output)
