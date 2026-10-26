"""Run a bounded board job over the verified USB debug UART, preserving Wi-Fi."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'work/uart_live_fix_20261014'))
from pynq_console_transport import execute
from serial.tools import list_ports

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('evidence',type=Path)
    parser.add_argument('--seconds',type=int,default=60)
    parser.add_argument('--root',action='store_true')
    parser.add_argument('--quiet',action='store_true',help='keep raw capture payload in the evidence file')
    args=parser.parse_args()
    if args.evidence.exists():raise FileExistsError(args.evidence)
    ports={p.device:p for p in list_ports.comports()}
    board=ports.get('COM14')
    if board is None or (board.vid,board.pid)!=(0x0403,0x6010):
        raise RuntimeError('Expected PYNQ FT2232 USB debug UART is unavailable')
    result=execute(args.source.read_text('utf8'),seconds=args.seconds,
                   root=args.root,password='xilinx' if args.root else None)
    result['usb_identity']={'vid':board.vid,'pid':board.pid,'serial':board.serial_number}
    args.evidence.parent.mkdir(parents=True,exist_ok=True)
    args.evidence.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps({k:result[k] for k in ['returncode','elapsed_seconds','pc_network_mutated']}))
    if not args.quiet:print(result['output'])
    raise SystemExit(result['returncode'])

if __name__=='__main__':main()
