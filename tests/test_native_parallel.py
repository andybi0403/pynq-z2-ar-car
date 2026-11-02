"""Actual native extension: identical pixels, corruption, context recovery."""
import io,os,sys,unittest
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pynq_fpga/preintegration/host'))
from native_video import NativeLibrary,Codec,FRAME_BYTES
from jpeg_parallel import Parallel720Decoder


class NativeParallelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library=os.environ.get('CAR_NATIVE_LIBRARY')
        if not library:raise unittest.SkipTest('set CAR_NATIVE_LIBRARY to the actual compiled candidate')
        cls.native=NativeLibrary(library)
        y,x=np.indices((720,1280));cls.rgb=np.stack(((x*5+y*11)%256,(x*7+y*3)%256,(x*19+y*13)%256),axis=-1).astype('uint8')

    def jpeg(self,subsampling=1,restart=10):
        output=io.BytesIO();Image.fromarray(self.rgb).save(output,format='JPEG',quality=87,subsampling=subsampling,restart_marker_blocks=restart)
        return output.getvalue()

    def test_parallel_and_unsupported_format_fallback_are_identical(self):
        with Codec(self.native,reuse_decoder=True) as full,Parallel720Decoder(self.native) as parallel:
            expected=bytearray(FRAME_BYTES);actual=bytearray(FRAME_BYTES)
            for subsampling,restart in ((1,10),(1,0),(2,10),(1,7),(0,10)):
                jpeg=self.jpeg(subsampling,restart)
                full.decode_into(jpeg,expected);parallel.decode_into(jpeg,actual)
                self.assertEqual(actual,expected,(subsampling,restart))

    def test_corrupt_restart_rejected_and_next_frame_recovers(self):
        jpeg=self.jpeg();pos=jpeg.index(b'\xff\xd0');bad=jpeg[:pos+1]+b'\xd3'+jpeg[pos+2:]
        with Parallel720Decoder(self.native) as parallel:
            output=bytearray(FRAME_BYTES)
            with self.assertRaises(RuntimeError):parallel.decode_into(bad,output)
            with self.assertRaises(RuntimeError):parallel.decode_into(jpeg[:-3],output)
            parallel.decode_into(jpeg,output)
            with Codec(self.native) as full:
                expected=bytearray(FRAME_BYTES);full.decode_into(jpeg,expected)
            self.assertEqual(output,expected)

    def test_native_stripe_failure_does_not_reuse_partial_output_as_success(self):
        jpeg=self.jpeg();sos=jpeg.index(b'\xff\xda');scan=sos+2+int.from_bytes(jpeg[sos+2:sos+4],'big')
        restart=jpeg.index(b'\xff\xd0',scan)
        bad=jpeg[:scan]+b'\x00'+jpeg[restart:]
        with Parallel720Decoder(self.native) as parallel:
            output=bytearray(FRAME_BYTES)
            with self.assertRaises(RuntimeError):parallel.decode_into(bad,output)
            parallel.decode_into(jpeg,output)

    def test_merged_chroma_retains_full_resolution_luminance_detail(self):
        y,x=np.indices((720,1280));gray=(((x//2+y//2)%2)*180+30).astype('uint8')
        output=io.BytesIO();Image.fromarray(np.repeat(gray[:,:,None],3,axis=2)).save(output,format='JPEG',quality=90,subsampling=1)
        jpeg=output.getvalue();expected=bytearray(FRAME_BYTES);actual=bytearray(FRAME_BYTES)
        with Codec(self.native,reuse_decoder=True) as strict,Codec(self.native,reuse_decoder=True,decode_upsampling='merged') as merged:
            strict.decode_into(jpeg,expected);merged.decode_into(jpeg,actual)
            self.assertEqual(actual,expected)

    def test_reused_merged_context_restores_strict_profile_and_rejects_corruption(self):
        jpeg=self.jpeg();expected=bytearray(FRAME_BYTES);actual=bytearray(FRAME_BYTES)
        with Codec(self.native,reuse_decoder=True) as strict,Codec(self.native,reuse_decoder=True,decode_upsampling='merged') as merged:
            strict.decode_into(jpeg,expected);merged.decode_into(jpeg,actual)
            self.assertNotEqual(actual,expected)
            merged.decode_flags=0;merged.decode_into(jpeg,actual);self.assertEqual(actual,expected)
            merged.decode_flags=2
            with self.assertRaises(RuntimeError):merged.decode_into(jpeg[:-20],actual)
            merged.decode_into(jpeg,actual)

if __name__=='__main__':unittest.main()
