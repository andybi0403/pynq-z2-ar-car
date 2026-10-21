"""Execute the readback-matched ARM firmware with explicitly modeled MMIO.

This tests production bytes, not a reimplementation of its parser/ownership.
The MMIO model supplies clocks, timer ticks, UART TX-ready/RX interrupts and
static sensor levels. It does not certify actual power, IRQ timing or pins.
"""
from pathlib import Path
import hashlib,json,struct,sys
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_R0,UC_ARM_REG_PC

ROOT=Path(__file__).resolve().parents[2]
PACKAGE=ROOT/'pynq_fpga/lab/task7_8_lab_only_v010_edge_console_20261014_r2'
sys.path.insert(0,str(PACKAGE))
from pynq_link import HybridCarLink,parse_sensor_report
BIN=(PACKAGE/'stm32_hybrid_v3.bin').read_bytes()
assert (ROOT/'pynq_fpga/preintegration/evidence/stm32_flash_v010_20261013/after_flash_128k.bin').read_bytes()[:len(BIN)]==BIN
with (PACKAGE/'stm32_hybrid_v3.elf').open('rb') as stream:
    ELF=ELFFile(stream)
    SYMS={s.name:s['st_value'] for s in ELF.get_section_by_name('.symtab').iter_symbols()}

class Machine:
    STOP=0x0800ff00
    U1=0x40013800;U2=0x40004400
    def __init__(self):
        self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
        self.u.mem_map(0x08000000,0x20000);self.u.mem_write(0x08000000,BIN)
        self.u.mem_map(0x20000000,0x5000)
        self.u.mem_map(0x40000000,0x30000);self.u.mem_map(0xe000e000,0x2000)
        data=BIN[SYMS['_sidata']-0x08000000:SYMS['_sidata']-0x08000000+SYMS['_edata']-SYMS['_sdata']]
        self.u.mem_write(SYMS['_sdata'],data)
        self.write32(0x40021000,0x03030003);self.write32(0x40021004,0x001d040a)
        self.output={self.U1:bytearray(),self.U2:bytearray()}
        self.pending={};self.timer=0;self.returned=False
        self.u.hook_add(UC_HOOK_MEM_READ,self.read_mmio)
        self.u.hook_add(UC_HOOK_MEM_WRITE,self.write_mmio)
        self.u.hook_add(UC_HOOK_CODE,self.code)
        self.call('safe_car_init')
        self.initial_registers={'USART1_BRR':self.read32(self.U1+8),'USART2_BRR':self.read32(self.U2+8),
            'USART2_CR1':self.read32(self.U2+12),'USART2_CR2':self.read32(self.U2+16),
            'USART2_CR3':self.read32(self.U2+20),'AFIO_MAPR':self.read32(0x40010004),
            'SystemCoreClock':self.read32(SYMS['SystemCoreClock'])}
    def write32(self,address,value):self.u.mem_write(address,struct.pack('<I',value))
    def read32(self,address):return struct.unpack('<I',self.u.mem_read(address,4))[0]
    def code(self,u,address,size,user):
        if address==self.STOP:self.returned=True;u.emu_stop()
    def read_mmio(self,u,access,address,size,value,user):
        if address in (self.U1,self.U2):
            flags=self.pending.get(address,(0,0))[0]
            self.write32(address,0xc0|flags)
        elif address in (self.U1+4,self.U2+4):
            base=address-4;self.write32(address,self.pending.get(base,(0,0))[1]);self.pending.pop(base,None)
        elif address==0x40000024:
            self.timer=(self.timer+1)&65535;self.write32(address,self.timer)
        elif address==0x40010808:self.write32(address,0x50)
    def write_mmio(self,u,access,address,size,value,user):
        if address in (self.U1+4,self.U2+4):self.output[address-4].append(value&255)
    def call(self,name):
        self.u.reg_write(UC_ARM_REG_SP,0x20004ff0)
        self.u.reg_write(UC_ARM_REG_LR,self.STOP|1)
        self.returned=False
        self.u.emu_start(SYMS[name]|1,0,count=300000)
        if not self.returned:raise RuntimeError('function did not return: '+name+' PC='+hex(self.u.reg_read(UC_ARM_REG_PC)))
    def inject(self,port,data,flags=0x20):
        for byte in data:
            self.pending[port]=(flags,byte)
            self.call('USART1_IRQHandler' if port==self.U1 else 'USART2_IRQHandler')
    def step(self,ms,polls=4):
        self.write32(SYMS['millis'],ms)
        for _ in range(polls):self.call('safe_car_poll')
    def reports(self):
        raw=bytes(self.output[self.U2]);parts=[]
        for fragment in raw.split(b'#')[:-1]:
            at=fragment.rfind(b'$')
            if at>=0:
                report=parse_sensor_report(fragment[at:]+b'#')
                if report is not None:parts.append(report)
        return parts
    def facts(self):
        reports=self.reports()
        return {'uart2_tx_bytes':len(self.output[self.U2]),'valid_S1':len(reports),
                'modeled_initial_registers':self.initial_registers,
                'usb_owner':int(self.u.mem_read(SYMS['usb_owner'],1)[0]),
                'diagnostic':list(struct.unpack('<10I',self.u.mem_read(SYMS['rx_diag'],40))),
                'all_replies_locked_zero':bool(reports and all(r['lock']==1 and r['left']==r['right']==0 for r in reports))}

