"""PG020 direct-register VDMA with an isolated completion scratch frame.

With S2MM TUSER sync, the following SOF completes the preceding frame count.
Send two copies; capture the second into private scratch, never the encoder's
destination. Require RX completion, TX halt and RX halt before exposing pixels.
Reset/re-arm each transaction so counters and frame pointers cannot carry over.
"""
import time
import xml.etree.ElementTree as ET
from native_video import WIDTH,HEIGHT,FRAME_BYTES
from hwh_contract import audit_hwh


def audit_wireless_hwh(path):
    audit_hwh(path,require_placeholder=False)
    root=ET.parse(path).getroot();modules={m.get('INSTANCE'):m for m in root.iter('MODULE')}
    def params(instance):return {p.get('NAME'):p.get('VALUE') for p in modules[instance].iter('PARAMETER')}
    p=params('video_vdma')
    for name,value in {'C_INCLUDE_S2MM':'1','C_INCLUDE_MM2S':'1','C_NUM_FSTORES':'3',
                       'C_M_AXI_MM2S_DATA_WIDTH':'64','C_M_AXI_S2MM_DATA_WIDTH':'64',
                       'C_M_AXIS_MM2S_TDATA_WIDTH':'32','C_S_AXIS_S2MM_TDATA_WIDTH':'32'}.items():
        if p.get(name)!=value:raise ValueError('wireless VDMA parameter mismatch: '+name)
    if params('car_system').get('VIDEO_WIDTH')!='1280' or params('car_system').get('VIDEO_HEIGHT')!='720':
        raise ValueError('wireless wrapper must be 1280x720')
    if params('video_hp0_ic').get('NUM_SI')!='2':raise ValueError('wireless capture requires two HP0 masters')
    def bus(instance,name):
        b=modules[instance].find(f"./BUSINTERFACES/BUSINTERFACE[@NAME='{name}']")
        if b is None or not b.get('BUSNAME'):raise ValueError('missing capture interface '+instance+'/'+name)
        return b.get('BUSNAME')
    for a,b in [(('car_system','M_AXIS'),('video_capture_adapter','S_AXIS')),
                (('video_capture_adapter','M_AXIS'),('video_vdma','S_AXIS_S2MM')),
                (('video_vdma','M_AXI_S2MM'),('video_hp0_ic','S01_AXI'))]:
        if bus(*a)!=bus(*b):raise ValueError('processed pixels/capture DDR path is disconnected')
    # A stray HDMI fanout would propagate its READY back into the live path.
    sink=modules['hdmi_axis_to_video'].find("./BUSINTERFACES/BUSINTERFACE[@NAME='video_in']")
    if sink is not None and bus('car_system','M_AXIS')==sink.get('BUSNAME'):
        raise ValueError('HDMI must not backpressure the wireless capture path')
    return {'profile':'wireless720','width':WIDTH,'height':HEIGHT,'stride':WIDTH*4,'hardware_validated':False}


