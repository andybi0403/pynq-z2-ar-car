"""Compare production metadata/dual-OSD chain against independent pixel oracles."""
import argparse
import json
from pathlib import Path
from osd_ref_render import render
from compare_status_osd import expected_pixels
from front_overlay_ref import apply_front


def compare(directory):
    cases=[(dict(risk_level=2,stop=1,locked=1,distance_valid=1,speed_valid=1,
                 distance_mm=1000,speed_q16=0xffff0000),
            [('M:00000003',True),('D:-00000002',True),('R:0201',True),('L:1 F:1234',True),('P:-',True)]),
           (dict(risk_level=0,stop=0,locked=0,distance_valid=1,speed_valid=1,
                 distance_mm=750,speed_q16=7*65536),
            [('M:00000099',True),('D:+00000042',True),('R:0E13',True),('L:0 F:0000',True),('P:+',True)])]
    cases.append(cases[1])  # repeated VDMA picture carries identical historical state
    cases.append((dict(risk_level=0,stop=0,locked=0,distance_valid=0,speed_valid=0,
                       distance_mm=750,speed_q16=7*65536),
                  [('M:FFFFFFFF',False),('D:FFFFFFFFF',False),('R:FFFF',True),('L:0 F:0000',True),('P:F',False)]))
    for number,(base,lines) in enumerate(cases,1):
        expected=render(640,480,**base)
        raw=[0xf0f0f0 if number==1 and 220<=x<410 and 165<=y<300 else 0x112233
             for y in range(480) for x in range(640)]
        front=apply_front(raw,distance_mm=base['distance_mm'],risk=2 if number==1 else 0,stop=number==1,valid=number!=4)
        # Existing base OSD alters only its own marks; otherwise forward overlay flows through.
        baseline=render(640,480,risk_level=base['risk_level'],stop=base['stop'],locked=base['locked'],distance_valid=base['distance_valid'],speed_valid=base['speed_valid'],distance_mm=base['distance_mm'],speed_q16=base['speed_q16'])
        expected=[a if a!=0x112233 else b for a,b in zip(baseline,front)]
        overlay=expected_pixels(lines,width=640,height=480)
        expected=[second if second!=0x112233 else first for first,second in zip(expected,overlay)]
        actual=[int(line,16) for line in (Path(directory)/f'display_chain_f{number}.rgb').read_text().splitlines()]
        if len(actual)!=640*480:raise AssertionError('full display frame missing pixels')
        bad=[index for index,(a,b) in enumerate(zip(actual,expected)) if a!=b]
        if bad:
            index=bad[0]
            raise AssertionError(f'frame {number}: {len(bad)} mismatches; first x={index%640},y={index//640}: {actual[index]:06x} != {expected[index]:06x}')
    return {'frames':4,'pixels':4*640*480,'mismatches':0,'scope':'production RTL stream, not physical HDMI'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--rtl-dir',type=Path,required=True)
    args=parser.parse_args();print('FRAME_DISPLAY_CHAIN_PIXEL_PASS '+json.dumps(compare(args.rtl_dir)))