def run(name,noise_period=None,noise_flags=0x20,one_noise=False,invalid_sensor=True):
    m=Machine();session=0x12345678;queries=0
    now=[0.0]
    class Wire:
        def __init__(self):self.offset=0;self.writes=[]
        def write(self,data):
            self.writes.append(bytes(data));m.inject(m.U2,data);return len(data)
        def read(self,n):
            data=bytes(m.output[m.U2][self.offset:self.offset+min(n,7)])
            self.offset+=len(data);return data
    wire=Wire();host=HybridCarLink('offline_emulated_wire',ser=wire,clock_fn=lambda:now[0],session=session)
    for ms in range(1250):
        now[0]=ms/1000
        m.write32(SYMS['millis'],ms)
        if (one_noise and ms==0) or (noise_period and ms%noise_period==0):
            m.inject(m.U1,b'x',noise_flags)
        if ms%50==0:
            queries+=1;host._send_once(now[0])
        m.step(ms)
        host._process_rx(now[0])
    assert all(data.startswith(b'$Q1,') or data==b'$PSTOP#' for data in wire.writes)
    assert m.read32(0x40000834)==m.read32(0x40000838)==0
    return {'scenario':name,'query_count':queries,'full_host_accepted_S1':host.state_seq,
            'full_host_parser_errors':host.sensor_errors,'modeled_PWM_final':[0,0],**m.facts()}

if __name__=='__main__':
    results=[run('clean USART1, valid PYNQ Q1; ultrasound has no echo'),
        run('one stray USART1 byte then silence',one_noise=True),
        run('USART1 stray byte every 100ms',noise_period=100),
        run('USART1 framing-error byte every 100ms',noise_period=100,noise_flags=2)]
    assert results[0]['valid_S1']>=20 and results[0]['full_host_accepted_S1']>=20 and results[0]['all_replies_locked_zero']
    assert results[1]['valid_S1']>0 and results[1]['usb_owner']==0
    assert results[2]['valid_S1']==0 and results[2]['uart2_tx_bytes']==0 and results[2]['usb_owner']==1
    assert results[3]['valid_S1']==0 and results[3]['uart2_tx_bytes']==0 and results[3]['usb_owner']==1 and results[3]['diagnostic'][1]>0
    record={'schema':'flashed-arm-uart-emulation/v1','hardware':False,
       'firmware_sha256':hashlib.sha256(BIN).hexdigest(),'matches_actual_flash_readback':True,
       'scope':'actual ARM instructions with modeled MMIO; not board power/wires/IRQ timing',
       'scenarios':results,'passed':True}
    Path(__file__).with_name('arm_emulation_results.json').write_text(json.dumps(record,indent=2),'utf8')
    print(json.dumps(record))
