import io,struct,sys,unittest
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pynq_fpga/preintegration/host'))
from wireless_jpeg_dma import validate_packet,JpegDMA,PACKET_CAPACITY
from video_profile import FRAME_BYTES


class PacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out=io.BytesIO();Image.new('RGB',(1280,720),(30,60,120)).save(out,format='JPEG',subsampling=1)
        cls.jpeg=out.getvalue()
    def packet(self,**changes):
        words=dict(magic=0x47504a43,abi=1,frame_id=123,flags=1,size=len(self.jpeg),width=1280,height=720,counter=1)
        words.update(changes);return self.jpeg+struct.pack('<8I',*words.values())
    def test_accept_complete_identity_bound_720_jpeg(self):
        jpeg,counter=validate_packet(self.packet(),123,0)
        self.assertEqual((jpeg,counter),(self.jpeg,1))
    def test_reject_overflow_invalid_metadata_wrong_id_and_old_completion(self):
        for changes in ({'flags':3},{'flags':0},{'flags':5},{'frame_id':124},{'counter':0},{'counter':2},{'abi':2},{'width':640},{'size':len(self.jpeg)+1}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):validate_packet(self.packet(**changes),123,0)
    def test_jpeg_sof_and_trailer_must_agree(self):
        packet=bytearray(self.packet());sof=packet.index(b'\xff\xc0');packet[sof+5:sof+7]=(360).to_bytes(2,'big')
        with self.assertRaises(ValueError):validate_packet(packet,123,0)
    def test_byte_count_and_eoi_cannot_be_forged_by_padding(self):
        with self.assertRaises(ValueError):validate_packet(self.packet()[:-1],123,0)
        packet=self.jpeg[:-2]+b'\x00\x00'+self.packet()[-32:]
        with self.assertRaises(ValueError):validate_packet(packet,123,0)


class TimeoutTests(unittest.TestCase):
    def test_missing_packet_completion_disables_session_and_prevents_reuse(self):
        class MMIO:
            def __init__(self):self.writes=[]
            def write(self,a,v):self.writes.append((a,v))
            def read(self,a):return 0
        class Buffer(bytearray):
            def __init__(self,size,address):super().__init__(size);self.physical_address=address;self.nbytes=size
            def flush(self):pass
            def invalidate(self):raise AssertionError('uncompleted DDR must not be exposed')
        now=[0.]
        def sleep(seconds):now[0]+=.01
        dma=JpegDMA(MMIO(),MMIO(),MMIO(),timeout_s=.02,clock=lambda:now[0],sleep=sleep);dma.quality=85
        source=Buffer(FRAME_BYTES,0x10000000);dest=Buffer(PACKET_CAPACITY,0x11000000)
        with self.assertRaises(TimeoutError):dma.transfer(1,source,dest,quality=85)
        self.assertTrue(dma.failed)
        with self.assertRaisesRegex(RuntimeError,'session failed'):dma.transfer(2,source,dest,quality=85)

if __name__=='__main__':unittest.main()
