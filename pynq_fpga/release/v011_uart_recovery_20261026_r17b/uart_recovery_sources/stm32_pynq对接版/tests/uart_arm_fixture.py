"""Execute the freshly built production ARM firmware with modeled MMIO.

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
PACKAGE=ROOT/'stm32_pynq对接版/build_safe'
sys.path.insert(0,str(ROOT/'stm32预备程序/pc'))
from pynq_link import HybridCarLink,parse_sensor_report
BIN=(PACKAGE/'safe_car.bin').read_bytes()
with (PACKAGE/'safe_car.elf').open('rb') as stream:
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
        bound=int(self.u.mem_read(SYMS['hybrid_uart'],1)[0]);raw=bytes(self.output[self.U1 if bound==1 else self.U2]);parts=[]
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
                'bound_uart':int(self.u.mem_read(SYMS['hybrid_uart'],1)[0]),
                'diagnostic':list(struct.unpack('<10I',self.u.mem_read(SYMS['rx_diag'],40))),
                'all_replies_locked_zero':bool(reports and all(r['lock']==1 and r['left']==r['right']==0 for r in reports))}
