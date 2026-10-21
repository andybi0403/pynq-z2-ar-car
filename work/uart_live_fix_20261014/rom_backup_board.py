"""Read-only STM32 ROM protocol over the empirically identified USART1 link."""
from pathlib import Path
import base64,hashlib,json,struct,sys,time,zlib
import serial
sys.path.insert(0,'/home/xilinx/edge_console_v010_20261014_r2')
from overlay_session import DeviceLease
OUT=Path('/home/xilinx/stm32_sensors_platform_20261013/uart_live_fix_20261014')
OUT.mkdir(parents=True,exist_ok=True)
with DeviceLease(),serial.Serial('/dev/ttyPS1',115200,bytesize=8,parity='E',stopbits=1,timeout=.1,write_timeout=1,exclusive=True) as port:
    def receive(n,timeout=2):
        data=b'';end=time.monotonic()+timeout
        while len(data)<n and time.monotonic()<end:data+=port.read(n-len(data))
        if len(data)!=n:raise TimeoutError('ROM read: expected '+str(n)+' bytes, got '+data.hex())
        return data
    def ack():
        data=receive(1)
        if data!=b'\x79':raise RuntimeError('ROM expected ACK, got '+data.hex())
    def command(value):port.write(bytes((value,value^255)));port.flush();ack()
    def read_mem(address,size):
        command(0x11);encoded=struct.pack('>I',address);check=0
        for byte in encoded:check^=byte
        port.write(encoded+bytes((check,)));ack();port.write(bytes((size-1,(size-1)^255)));ack()
        return receive(size)
    port.reset_input_buffer();port.write(b'\x7f');port.flush();ack()
    command(0x02);count=receive(1)[0]+1;chip=receive(count);ack()
    assert chip==b'\x04\x10',chip.hex()
    factory=read_mem(0x1ffff7e0,4);capacity=struct.unpack_from('<H',factory)[0]*1024
    assert capacity in (65536,131072),capacity
    started=time.monotonic();image=b''.join(read_mem(0x08000000+off,min(256,capacity-off)) for off in range(0,capacity,256))
    (OUT/'before_uart_role_fix.bin').write_bytes(image)
    expected=Path('/home/xilinx/edge_console_v010_20261014_r2/stm32_hybrid_v3.bin').read_bytes()
    print(json.dumps({'kind':'STM32_LIVE_ROM_BACKUP','hardware':True,'chip_id':chip.hex(),
        'flash_bytes':capacity,'bytes_read':len(image),'duration_s':time.monotonic()-started,
        'original_firmware_matches_candidate':image[:len(expected)]==expected,
        'backup_sha256':hashlib.sha256(image).hexdigest(),'wrote_flash':False,
        'backup_zlib_base64':base64.b64encode(zlib.compress(image,9)).decode()}))
