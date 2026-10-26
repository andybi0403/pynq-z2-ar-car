"""ctypes.CDLL native calls release the GIL; no raw-frame pipe or Python loop."""
import ctypes as C
import time
import threading
from pathlib import Path

WIDTH, HEIGHT, FPS = 1280, 720, 30
FRAME_BYTES = WIDTH * HEIGHT * 4


class CameraWarmingUp(TimeoutError):
    """No first frame yet; retry this open stream within the startup budget."""

class CameraFrameRejected(RuntimeError):
    """A single unusable frame; the V4L2 device is still open."""
    def __init__(self,reason,frame_id,jpeg=None,diagnostics=None):
        super().__init__(reason)
        self.reason=reason;self.frame_id=frame_id;self.jpeg=jpeg
        self.diagnostics=diagnostics or {}


class FrameInfo(C.Structure):
    _fields_ = [("sequence", C.c_uint32), ("flags", C.c_uint32),
                ("captured_ns", C.c_uint64), ("width", C.c_uint32),
                ("height", C.c_uint32), ("fps_num", C.c_uint32), ("fps_den", C.c_uint32)]


class NativeLibrary:
    def __init__(self, path):
        self.path = Path(path)
        self.lib = C.CDLL(str(self.path.resolve()))
        types = {
            "wv_version": ([], C.c_char_p),
            "wv_codec_open": ([], C.c_void_p),
            "wv_codec_close": ([C.c_void_p], None),
            "wv_codec_error": ([C.c_void_p], C.c_char_p),
            "wv_decode": ([C.c_void_p,C.c_char_p,C.c_ulong,C.c_void_p,C.c_ulong], C.c_int),
            "wv_encode": ([C.c_void_p,C.c_void_p,C.c_ulong,C.c_int,C.POINTER(C.c_void_p),C.POINTER(C.c_ulong)], C.c_int),
            "wv_camera_open": ([C.c_char_p,C.c_void_p,C.c_uint], C.c_void_p),
            "wv_camera_close": ([C.c_void_p], None),
            "wv_camera_read": ([C.c_void_p,C.c_void_p,C.c_uint,C.POINTER(FrameInfo),C.c_int], C.c_int),
        }
        for name,(args,result) in types.items():
            f=getattr(self.lib,name);f.argtypes=args;f.restype=result
        if self.lib.wv_version()!=b"car-video/2;libjpeg-turbo/3.1.2":
            raise RuntimeError("native ABI or pinned codec version mismatch")
        if hasattr(self.lib,'wv_encode_profile'):
            self.lib.wv_encode_profile.argtypes=[C.c_void_p,C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_int,
                                                C.POINTER(C.c_void_p),C.POINTER(C.c_ulong)]
            self.lib.wv_encode_profile.restype=C.c_int
        if hasattr(self.lib,'wv_decode_profile'):
            self.lib.wv_decode_profile.argtypes=[C.c_void_p,C.c_char_p,C.c_ulong,C.c_void_p,C.c_ulong,C.c_int,C.c_int]
            self.lib.wv_decode_profile.restype=C.c_int


def writable_pointer(buffer):
    view=memoryview(buffer).cast('B')
    if not view.contiguous or view.readonly or len(view)!=FRAME_BYTES:
        raise ValueError('writable contiguous 1280x720 BGR0 buffer required')
    owner=(C.c_ubyte*len(view)).from_buffer(view)
    return owner, C.cast(owner,C.c_void_p)


