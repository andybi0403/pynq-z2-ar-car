"""Stop the console and inspect scale-independent QEI diagnostics; no drive commands."""
from pathlib import Path
import json,subprocess,time,mmap,os,struct
unit='pynq-car-console.service'
path='/home/xilinx/v011_uart_recovery_20261026_r17b'
config=Path('/etc/systemd/system/'+unit).read_text()
assert path in config
assert subprocess.check_output(['systemctl','show',unit,'-p','MainPID','--value'],text=True).strip()=='0','Console must be stopped first'
fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
mem=mmap.mmap(fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0x43c00000)
def read(offset):return struct.unpack_from('<I',mem,offset)[0]
assert read(0)==0xc425100b,'Unexpected hardware contract; no reconfiguration attempted'
struct.pack_into('<I',mem,4,1)
result={'service_stopped':True,'motor_commands_sent':False,'scales_changed':False,
        'id':hex(read(0)),'epoch':read(12),'qei':[]}
for ch,base,cfg in [(0,0x80,0x120),(1,0x98,0x130)]:
    info=read(base+20)
    result['qei'].append({'channel':ch,'position_batch':read(base),
      'info':info,'seen_edge':bool(info&2),'period_valid':bool(info&4),
      'illegal_transitions':(info>>4)&255,'divider_overruns':(info>>12)&255,
      'filter_rejections':(info>>20)&255,'scale':read(cfg+8),
      'filter':read(cfg+4)})
mem.close();os.close(fd)
print(json.dumps(result))
