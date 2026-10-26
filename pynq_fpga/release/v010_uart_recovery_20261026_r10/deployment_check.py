"""Read-only deployment prerequisites; never download an Overlay or open UART."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

if sys.version_info<(3,10):
    raise SystemExit('Deployment runtime requires Python 3.10 or newer; check python3 --version first')
import importlib.metadata

HERE=Path(__file__).resolve().parent


def inspect(directory,*,board=False,camera='/dev/video0',uart='/dev/ttyPS1'):
    from lab_acceptance import verify_package
    folder=Path(directory)
    package=verify_package(folder/'task7_8_LAB_ONLY.bit',folder/'task7_8_LAB_ONLY.hwh',folder/'lab_manifest.json')
    failures=[]
    if sys.version_info<(3,10):failures.append('Python 3.10 or newer required by runtime annotations')
    dependencies={}
    if board:
        if sys.platform!='linux':failures.append('board deployment requires the PYNQ Linux environment')
        wireless=package.get('video_profile')=='wireless720'
        required=[('pynq','pynq'),('numpy','numpy'),('serial','pyserial')]
        if wireless:required.append(('aiohttp','aiohttp'))
        for module,distribution in required:
            exists=importlib.util.find_spec(module) is not None
            try:version=importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:version=None
            dependencies[module]={'available':exists,'version':version}
            if not exists:failures.append(f'missing board dependency {module}')
        ffmpeg=shutil.which('ffmpeg')
        dependencies['ffmpeg']={'path':ffmpeg}
        if ffmpeg is None and not wireless:failures.append('FFmpeg is missing')
        elif ffmpeg is not None and not wireless:
            try:
                result=subprocess.run([ffmpeg,'-version'],capture_output=True,text=True,timeout=3)
                if result.returncode:failures.append('FFmpeg version probe failed')
                dependencies['ffmpeg']['version_line']=result.stdout.splitlines()[0] if result.stdout else None
            except (OSError,subprocess.TimeoutExpired):failures.append('FFmpeg version probe failed or timed out')
        if wireless:
            native=folder/'native-build/libcar_video.so'
            dependencies['native_video']={'path':str(native),'available':native.is_file()}
            if not native.is_file():failures.append('build pinned ARM libcar_video.so before wireless startup')
        for label,name in [('camera',camera),('uart',uart)]:
            available=Path(name).exists() and os.access(name,os.R_OK|os.W_OK)
            dependencies[label]={'path':name,'accessible':available}
            if not available:failures.append(f'{label} device missing or inaccessible: {name}')
    return {'schema':'car-deployment-check/v1','passed':not failures,'failures':failures,
            'contract_id':package['integrated_id'],'board_prerequisites_checked':board,
            'hardware_acceptance':'PENDING','overlay_loaded':False,'serial_opened':False,
            'python':platform.python_version(),'machine':platform.machine(),'dependencies':dependencies}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,default=HERE)
    parser.add_argument('--board',action='store_true')
    parser.add_argument('--camera',default='/dev/video0');parser.add_argument('--uart',default='/dev/ttyPS1')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        result=inspect(args.directory,board=args.board,camera=args.camera,uart=args.uart)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print('DEPLOYMENT_CHECK_'+('PASS' if result['passed'] else 'FAIL')+' '+json.dumps(result))
        raise SystemExit(0 if result['passed'] else 1)
    except (OSError,ValueError) as exc:
        print(f'DEPLOYMENT_CHECK_INVALID: {exc}',file=sys.stderr);raise SystemExit(1)
