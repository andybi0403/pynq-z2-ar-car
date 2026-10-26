"""Acknowledged binary upload over PYNQ's USB console; Wi-Fi is never changed."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import secrets
import shlex
import sys
import time
import zlib

import serial
from serial.tools import list_ports

def upload(source, target):
    data=Path(source).read_bytes();digest=hashlib.sha256(data).hexdigest()
    marker='USBX_'+secrets.token_hex(8)
    receiver='''import sys,base64,hashlib,os
from pathlib import Path
target=Path(TARGET)
assert str(target).startswith('/home/xilinx/') and '..' not in target.parts
partial=Path(str(target)+'.'+MARKER+'.partial')
h=hashlib.sha256();count=0;total=0
try:
 with partial.open('xb') as f:
  print(MARKER+'_READY',flush=True)
  while True:
   line=sys.stdin.buffer.readline()
   if not line:raise RuntimeError('unexpected input EOF')
   if line.strip()==(MARKER+'_END').encode():break
   block=base64.b64decode(line.strip(),validate=True)
   assert len(block)<=768
   f.write(block);h.update(block);total+=len(block);count+=1
   print(MARKER+'_ACK:'+str(count)+':'+str(total),flush=True)
 assert total==SIZE and h.hexdigest()==DIGEST
 os.replace(partial,target)
 print(MARKER+'_DONE:'+h.hexdigest(),flush=True)
except BaseException:
 partial.unlink(missing_ok=True)
 raise
'''
    receiver=receiver.replace('TARGET',repr(target)).replace('MARKER',repr(marker))
    receiver=receiver.replace('DIGEST',repr(digest)).replace('SIZE',str(len(data)))
    ports={p.device:p for p in list_ports.comports()}
    assert 'COM14' in ports and (ports['COM14'].vid,ports['COM14'].pid)==(0x0403,0x6010)
    port=serial.Serial(port=None,baudrate=115200,timeout=.02,write_timeout=3)
    port.port='COM14';port.dtr=False;port.rts=False
    started=time.monotonic();transcript=bytearray();receiver_started=False
    def wait_for(pattern,seconds):
        buf=bytearray();end=time.monotonic()+seconds
        while time.monotonic()<end:
            buf.extend(port.read(4096))
            match=re.search(pattern,buf)
            if match:return bytes(buf)
        raise TimeoutError('USB transfer acknowledgement missing: '+repr(bytes(buf[-500:])))
    try:
        port.open();port.write(b'\r')
        wait_for(rb'xilinx@pynq:[^\r\n]*\$\s*$',3)
        port.write(b'stty -echo\n')
        wait_for(rb'xilinx@pynq:[^\r\n]*\$\s*$',3)
        code=base64.b64encode(receiver.encode()).decode()
        command="/usr/local/share/pynq-venv/bin/python3 -c "+shlex.quote("import base64;exec(base64.b64decode("+repr(code)+"))")+'\n'
        assert len(command)<4000
        port.write(command.encode());receiver_started=True
        wait_for((marker+'_READY').encode()+rb'\r?\n',5)
        for offset in range(0,len(data),768):
            block=data[offset:offset+768]
            port.write(base64.b64encode(block)+b'\n');port.flush()
            number=offset//768+1;total=offset+len(block)
            wait_for((marker+'_ACK:'+str(number)+':'+str(total)).encode()+rb'\r?\n',4)
            if number%50==0:print('USB_UPLOAD',total,'/',len(data),flush=True)
        port.write((marker+'_END\n').encode());port.flush()
        wait_for((marker+'_DONE:'+digest).encode()+rb'\r?\n',8)
        receiver_started=False
        result=dict(bytes=len(data),sha256=digest,target=target,elapsed_s=time.monotonic()-started,
                    verified=True,pc_network_mutated=False)
        print(json.dumps(result),flush=True)
        return result
    finally:
        if port.is_open:
            if receiver_started:port.write(b'\x03');port.flush();time.sleep(.2)
            port.write(b'stty echo\n');port.flush()
        port.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('target');p.add_argument('evidence',type=Path)
    args=p.parse_args();result=upload(args.source,args.target)
    args.evidence.write_text(json.dumps(result,indent=2),'utf8')
