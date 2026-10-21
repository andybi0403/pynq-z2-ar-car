from pathlib import Path
import base64,hashlib,json,sys,time,subprocess
PACKAGE=Path('/home/xilinx/edge_console_v010_20261014_r2')
sys.path.insert(0,str(PACKAGE))
from native_video import NativeLibrary,Camera,CameraWarmingUp,CameraFrameRejected
from overlay_session import DeviceLease
frames=0;errors=[];first=None;last=None;jpeg=None
with DeviceLease():
    with Camera(NativeLibrary(PACKAGE/'native-build/libcar_video.so')) as camera:
        end=time.monotonic()+6
        while time.monotonic()<end:
            try:
                frame,stamp,data,info=camera.read();frames+=1
                if first is None:first=stamp
                last=stamp;jpeg=data
            except (CameraWarmingUp,CameraFrameRejected) as exc:errors.append(str(exc))
assert jpeg is not None,'no actual camera JPEG'
folder=Path('/home/xilinx/stm32_sensors_platform_20261013/uart_live_fix_20261014')
folder.mkdir(parents=True,exist_ok=True);path=folder/'camera_raw.jpg';path.write_bytes(jpeg)
controls=subprocess.run(['v4l2-ctl','--device','/dev/video0','--all'],capture_output=True,text=True,timeout=8)
print(json.dumps({'kind':'CURRENT_CAMERA_RAW_CHECK','hardware':True,'scope':'native camera JPEG, no color conversion or PL overlay',
    'frames':frames,'capture_timestamp_fps':(frames-1)*1e9/(last-first) if frames>1 else None,
    'errors':errors[-10:],'camera_closed':True,'jpeg_bytes':len(jpeg),'jpeg_sha256':hashlib.sha256(jpeg).hexdigest(),
    'controls':controls.stdout,'jpeg_base64':base64.b64encode(jpeg).decode()}))
