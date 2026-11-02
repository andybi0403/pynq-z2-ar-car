"""Independent JPEG decoder checks for restart-aligned splitting."""
import io
from pathlib import Path
import sys
import unittest
import numpy as np
from PIL import Image
HOST=Path(__file__).resolve().parents[1]/'pynq_fpga/preintegration/host'
sys.path.insert(0,str(HOST))
from jpeg_parallel import split_restart_720,UnsupportedJPEG


class RestartPartitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        y,x=np.indices((720,1280))
        cls.rgb=np.stack(((x*7+y*13)%256,(x*3+y*19)%256,(x*11+y*5)%256),axis=-1).astype('uint8')
        out=io.BytesIO();Image.fromarray(cls.rgb).save(out,format='JPEG',quality=90,subsampling=1,restart_marker_blocks=10)
        cls.jpeg=out.getvalue()

    def test_entire_720_picture_is_pixel_identical(self):
        top,bottom=split_restart_720(self.jpeg)
        expected=np.asarray(Image.open(io.BytesIO(self.jpeg)).convert('RGB'))
        actual=np.concatenate([np.asarray(Image.open(io.BytesIO(p)).convert('RGB')) for p in (top,bottom)])
        np.testing.assert_array_equal(actual,expected)

    def test_missing_restart_and_corrupt_sequence_rejected(self):
        marker=self.jpeg.index(b'\xff\xd0')
        with self.assertRaisesRegex(ValueError,'sequence'):
            split_restart_720(self.jpeg[:marker+1]+b'\xd2'+self.jpeg[marker+2:])
        with self.assertRaises(ValueError):split_restart_720(self.jpeg[:-2])

    def test_unsupported_chroma_and_no_restart_use_fallback(self):
        for subsampling,restart in ((2,10),(1,0)):
            out=io.BytesIO();Image.fromarray(self.rgb).save(out,format='JPEG',subsampling=subsampling,restart_marker_blocks=restart)
            with self.assertRaises(UnsupportedJPEG):split_restart_720(out.getvalue())

    def test_unsupported_interval_use_fallback(self):
        out=io.BytesIO();Image.fromarray(self.rgb).save(out,format='JPEG',subsampling=1,restart_marker_blocks=7)
        with self.assertRaises(UnsupportedJPEG):split_restart_720(out.getvalue())

if __name__=='__main__':unittest.main()
