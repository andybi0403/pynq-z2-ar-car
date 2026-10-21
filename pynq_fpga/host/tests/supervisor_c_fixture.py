"""Actual supervisor/client/CarLink/production C, with simulated PL and UART.

PL register stimuli are explicit fixtures, not a replacement risk algorithm.
UART is a serialized 9600 baud 8N1 full-duplex delivery model. No hardware.
"""
import sys
import json
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'host'))
sys.path.insert(0,str(ROOT.parent/'stm32预备程序/pc'))
from test_night_a_loop import CLoop, FakeTransport, SimClock
from pynq_link import CarLink, MockSerial
from perception_client import PerceptionClient
from control_supervisor import ControlSupervisor
import car_regs as reg


def production_c_identity():
    def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    build=ROOT/'host/c_build'
    identity=json.loads((build/'build_identity.json').read_text(encoding='utf-8'))
    checks=[(identity['source'],identity['source_sha256']),
            (build/'safe_control_prod.c',identity['source_sha256']),
            (identity['header'],identity['header_sha256']),
            (build/'safe_control.h',identity['header_sha256']),
            (build/'safe_control.dll',identity['dll_sha256'])]
    if identity.get('schema')!='car-production-c-build/v1' or any(sha(path)!=expected for path,expected in checks):
        raise RuntimeError('production C build identity mismatch; rebuild DLL')
    return identity


PRODUCTION_C_IDENTITY=production_c_identity()


class PLRegisters:
    def __init__(self, clock):
        self.clock=clock;self.command=0;self.command_ts=0;self.epoch=0
        self.sample_ts=self.ticks();self.sampling=True;self.mm=1000;self.ir=0
        self.level=0;self.reasons=0;self.valid=True;self.error=False
        self.tick_offset=0xFFFFFF00
        self.sample_ts=self.ticks()
        self.mem={reg.ID_VERSION:reg.INTEGRATED_ID,reg.STATUS:3,reg.SNAP_EPOCH:0}
        self.command_writes=[]
    def ticks(self):return (int(self.clock()*100_000_000)+getattr(self,'tick_offset',0))&0xFFFFFFFF
    def read32(self, offset):
        if self.error:raise OSError('fixture MMIO disconnected')
        return self.mem.get(offset,0)
    def write32(self, offset, value):
        if self.error:raise OSError('fixture MMIO disconnected')
        if offset==reg.RISK_CMD:
            self.command=value;self.command_ts=self.ticks()
            self.command_writes.append((self.clock(),value))
        elif offset==reg.CTRL:
            if value&1:
                self.epoch=(self.epoch+1)&65535;now=self.ticks()
                if self.sampling:self.sample_ts=now
                risk=(self.reasons<<16)|(self.level<<1)|int(self.level>=2)
                self.mem.update({reg.SNAP_EPOCH:self.epoch,
                    reg.US_DATA:self.mm,reg.US_TS:self.sample_ts,reg.US_META:0x80000001 if self.valid else 1,
                    reg.IR_STATUS:4|self.ir,reg.IR_TS:now,reg.IR_META:0x80000001,
                    reg.QEI0_TS:now,reg.QEI0_META:0x80000001,
                    reg.QEI1_TS:now,reg.QEI1_META:0x80000001,
                    reg.RISK_STATE:risk,reg.RISK_TS:now,reg.RISK_META:0x80000001,
                    reg.CMD_STATE:self.command,reg.CMD_TS:self.command_ts})
            if value&2:
                self.mem[reg.TS_SNAP_LO]=self.ticks();self.mem[reg.TS_SNAP_HI]=0
        else:self.mem[offset]=value


class SupervisorCFixture:
    def __init__(self, c_offset=0):
        self.ms=SimClock();self.clock=lambda:self.ms()/1000
        self.tx=FakeTransport(self.ms);self.rx=FakeTransport(self.ms)
        self.ser=MockSerial();self.ser.write=self.tx.write
        self.link=CarLink('fixture',ser=self.ser,clock_fn=self.clock)
        self.pl=PLRegisters(self.clock);self.client=PerceptionClient(self.pl)
        self.control=ControlSupervisor(self.client,self.link,clock=self.clock,motion_allowed=True)
        self.c=CLoop();self.c_offset=c_offset
        self.intent=(0,0);self.heartbeat=True;self.control_enabled=True;self.uart_enabled=True
        self.status_enabled=True;self.next_intent=0;self.next_control=0;self.next_tx=0;self.next_status=0
        self.sequence=0;self.control_log=[];self.sent=[];self.errors=[]
        self.rejected_intents=[]
        self.control.stop()
    def c_time(self):return (int(self.ms())+self.c_offset)&0xFFFFFFFF
    def advance(self, duration_ms):
        end=self.ms()+duration_ms
        while self.ms()<end:
            now=self.ms()
            if self.control_enabled and now>=self.next_control:
                if self.heartbeat and now>=self.next_intent:
                    self.sequence+=1
                    try:self.control.submit_intent(self.sequence,*self.intent)
                    except PermissionError as exc:self.rejected_intents.append((now,self.intent,str(exc)))
                    self.next_intent=now+80
                try:self.control_log.append(self.control.tick()[2])
                except OSError as exc:self.errors.append(str(exc))
                self.next_control=now+20
            if self.uart_enabled and now>=self.next_tx:
                before=len(self.tx.sent);kind=self.link._send_once(self.clock())
                self.sent.append((now,kind,self.tx.sent[before][1]))
                self.next_tx=now+100
            self.tx.pump()
            for frame in self.tx.delivered:self.c.feed_frame(frame,self.c_time())
            self.tx.delivered.clear();self.c.tick(self.c_time())
            if self.status_enabled and now>=self.next_status:
                entry=self.c.log[-1]
                frame=f'$CAR,{entry[3]},{entry[4]},{self.c.s.latched},{self.c.s.reason},{self.c.s.distance_mm},{self.c.s.ir},{self.c.s.drop_count}#'.encode()
                self.rx.write(frame);self.next_status=now+300
            self.rx.pump()
            if self.rx.delivered:
                self.ser._rx.extend(self.rx.delivered);self.rx.delivered.clear()
            self.link._process_rx(self.clock())
            self.ms.advance(1)
    def arm(self):
        self.advance(750)
        self.control.request_release();self.advance(400)
        if self.control.last['phase']!='ARMED' or self.c.s.latched:
            raise AssertionError(f'arming failed: {self.control.last}, C latched={self.c.s.latched}')
    def drive(self,left=900,right=900):
        self.intent=(left,right);self.next_intent=self.ms();self.advance(150)
        if self.c.log[-1][3:5]!=(left,right):
            raise AssertionError(f'no motion baseline: {self.c.log[-1]}')
    def first_stop_after(self, start):
        return next((t for t,_,moving,*_ in self.c.log if t>=start and not moving),None)
