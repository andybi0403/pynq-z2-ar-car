"""Independent string/decimal pixel oracle for the additional RTL OSD rows."""
from pathlib import Path
import argparse
import json

FONT = Path(__file__).resolve().parents[2]/'fpga/rtl/font_8x8_status.mem'
GLYPHS = {str(i):i for i in range(10)} | {'-':10,'F':11,':':12,' ':13,
         'V':14,'D':15,'A':16,'B':17,'C':18,'E':19,'R':20,'L':21,'M':22,'S':23,'P':24,'+':25}
CASES = [
 [('M:12345678',True),('D:-00000042',True),('R:A05F',True),('L:1 F:1234',True),('P:-',True)],
 [('M:FFFFFFFF',False),('D:FFFFFFFFF',False),('R:0E13',True),('L:F F:FFFF',False),('P:F',False)],
 [('M:00000000',True),('D:+00000000',True),('R:0000',True),('L:0 F:0000',True),('P:0',True)],
 [('M:FFFFFFFF',False),('D:FFFFFFFFF',False),('R:0000',True),('L:0 F:0000',True),('P:+',True)],
]


def expected_pixels(lines, width=480, height=320):
    from hud_font_ref import text
    path,net,reasons,car,direction=lines
    path_label='路程: '+(path[0][2:] if path[1] else '无效'.ljust(8))+' mm'
    net_label='位移: '+(net[0][2:] if net[1] else '无效'.ljust(9))+' mm'
    car_label='锁车: '+(('是' if car[0][2]=='1' else '否') if car[1] else '无效')
    fault_label='故障码: '+('0x'+car[0][6:10] if car[1] else '无效')
    direction_label='方向: '+({'0':'停','+':'正','-':'反'}[direction[0][2]] if direction[1] else '无效')
    labels=[(path_label,path[1]),(net_label,net[1]),('原因码: 0x'+reasons[0][2:],True),
            (car_label,car[1]),(fault_label,car[1]),(direction_label,direction[1])]
    pixels=[0x112233]*(width*height)
    for row,(label,valid) in enumerate(labels):
        text(pixels,width,height,24,104+32*row,label,0xffffff if valid else 0xe0e0e0,16)
    return pixels


def compare(directory):
    for i,case in enumerate(CASES,1):
        actual=[int(row,16) for row in (Path(directory)/f'status_f{i}.rgb').read_text().splitlines()]
        expected=expected_pixels(case)
        if len(actual)!=len(expected):
            raise AssertionError(f'frame {i} pixel count {len(actual)} != {len(expected)}')
        bad=[index for index,(a,b) in enumerate(zip(actual,expected)) if a!=b]
        if bad:
            p=bad[0];raise AssertionError(f'frame {i}: {len(bad)} pixel mismatches, first ({p%480},{p//480}): {actual[p]:06x} != {expected[p]:06x}')
    return {'frames':len(CASES),'pixels':len(CASES)*480*320,'mismatches':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--rtl-dir',type=Path,required=True)
    args=parser.parse_args();print('STATUS_OSD_PIXEL_PASS '+json.dumps(compare(args.rtl_dir)))
