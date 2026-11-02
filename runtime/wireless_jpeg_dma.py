"""One source frame -> real PL HUD -> hardware JPEG -> packet DMA completion."""
import struct,time
from pathlib import Path
import xml.etree.ElementTree as ET
from video_profile import WIDTH,HEIGHT,FRAME_BYTES

PACKET_CAPACITY=4*1024*1024


def validate_packet(packet,frame_id,previous_counter):
    if len(packet)<36:raise ValueError('short PL JPEG packet')
    magic,abi,actual_id,flags,size,width,height,counter=struct.unpack('<8I',packet[-32:])
    if (magic,abi)!=(0x47504a43,1):raise ValueError('PL JPEG trailer ABI mismatch')
    if actual_id!=frame_id&0xffffffff:raise ValueError('PL JPEG frame identity mismatch')
    if flags!=1:raise ValueError('PL JPEG overflow, geometry, or metadata validity failure: '+hex(flags))
    if (width,height)!=(1280,720) or size!=len(packet)-32:raise ValueError('PL JPEG geometry/byte-count mismatch')
    if counter!=(previous_counter+1)&0xffffffff:raise ValueError('PL JPEG completion counter mismatch')
    jpeg=packet[:-32]
    if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):raise ValueError('incomplete PL JPEG')
    i=2;size_seen=False
    while i<len(jpeg)-3:
        if jpeg[i]!=255:raise ValueError('PL JPEG header marker invalid')
        marker=jpeg[i+1]
        if marker==255:i+=1;continue
        length=int.from_bytes(jpeg[i+2:i+4],'big')
        if length<2 or i+2+length>len(jpeg):raise ValueError('PL JPEG header length invalid')
        if marker==0xc0:
            if length!=17 or jpeg[i+4]!=8 or (int.from_bytes(jpeg[i+7:i+9],'big'),int.from_bytes(jpeg[i+5:i+7],'big'))!=(width,height):
                raise ValueError('JPEG SOF differs from PL packet geometry')
            size_seen=True
        if marker==0xda:break
        i+=length+2
    if not size_seen:raise ValueError('missing baseline JPEG frame header')
    return jpeg,counter


def audit_jpeg_hwh(path):
    root=ET.parse(path).getroot();modules={m.get('INSTANCE'):m for m in root.iter('MODULE')}
    for name in ('video_vdma','car_system','jpeg_encoder','jpeg_width','jpeg_dma'):
        if name not in modules:raise ValueError('missing hardware JPEG module: '+name)
    def parameter(module,name):
        p=modules[module].find("./PARAMETERS/PARAMETER[@NAME='"+name+"']")
        if p is None:raise ValueError('missing HWH parameter '+module+'/'+name)
        return int(p.get('VALUE'),0)
    for module,name,expected in (
        ('car_system','VIDEO_WIDTH',1280),('car_system','VIDEO_HEIGHT',720),
        ('jpeg_encoder','VIDEO_WIDTH',1280),('jpeg_encoder','VIDEO_HEIGHT',720),
        ('video_vdma','C_INCLUDE_S2MM',0),('jpeg_dma','C_INCLUDE_SG',0),
        ('jpeg_dma','C_INCLUDE_MM2S',0),('jpeg_dma','C_SG_LENGTH_WIDTH',23),
        ('jpeg_dma','C_S_AXIS_S2MM_TDATA_WIDTH',32),('jpeg_dma','C_M_AXI_S2MM_DATA_WIDTH',64)):
        if parameter(module,name)!=expected:raise ValueError('incorrect HWH hardware JPEG parameter '+module+'/'+name)
    def bus(module,interface):
        p=modules[module].find("./BUSINTERFACES/BUSINTERFACE[@NAME='"+interface+"']")
        if p is None:raise ValueError('missing HWH interface '+module+'/'+interface)
        return p.get('BUSNAME')
    for a,ai,b,bi in (('car_system','M_AXIS','jpeg_encoder','S_AXIS'),('jpeg_encoder','M_AXIS','jpeg_width','S_AXIS'),('jpeg_width','M_AXIS','jpeg_dma','S_AXIS_S2MM')):
        if not bus(a,ai) or bus(a,ai)!=bus(b,bi):raise ValueError('hardware JPEG stream connection differs')
    for module,address in (('video_vdma',0x43000000),('jpeg_encoder',0x43c30000),('jpeg_dma',0x40400000)):
        ranges=[int(n.get('BASEVALUE'),0) for n in root.iter('MEMRANGE') if n.get('INSTANCE')==module and n.get('BASEVALUE')]
        if ranges!=[address]:raise ValueError('hardware JPEG MMIO address differs: '+module)
    return {'profile':'wireless720_jpeg','width':1280,'height':720,'packet_abi':1,'hardware_validated':False}


