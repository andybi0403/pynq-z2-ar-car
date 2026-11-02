from pathlib import Path
import unittest,subprocess,sys,os,json
ROOT=Path(__file__).resolve().parents[1]
class VideoProfilesTests(unittest.TestCase):
 def test_native_roundtrip_and_wrong_dimensions_for_both_profiles(self):
  for profile,width,height in [('wireless720',1280,720),('wireless360',640,360)]:
   code='''import sys,io,json
from pathlib import Path
from PIL import Image
r=Path(sys.argv[1]);sys.path.insert(0,str(r/'pynq_fpga/preintegration/host'))
from native_video import NativeLibrary,Codec,FRAME_BYTES,WIDTH,HEIGHT
native=NativeLibrary(r/'pynq_fpga/fpga/build/wireless_native_host_v2/Release/car_video.dll')
buffer=bytearray(FRAME_BYTES)
s=io.BytesIO();Image.new('RGB',(WIDTH,HEIGHT),(20,120,210)).save(s,format='JPEG')
with Codec(native) as codec:
 codec.decode_into(s.getvalue(),buffer)
 jpeg=codec.encode(buffer,quality=65,profile='balanced')
 im=Image.open(io.BytesIO(jpeg));assert im.size==(WIDTH,HEIGHT)
 assert all(abs(a-b)<8 for a,b in zip(im.getpixel((100,100)),(20,120,210)))
 wrong=io.BytesIO();Image.new('RGB',(320,240)).save(wrong,format='JPEG')
 try:codec.decode_into(wrong.getvalue(),buffer)
 except RuntimeError:pass
 else:raise AssertionError('wrong size accepted')
 codec.decode_into(s.getvalue(),buffer)
 try:codec.encode(buffer[:-1])
 except ValueError:pass
 else:raise AssertionError('short buffer accepted')
print(json.dumps({'width':WIDTH,'height':HEIGHT,'bytes':FRAME_BYTES}))
'''
   env={**os.environ,'PYNQ_VIDEO_PROFILE':profile}
   p=subprocess.run([sys.executable,'-c',code,str(ROOT)],env=env,capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['bytes'],width*height*4)
 def test_unknown_profile_fails_before_hardware(self):
  env={**os.environ,'PYNQ_VIDEO_PROFILE':'invalid'}
  p=subprocess.run([sys.executable,'-c',"import sys;sys.path.insert(0,sys.argv[1]);import video_profile",str(ROOT/'pynq_fpga/preintegration/host')],env=env,capture_output=True,text=True)
  self.assertNotEqual(p.returncode,0);self.assertIn('unsupported video profile',p.stderr)
if __name__=='__main__':unittest.main()