class Codec:
    def __init__(self, native,*,decode_dct='islow',reuse_decoder=False):
        if decode_dct not in ('islow','ifast'):raise ValueError('invalid decode DCT')
        self.lib=native.lib;self.handle=self.lib.wv_codec_open()
        self.decode_dct=decode_dct;self.reuse_decoder=reuse_decoder
        self.restart_padding_warnings=0
        if not self.handle:raise MemoryError('native codec allocation failed')
    def decode_into(self,jpeg,buffer):
        if not self.handle:raise RuntimeError('codec is closed')
        owner,pointer=writable_pointer(buffer)
        if self.reuse_decoder or self.decode_dct!='islow':
            if not hasattr(self.lib,'wv_decode_profile'):raise RuntimeError('decode profile extension requires native rebuild')
            result=self.lib.wv_decode_profile(self.handle,jpeg,len(jpeg),pointer,FRAME_BYTES,
                                              int(self.decode_dct=='ifast'),int(self.reuse_decoder))
        else:result=self.lib.wv_decode(self.handle,jpeg,len(jpeg),pointer,FRAME_BYTES)
        self.restart_padding_warnings=0
        if result<0:
            raise RuntimeError(self.lib.wv_codec_error(self.handle).decode('utf-8',errors='replace'))
        self.restart_padding_warnings=result
    def encode(self,buffer,quality=85,profile='legacy'):
        if not self.handle:raise RuntimeError('codec is closed')
        if type(quality) is not int or not 1<=quality<=100:raise ValueError('quality must be 1..100')
        if profile not in ('legacy','balanced','balanced_fast','detail'):raise ValueError('invalid JPEG profile')
        owner,pointer=writable_pointer(buffer)
        output=C.c_void_p();size=C.c_ulong()
        if profile=='legacy':
            result=self.lib.wv_encode(self.handle,pointer,FRAME_BYTES,quality,C.byref(output),C.byref(size))
        else:
            if not hasattr(self.lib,'wv_encode_profile'):
                raise RuntimeError('native library lacks measured JPEG profile extension; rebuild required')
            result=self.lib.wv_encode_profile(self.handle,pointer,FRAME_BYTES,quality,
                2 if profile in ('balanced','balanced_fast') else 0,int(profile!='balanced_fast'),C.byref(output),C.byref(size))
        if result:
            raise RuntimeError(self.lib.wv_codec_error(self.handle).decode('utf-8',errors='replace'))
        return C.string_at(output,size.value)  # only the compressed JPEG is copied
    def close(self):
        if self.handle:self.lib.wv_codec_close(self.handle);self.handle=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class Camera:
    def __init__(self,native,device='/dev/video0'):
        self.lib=native.lib;self.device=device;self.handle=None
        self.storage=C.create_string_buffer(4*1024*1024)
        self.last_sequence=None;self.frame_id=0;self.dropped=0
        self.generation=0
        self.opened_at=None
        self.lock=threading.Lock()
    def __enter__(self):
        error=C.create_string_buffer(256)
        self.handle=self.lib.wv_camera_open(self.device.encode(),error,len(error))
        if not self.handle:raise RuntimeError(error.value.decode(errors='replace'))
        self.last_sequence=None;self.generation+=1
        self.opened_at=time.monotonic()
        return self
    def read(self):
        info=FrameInfo()
        with self.lock:
            if not self.handle:raise RuntimeError('camera is closed')
            n=self.lib.wv_camera_read(self.handle,self.storage,len(self.storage),C.byref(info),500)
        if n==0:
            if self.last_sequence is None and time.monotonic()-self.opened_at<5:
                raise CameraWarmingUp('camera is awaiting its first frame (startup limit 5s)')
            raise TimeoutError('camera did not deliver a frame in 500ms')
        if n==-2:
            raise CameraFrameRejected('v4l2_bad_frame',self.frame_id+1,
                diagnostics={'capture_sequence':info.sequence,'v4l2_flags':info.flags,'native_read_code':n})
        if n<0:raise RuntimeError('V4L2 device/timestamp read failed: code '+str(n))
        age_ns=time.monotonic_ns()-info.captured_ns
        if age_ns>=500_000_000 and self.last_sequence is None and time.monotonic()-self.opened_at<5:
            raise CameraWarmingUp('discarded stale first frame while camera starts')
        if not 0<=age_ns<500_000_000:
            raise RuntimeError('camera timestamp is stale or in another clock domain')
        if self.last_sequence is not None:
            delta=(info.sequence-self.last_sequence)&0xffffffff
            if delta==0 or delta>=0x80000000:raise RuntimeError('repeated/out-of-order camera sequence')
            self.dropped+=delta-1
        self.last_sequence=info.sequence;self.frame_id+=1
        jpeg=C.string_at(self.storage,n)
        if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
            raise CameraFrameRejected('incomplete_jpeg',self.frame_id,jpeg,
                {'capture_sequence':info.sequence,'v4l2_flags':info.flags,'bytes':n})
        return self.frame_id,info.captured_ns,jpeg,info
    def close(self):
        with self.lock:
            if self.handle:self.lib.wv_camera_close(self.handle);self.handle=None
    def __exit__(self,*args):self.close()
