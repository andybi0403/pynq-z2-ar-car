"""Future board-side read-only audit. This file has not been run on hardware.

No Overlay reload, UART open, query, STOP, networking change or register write.
Run as root on the PYNQ only when a later connected diagnostic is available.
"""
from pathlib import Path
import json,mmap,subprocess,struct

result={'schema':'pynq-uart-route-readonly/v1','hardware':True,
        'mutations':False,'UART_opened':False}
with open('/dev/mem','rb',buffering=0) as physical:
    def block(base,offsets):
        with mmap.mmap(physical.fileno(),4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=base) as page:
            return {hex(off):hex(struct.unpack_from('<I',page,off)[0]) for off in offsets}
    result['UART1']=block(0xe0001000,[0,4,0x10,0x14,0x18,0x1c,0x20,0x2c,0x34])
    result['SLCR']=block(0xf8000000,[0x12c,0x154,0x22c,0x900]+list(range(0x700,0x7d8,4)))
node=Path('/sys/firmware/devicetree/base/axi/serial@e0001000')
result['device_tree']={name:(node/name).read_bytes().hex() for name in ('status','reg','pinctrl-0','pinctrl-names') if (node/name).exists()}
device=Path('/sys/class/tty/ttyPS1/device')
result['device_path']=str(device.resolve()) if device.exists() else None
result['owners']=subprocess.run(['fuser','/dev/ttyPS1'],capture_output=True,text=True,timeout=5).stdout.strip()
print(json.dumps(result,indent=2))