class FiniteVDMA:
    RUN_TWICE=0x00025011  # two source copies, PARK, no genlock
    CAPTURE=0x00015003  # circular RX with one-frame notifications, no count halt
    ERROR_MASK=0x4ff0
    def __init__(self,mmio,*,scratch=None,timeout_s=.1,clock=time.monotonic,sleep=time.sleep):
        self.mmio=mmio;self.timeout=timeout_s;self.clock=clock;self.sleep=sleep
        self.last_id=-1;self.failed=False;self.scratch=scratch
        self.last_timings={}
    def wait(self,predicate,label):
        deadline=self.clock()+self.timeout
        while not predicate():
            if self.clock()>=deadline:raise TimeoutError('VDMA '+label+' timed out')
            self.sleep(.0002)
    def reset(self):
        for cr in (0,0x30):self.mmio.write(cr,4)
        self.wait(lambda:all(not self.mmio.read(cr)&4 for cr in (0,0x30)),'reset')
    @staticmethod
    def address(buffer):
        if getattr(buffer,'nbytes',len(memoryview(buffer).cast('B')))!=FRAME_BYTES:
            raise ValueError('wrong DMA frame size')
        address=int(buffer.physical_address)
        if address<0 or address>=2**32 or address%8:raise ValueError('DMA address must be aligned 32-bit DDR address')
        return address
    def transfer(self,frame_id,source,destination):
        if self.failed:raise RuntimeError('VDMA failed; restart the whole session')
        if type(frame_id) is not int or frame_id<=self.last_id:raise ValueError('duplicate DMA frame identity')
        src=self.address(source);dst=self.address(destination)
        if self.scratch is None:raise ValueError('private completion scratch buffer required')
        scratch=self.address(self.scratch)
        if any(abs(a-b)<FRAME_BYTES for a,b in ((src,dst),(src,scratch),(dst,scratch))):
            raise ValueError('DMA source, destination and scratch must not overlap')
        try:
            begun=self.clock();self.reset();reset_done=self.clock()
            source.flush();flush_done=self.clock();self.mmio.write(0x28,0)
            # Prepare writer first; VSIZE is always programmed last (PG020).
            for cr,base,addresses,control in (
                    (0x30,0xa0,(dst,scratch,scratch),self.CAPTURE),
                    (0,0x50,(src,src,src),self.RUN_TWICE)):
                self.mmio.write(cr+4,0x7ff0)
                self.mmio.write(cr,control)
                for i,address in enumerate(addresses):self.mmio.write(base+12+4*i,address)
                self.mmio.write(base+4,WIDTH*4);self.mmio.write(base+8,WIDTH*4)
                self.mmio.write(base,HEIGHT)
            def complete():
                statuses=[self.mmio.read(x) for x in (4,0x34)]
                if any(s&self.ERROR_MASK for s in statuses):raise RuntimeError('VDMA error: '+str(statuses))
                return bool(statuses[0]&0x1000 and statuses[0]&1 and statuses[1]&0x1000)
            programmed=self.clock();self.wait(complete,'first frame and private scratch');completed=self.clock()
            # The writer is waiting for a third SOF; stop and confirm it halted.
            self.stop()
            if any(self.mmio.read(x)&self.ERROR_MASK for x in (4,0x34)):
                raise RuntimeError('VDMA error while draining writer')
            halted=self.clock();destination.invalidate();ended=self.clock();self.last_id=frame_id
            self.last_timings={'reset_ms':(reset_done-begun)*1000,'flush_ms':(flush_done-reset_done)*1000,
              'program_ms':(programmed-flush_done)*1000,'two_frames_and_completion_ms':(completed-programmed)*1000,
              'halt_ms':(halted-completed)*1000,'invalidate_ms':(ended-halted)*1000,
              'total_ms':(ended-begun)*1000,'source_copies':2}
        except Exception:
            self.failed=True
            self.mmio.write(0,0);self.mmio.write(0x30,0)
            raise
    def stop(self):
        self.mmio.write(0,0);self.mmio.write(0x30,0)
        self.wait(lambda:all(self.mmio.read(x)&1 for x in (4,0x34)),'halt')


class WirelessBoardVideo:
    worker_owned_shutdown=True
    def __init__(self,overlay):
        self.overlay=overlay;self.running=False;self.inputs=[];self.outputs=[];self.dma=None;self.scratch=None
    def start(self):
        from pynq import allocate
        from pynq import MMIO
        if self.running:raise RuntimeError('video already started')
        self.dma=FiniteVDMA(MMIO(0x43000000,0x10000));self.dma.reset()
        try:
            for _ in range(3): self.inputs.append(allocate(shape=(HEIGHT,WIDTH,4),dtype='u1'))
            for _ in range(3): self.outputs.append(allocate(shape=(HEIGHT,WIDTH,4),dtype='u1'))
            self.scratch=allocate(shape=(HEIGHT,WIDTH,4),dtype='u1')
            self.dma.scratch=self.scratch
        except Exception:
            for f in self.inputs+self.outputs:f.freebuffer()
            self.inputs=[];self.outputs=[]
            raise
        self.running=True
    def stop(self):
        if self.dma:self.dma.stop()
        # Caller must join every worker before releasing buffers.
        for f in self.inputs+self.outputs:f.freebuffer()
        if self.scratch is not None:self.scratch.freebuffer();self.scratch=None
        self.inputs=[];self.outputs=[];self.running=False