class JpegDMA:
    VDMA_ERRORS=0x4ff0
    DMA_ERRORS=0x770
    def __init__(self,vdma,dma,encoder,*,timeout_s=.25,clock=time.monotonic,sleep=time.sleep):
        self.vdma=vdma;self.dma=dma;self.encoder=encoder;self.timeout=timeout_s;self.clock=clock;self.sleep=sleep
        self.failed=False;self.last_id=-1;self.counter=0;self.last_timings={};self.quality=None
    def wait(self,predicate,label):
        end=self.clock()+self.timeout
        while not predicate():
            if self.clock()>=end:raise TimeoutError('hardware JPEG '+label+' timed out')
            self.sleep(.001)
    def reset(self):
        self.vdma.write(0,4);self.dma.write(0x30,4)
        self.wait(lambda:not (self.vdma.read(0)&4 or self.dma.read(0x30)&4),'reset')
        self.encoder.write(0,3);self.sleep(.00002);self.encoder.write(0,0)
        self.counter=0;self.quality=None
    @staticmethod
    def address(buffer,expected_size):
        if buffer.nbytes!=expected_size:raise ValueError('incorrect hardware JPEG DMA buffer size')
        address=int(buffer.physical_address)
        if address<0 or address>=2**32 or address%8:raise ValueError('unaligned hardware JPEG DDR address')
        return address
    def transfer(self,frame_id,source,destination,*,quality):
        if self.failed:raise RuntimeError('hardware JPEG session failed; restart with explicit FPGA reload')
        if type(frame_id) is not int or frame_id<=self.last_id:raise ValueError('repeated hardware JPEG source identity')
        if type(quality) is not int or not 1<=quality<=100:raise ValueError('invalid hardware JPEG quality')
        src=self.address(source,FRAME_BYTES);dst=self.address(destination,PACKET_CAPACITY)
        if src<dst+PACKET_CAPACITY and dst<src+FRAME_BYTES:raise ValueError('overlapping hardware JPEG DMA buffers')
        try:
            started=self.clock()
            self.vdma.write(0,4)
            self.wait(lambda:not self.vdma.read(0)&4,'source channel reset')
            if self.quality!=quality:
                self.encoder.write(0xc,quality)
                if self.encoder.read(0xc)!=quality:raise RuntimeError('hardware JPEG quality readback differs')
                self.sleep(.00002);self.quality=quality
            source.flush();flushed=self.clock()
            self.dma.write(0x34,0x7000);self.dma.write(0x30,1)
            self.dma.write(0x48,dst);self.dma.write(0x58,PACKET_CAPACITY)
            self.encoder.write(0,1)
            self.vdma.write(4,0x7ff0);self.vdma.write(0x28,0);self.vdma.write(0,0x00015011)
            for offset in (0x5c,0x60,0x64):self.vdma.write(offset,src)
            self.vdma.write(0x58,WIDTH*4);self.vdma.write(0x54,WIDTH*4);self.vdma.write(0x50,HEIGHT)
            programmed=self.clock()
            def complete():
                vs=self.vdma.read(4);ds=self.dma.read(0x34)
                if vs&self.VDMA_ERRORS or ds&self.DMA_ERRORS:raise RuntimeError('hardware JPEG DMA status error: '+str((vs,ds)))
                return bool(vs&1 and vs&0x1000 and ds&2 and ds&0x1000)
            self.wait(complete,'one source frame and packet write completion')
            completed=self.clock();length=self.dma.read(0x58)
            if not 36<=length<=PACKET_CAPACITY:raise RuntimeError('invalid completed hardware JPEG DMA byte count')
            self.stop();destination.invalidate()
            jpeg,counter=validate_packet(bytes(memoryview(destination).cast('B')[:length]),frame_id,self.counter)
            ended=self.clock();self.counter=counter;self.last_id=frame_id
            self.last_timings={'flush_ms':(flushed-started)*1000,'program_ms':(programmed-flushed)*1000,'hardware_wait_ms':(completed-programmed)*1000,'completion_copy_ms':(ended-completed)*1000,'jpeg_bytes':len(jpeg),'completed_frame_counter':counter,'source_copies':1}
            return jpeg
        except Exception:
            self.failed=True
            try:self.stop()
            except Exception:pass
            raise
    def stop(self):
        self.vdma.write(0,0);self.dma.write(0x30,0)
        self.wait(lambda:bool(self.vdma.read(4)&1 and self.dma.read(0x34)&1),'halt')


class HardwareJpegBoardVideo:
    hardware_jpeg=True
    def __init__(self,overlay):
        self.overlay=overlay;self.inputs=[];self.outputs=[];self.dma=None;self.running=False
        self.reserved_bytes=3*(FRAME_BYTES+PACKET_CAPACITY)
    def start(self):
        from pynq import allocate,MMIO
        if self.running:raise RuntimeError('hardware JPEG video already running')
        for name,base,span in (('video_vdma',0x43000000,0x10000),('jpeg_dma',0x40400000,0x10000),('jpeg_encoder',0x43c30000,0x1000)):
            item=self.overlay.ip_dict.get(name,{})
            if int(item.get('phys_addr',-1))!=base or int(item.get('addr_range',0))<span:
                raise ValueError('loaded Overlay hardware JPEG address mismatch: '+name)
        self.dma=JpegDMA(MMIO(0x43000000,0x10000),MMIO(0x40400000,0x10000),MMIO(0x43c30000,0x1000))
        self.dma.reset()
        try:
            for _ in range(3):
                self.inputs.append(allocate(shape=(HEIGHT,WIDTH,4),dtype='u1'))
                self.outputs.append(allocate(shape=(PACKET_CAPACITY,),dtype='u1'))
        except Exception:
            for buffer in self.inputs+self.outputs:buffer.freebuffer()
            self.inputs=[];self.outputs=[];raise
        self.running=True
    def stop(self):
        if self.dma:self.dma.stop()
        for buffer in self.inputs+self.outputs:buffer.freebuffer()
        self.inputs=[];self.outputs=[];self.running=False
