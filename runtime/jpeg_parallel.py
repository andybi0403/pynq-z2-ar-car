"""Lossless restart-aligned partitioning of a baseline 720p 4:2:2 JPEG.

Only the two SOF height fields and the midpoint restart marker are changed.
Horizontal-only chroma upsampling has no cross-stripe dependency. Unsupported
camera formats use the original strict full-frame decoder.
"""
import ctypes as C
from native_video import Codec, writable_pointer


class UnsupportedJPEG(ValueError):
    pass


def split_restart_720(jpeg):
    if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
        raise ValueError('incomplete JPEG')
    i=2;sof=None;restart=None;sos=None
    while i<len(jpeg)-3:
        if jpeg[i]!=255:raise ValueError('invalid JPEG header marker')
        marker=jpeg[i+1]
        if marker==255:i+=1;continue
        if marker in (0,0xd8,0xd9) or 0xd0<=marker<=0xd7:raise ValueError('unexpected header marker')
        length=int.from_bytes(jpeg[i+2:i+4],'big')
        if length<2 or i+2+length>len(jpeg):raise ValueError('invalid JPEG segment length')
        segment=jpeg[i+4:i+2+length]
        if marker in (0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf):
            raise UnsupportedJPEG('only baseline Huffman JPEG is partitioned')
        if marker==0xc0:
            if sof is not None:raise ValueError('duplicate SOF')
            if len(segment)!=15 or segment[:6]!=bytes.fromhex('0802d0050003') or segment[6:]!=bytes.fromhex('012100021101031101'):
                raise UnsupportedJPEG('requires 1280x720 baseline 4:2:2 with standard component order')
            sof=i
        if marker==0xdd:
            if restart is not None or len(segment)!=2:raise ValueError('invalid restart interval')
            restart=int.from_bytes(segment,'big')
        if marker==0xda:
            if segment!=bytes.fromhex('03010002110311003f00'):
                raise UnsupportedJPEG('requires one interleaved baseline scan')
            sos=i+2+length;break
        i+=2+length
    if sof is None or sos is None:raise ValueError('missing JPEG frame/scan')
    # 80 MCUs per row, 90 rows. A half-frame has 3600 MCUs.
    if not restart or 3600%restart or (3600//restart)%8:
        raise UnsupportedJPEG('restart interval cannot partition the frame at row 360')
    boundary_interval=3600//restart
    expected=(7200-1)//restart;markers=[];i=sos
    while i<len(jpeg)-1:
        start=jpeg.find(b'\xff',i)
        if start<0:raise ValueError('missing JPEG end marker')
        i=start
        while i<len(jpeg) and jpeg[i]==255:i+=1
        if i>=len(jpeg):raise ValueError('truncated entropy marker')
        marker=jpeg[i];i+=1
        if marker==0:continue
        if 0xd0<=marker<=0xd7:
            if marker!=0xd0+(len(markers)%8):raise ValueError('restart sequence mismatch')
            markers.append((start,i));continue
        if marker==0xd9:
            if i!=len(jpeg):raise ValueError('trailing JPEG payload')
            break
        raise ValueError('unexpected marker in entropy scan')
    if len(markers)!=expected:raise ValueError('restart marker count mismatch')
    begin,end=markers[boundary_interval-1]
    header=bytearray(jpeg[:sos]);header[sof+5:sof+7]=(360).to_bytes(2,'big')
    header=bytes(header)
    return header+jpeg[sos:begin]+b'\xff\xd9',header+jpeg[end:]


class Parallel720Decoder:
    """Native scan and joined worker; no Python loop over camera entropy."""
    def __init__(self,native,*,decode_dct='islow'):
        self.lib=native.lib
        if not hasattr(self.lib,'wv_decode_parallel'):
            raise RuntimeError('parallel decoder requires the verified native extension')
        self.lib.wv_decode_parallel.argtypes=[C.c_void_p,C.c_char_p,C.c_ulong,C.c_void_p,C.c_ulong,C.c_int]
        self.lib.wv_decode_parallel.restype=C.c_int
        self.codec=Codec(native,decode_dct=decode_dct,reuse_decoder=True)
        self.restart_padding_warnings=0;self.last_mode='native_parallel_or_strict_fallback'

    def decode_into(self,jpeg,buffer):
        owner,pointer=writable_pointer(buffer)
        result=self.lib.wv_decode_parallel(self.codec.handle,jpeg,len(jpeg),pointer,1280*720*4,int(self.codec.decode_dct=='ifast'))
        if result<0:raise RuntimeError(self.lib.wv_codec_error(self.codec.handle).decode(errors='replace'))
        self.restart_padding_warnings=result

    def close(self):
        self.codec.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
