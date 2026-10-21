"""Compare every actual production RTL pixel to independent Sobel math."""
import argparse,json
from pathlib import Path
from front_overlay_ref import apply_front,pattern,CASES


def compare(directory):
    results=[]
    for frame,case in enumerate(CASES):
        pixels=[pattern(frame,x,y) for y in range(480) for x in range(640)]
        expected=apply_front(pixels,**case)
        actual=[int(v,16) for v in (directory/f'front_f{frame}.rgb').read_text().splitlines()]
        if len(actual)!=len(expected):raise AssertionError(f'frame {frame}: wrong pixel count {len(actual)}')
        bad=[i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b]
        if bad:
            i=bad[0];raise AssertionError(f'frame {frame}: {len(bad)} mismatches first ({i%640},{i//640}) {actual[i]:06x}!={expected[i]:06x}')
        results.append(dict(frame=frame,pixels=len(actual),mismatches=0))
    return dict(scope='production RTL simulation, not physical HDMI',cases=results,total_pixels=sum(r['pixels'] for r in results))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--rtl-dir',required=True,type=Path)
    args=p.parse_args();result=compare(args.rtl_dir)
    (args.rtl_dir/'front_compare.json').write_text(json.dumps(result,indent=2)+'\n')
    print('FRONT_OVERLAY_PIXEL_PASS '+json.dumps(result))
