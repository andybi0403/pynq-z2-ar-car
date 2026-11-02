"""Check actual wrapper output at independent, meaningful map coordinates."""
from pathlib import Path
import argparse,hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('simulation',type=Path);args=parser.parse_args()
directory=args.simulation.resolve()
log=(directory/'xsim_console.log').read_text('utf8')
assert 'TEST PASSED' in log and 'TEST FAILED' not in log and '[FAIL]' not in log
checks=int(re.search(r'TEST PASSED \((\d+) checks\)',log)[1])
evidence=[]
for number in range(1,5):
    path=directory/f'display_chain_f{number}.rgb'
    pixels=path.read_text('ascii').splitlines()
    assert len(pixels)==1280*720,(number,len(pixels))
    # Centres lie outside the Sobel ROI, text, car glyph, wheels and risk lamp.
    expected=(0x00b870,0xff3030,0x00b870) if number<4 else (0x112233,)*3
    for (x,y),value in zip(((1132,525),(1072,550),(1192,550)),expected):
        assert int(pixels[y*1280+x],16)==value,(number,x,y,pixels[y*1280+x],value)
    # Corners of the former square zones now show only darkened background.
    if number<4:
        background=sum((((0x112233>>shift)&255)//4+((0x112233>>shift)&255)//8+8)<<shift for shift in (0,8,16))
        for x,y in ((1040,530),(1220,530)):
            assert int(pixels[y*1280+x],16)==background,(number,x,y)
    evidence.append({'frame':number,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
result={'pass':True,'geometry':[1280,720],'frames':4,'wrapper_checks':checks,
        'map_output_checked':True,'stale_map_disabled':True,'outputs':evidence,
        'simulation_log':str(directory/'xsim_console.log'),
        'scope':'production wrapper simulation; not board validation'}
inputs=[*(ROOT/'pynq_fpga/fpga/rtl').glob('*.v'),*(ROOT/'pynq_fpga/fpga/rtl').glob('*.vh'),
        *(ROOT/'pynq_fpga/fpga/rtl').glob('*.mem'),ROOT/'pynq_fpga/fpga/tb/tb_car_board_video_wrapper.sv']
result['sources']={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
(ROOT/'validation/tactical_chain_gate.json').write_text(json.dumps(result,indent=2),'utf8')
print(json.dumps(result))
