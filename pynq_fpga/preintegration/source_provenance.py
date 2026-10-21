"""Bind a routed candidate and its artifacts to the actual build inputs."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import os

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def current_identity():
    directories = ['fpga/rtl', 'fpga/tb', 'fpga/registers', 'fpga/board',
                   'preintegration/rtl', 'preintegration/tb',
                   'preintegration/constraints', 'preintegration/vivado',
                   'preintegration/board_repo', 'third_party/verilog-axi/rtl',
                   'third_party/PYNQ/boards/ip', 'fpga/scripts', 'host',
                   'preintegration/host', 'preintegration/tests', 'preintegration/camera', 'preintegration/native']
    extensions = {'.v', '.sv', '.vh', '.mem', '.json', '.tcl', '.xdc', '.xml', '.vhd', '.coe',
                  '.py', '.ps1', '.cmd', '.c', '.h', '.s', '.ld', '.html', '.txt', '.cmake', '.js', '.jsonl'}
    files = [Path(__file__).resolve()]
    files.append(ROOT/'host/c_build/build_car_c_dll.ps1')
    files.extend(p for p in ROOT.joinpath('preintegration').iterdir()
                 if p.is_file() and p.suffix.lower() in {'.py','.ps1'})
    for directory in directories:
        files.extend(p for p in (ROOT/directory).rglob('*')
                     if p.is_file() and p.suffix.lower() in extensions
                     and not p.is_relative_to(ROOT/'host/c_build'))
    sources={p.relative_to(ROOT).as_posix():sha256(p) for p in sorted(set(files))}
    # Capture authoritative C/PC inputs, not generated DLL/build-identity files.
    for child in ROOT.parent.iterdir():
        if not child.is_dir():continue
        external=[]
        if (child/'tests/run_tests.cmd').is_file():
            external.extend(p for p in child.iterdir()
                            if p.is_file() and p.suffix.lower() in {'.c','.h','.s','.ld','.ps1','.cmd'})
            for directory in ('Source','tests'):
                external.extend(p for p in (child/directory).rglob('*')
                                if p.is_file() and p.suffix.lower() in {'.c','.h','.cmd','.s'})
        if (child/'pc/pynq_link.py').is_file():external.extend((child/'pc').glob('*.py'))
        for path in sorted(set(external)):
            sources['workspace/'+path.relative_to(ROOT.parent).as_posix()]=sha256(path)
    spec = json.loads((ROOT/'fpga/registers/register_map.json').read_text(encoding='utf-8'))
    risk = (ROOT/'fpga/rtl/car_risk_core.v').read_text(encoding='utf-8').split(')(', 1)[0]
    params = {name: int(value.replace('_','')) for name, value in
              re.findall(r'parameter\s+integer\s+(\w+)\s*=\s*([0-9_]+)', risk)}
    if len(params) != 7:
        raise ValueError('cannot identify all production risk parameters')
    # Production uses the core defaults. Reject newly introduced overrides
    # rather than publishing a misleading parameter list.
    production = (ROOT/'fpga/rtl/car_perception_top.v').read_text(encoding='utf-8')
    if re.search(r'car_risk_core\s*#', production):
        raise ValueError('risk parameter overrides require explicit provenance support')
    firmware_roots = [p for p in ROOT.parent.iterdir() if p.is_dir() and p.name.startswith('stm32_pynq')]
    if len(firmware_roots) != 1:
        raise ValueError('expected one authoritative hybrid STM32 firmware')
    firmware = {name: sha256(firmware_roots[0]/'build_safe'/('safe_car.'+name))
                for name in ('hex', 'bin', 'elf')}
    return {'schema': 'car-build-source/v1', 'sensor_source': 'stm32_uart_v3',
            'stm32_firmware': firmware, 'integrated_id': spec['integrated_id'],
            'contract_version': spec['contract_version'], 'tick_hz': 100_000_000,
            'risk_parameters': params,
            'video_profile': os.environ.get('PYNQ_VIDEO_PROFILE','hdmi640'),
            'sources': sources}


def check(path):
    captured = json.loads(Path(path).read_text(encoding='utf-8'))
    if captured != current_identity():
        raise ValueError('build inputs changed or candidate contract is stale; rebuild required')
    return captured


def bind(source, bit, hwh, output):
    identity = check(source)
    payload = {'schema': 'car-built-artifacts/v1', 'source_identity': identity,
               'artifacts': {key: {'file': Path(path).name, 'sha256': sha256(path)}
                             for key, path in [('bit',bit), ('hwh',hwh)]}}
    Path(output).write_text(json.dumps(payload, indent=2)+'\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--capture', type=Path)
    group.add_argument('--check', type=Path)
    group.add_argument('--bind', type=Path)
    parser.add_argument('--bit', type=Path)
    parser.add_argument('--hwh', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.capture:
        args.capture.parent.mkdir(parents=True, exist_ok=True)
        args.capture.write_text(json.dumps(current_identity(), indent=2)+'\n', encoding='utf-8')
    elif args.check:
        check(args.check)
    else:
        if not all((args.bit,args.hwh,args.output)):
            parser.error('--bind requires --bit, --hwh and --output')
        bind(args.bind,args.bit,args.hwh,args.output)
    print('SOURCE_PROVENANCE_PASS')


if __name__ == '__main__':
    main()
