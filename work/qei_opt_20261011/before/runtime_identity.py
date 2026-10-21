"""Identify the package, loaded runtime modules and explicit calibration."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

RUNTIME_FILES=tuple(name+'.py' for name in (
    'lab_acceptance','board_runtime','frame_pipeline','overlay_session','frame_association',
    'system_runtime','control_supervisor','calibration_config','status_server','association_metrics',
    'joint_evidence','hwh_contract','perception_client','qei_calibration','perception_replay','car_regs',
    'pynq_link','runtime_identity','frame_metadata','deployment_check'))


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def runtime_hashes():
    result={}
    for filename in RUNTIME_FILES:
        name=filename[:-3]
        module=sys.modules.get(name)
        origin=getattr(module,'__file__',None)
        if origin is None:
            spec=importlib.util.find_spec(name)
            origin=None if spec is None else spec.origin
        if origin is None or not Path(origin).is_file():raise ValueError(f'missing runtime module {name}')
        result[filename]=sha256(origin)
    return result


def session_identity(bit,hwh,manifest,calibration):
    package=json.loads(Path(manifest).read_text(encoding='utf-8-sig'))
    code=runtime_hashes()
    if code!=package.get('runtime_files'):raise ValueError('loaded runtime code differs from verified package')
    return {'bit_sha256':sha256(bit),'hwh_sha256':sha256(hwh),
            'manifest_sha256':sha256(manifest),'runtime_sources':code,'calibration':calibration,
            'build_parameters':package.get('build_parameters')}


def expected_identity_from_package(directory, calibration_file):
    """Derive the expected identity from verified files, never from a journal.

    This path runs offline and hashes packaged sources rather than this
    auditor's installed modules. PYNQ/serial hardware is not opened.
    """
    from lab_acceptance import verify_package
    from calibration_config import CalibrationConfig
    folder=Path(directory)
    bit=folder/'task7_8_LAB_ONLY.bit'
    hwh=folder/'task7_8_LAB_ONLY.hwh'
    manifest=folder/'lab_manifest.json'
    package=verify_package(bit,hwh,manifest)
    calibration=CalibrationConfig.load(calibration_file)
    return {'bit_sha256':sha256(bit),'hwh_sha256':sha256(hwh),
            'manifest_sha256':sha256(manifest),
            'runtime_sources':{name:sha256(folder/name) for name in RUNTIME_FILES},
            'calibration':calibration.payload(),
            'build_parameters':package.get('build_parameters')}
