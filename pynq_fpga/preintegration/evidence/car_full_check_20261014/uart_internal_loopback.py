"""Bounded UART1 peripheral self-test; never tests external wiring implicitly.

Register definitions: AMD embeddedsw xuartps_hw.h (MR offset 4,
CHMODE_MASK=0x300, local loopback=0x200). No release/drive frames are sent.
"""
from pathlib import Path
import json
import mmap
import secrets
import struct
import time
import serial

result={'kind':'UART1_INTERNAL_LOOPBACK','hardware':True,
        'scope':'PS UART peripheral + Linux serial path; excludes EMIO pins, wires and STM32',
        'source':'https://github.com/Xilinx/embeddedsw/blob/master/XilinxProcessorIPLib/drivers/uartps/src/xuartps_hw.h'}
with serial.Serial('/dev/ttyPS1',115200,timeout=.05,write_timeout=.5,exclusive=True) as port:
    with open('/dev/mem','r+b',buffering=0) as memory:
        with mmap.mmap(memory.fileno(),4096,offset=0xe0001000) as regs:
            def read(offset):return struct.unpack_from('<I',regs,offset)[0]
            def write(offset,value):struct.pack_into('<I',regs,offset,value)
            port.flush();time.sleep(.05)
            original=read(4)
            result['normal_registers']={hex(n):hex(read(n)) for n in (0,4,0x10,0x18,0x1c,0x20,0x2c,0x34)}
            trials=[]
            try:
                assert original&0x300==0, 'UART already in a non-normal mode'
                write(4,(original&~0x300)|0x200)
                assert read(4)&0x300==0x200
                port.reset_input_buffer()
                for _ in range(3):
                    payload=('UART_LOCAL_SELFTEST_'+secrets.token_hex(8)+'\n').encode()
                    port.write(payload);port.flush()
                    received=b'';until=time.monotonic()+.8
                    while len(received)<len(payload) and time.monotonic()<until:
                        received+=port.read(len(payload)-len(received))
                    trials.append({'sent_bytes':len(payload),'received_bytes':len(received),
                                   'byte_match':received==payload})
            finally:
                port.flush();write(4,original)
                result['restored_mode']=read(4)==original
                port.reset_input_buffer()
                port.write(b'$PSTOP#');port.flush()
            result['trials']=trials
            result['passed']=bool(result['restored_mode'] and len(trials)==3 and all(t['byte_match'] for t in trials))
clock=Path('/sys/kernel/debug/clk/clk_summary')
if clock.exists():result['uart_clocks']=[line for line in clock.read_text().splitlines() if 'uart' in line]
print(json.dumps(result))
