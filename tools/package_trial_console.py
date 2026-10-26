"""Separate trial envelope; keep every r12 base source/hash/classification intact."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'v010_ground_trial_20261026_r14'
BASE = 'v010_locked_resync_20261026_r12'
FILES = ('trial_control.py', 'trial_runtime.py', 'trial_page.html', 'start_trial_console.sh')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    release = ROOT/'pynq_fpga/release'
    out = release/NAME
    if out.exists() or out.with_suffix('.zip').exists():
        raise FileExistsError('immutable trial candidate already exists')
    base = release/BASE
    shutil.copytree(base, out, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'evidence'))
    for name in FILES:
        shutil.copy2(ROOT/'pynq_fpga/preintegration/host'/name, out/name)
    manifest = {'schema':'car-ground-trial/v1', 'classification':'CONTROLLED_TRIAL_CANDIDATE_NOT_RELEASE',
                'name':NAME, 'base':BASE, 'base_manifest_sha256':digest(base/'lab_manifest.json'),
                'files':{name:digest(out/name) for name in FILES},
                'limits':{'pwm':400, 'burst_s':1.0, 'intent_lease_ms':250, 'scheduling_fault_ms':100},
                'video_enabled':False, 'automatic_release':False,
                'calibration':'No nominal defaults. Physical measured calibration remains required.',
                'hardware_result':'PENDING', 'production_release_approved':False}
    (out/'trial_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', 'utf8')
    with zipfile.ZipFile(out.with_suffix('.zip'), 'x', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(out).as_posix())
    print(json.dumps({'name':NAME, 'manifest_sha256':digest(out/'trial_manifest.json'),
                      'zip_sha256':digest(out.with_suffix('.zip'))}))


if __name__ == '__main__':
    main()
