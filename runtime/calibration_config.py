"""Explicit, versioned wheel calibration with fail-closed MMIO transactions."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import tempfile
import os

try:
    from . import car_regs as reg
    from .perception_client import ContractError
except ImportError:
    import car_regs as reg
    from perception_client import ContractError

SCHEMA = 'car-wheel-calibration/v1'


@dataclass(frozen=True)
class WheelCalibration:
    scale: int
    direction: int = 0
    filter_ticks: int = 0
    zero_ticks: int = 10_000_000

    def __post_init__(self):
        limits = {'scale': (1, 0xFFFFFFFF), 'direction': (0, 1),
                  'filter_ticks': (0, 1_000_000),
                  'zero_ticks': (66, 19_000_000)}
        for name, (lo, hi) in limits.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
                raise ValueError(f'{name} must be an integer in [{lo}, {hi}]')


@dataclass(frozen=True)
class CalibrationConfig:
    left: WheelCalibration
    right: WheelCalibration
    provenance: str
    measured: bool

    def __post_init__(self):
        if not isinstance(self.left, WheelCalibration) or not isinstance(self.right, WheelCalibration):
            raise ValueError('both wheels require validated calibration')
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError('calibration provenance is required')
        if not isinstance(self.measured, bool):
            raise ValueError('measured must be boolean; nominal is not measured')

    def payload(self):
        return {'schema': SCHEMA, 'contract_version': reg.CONTRACT_VERSION,
                'channel_map': {'left': 'QEI0_left_front', 'right': 'QEI1_right_front'},
                **asdict(self)}

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=path.name+'.', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(json.dumps(self.payload(), indent=2)+'\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path):
        item = json.loads(Path(path).read_text(encoding='utf-8'))
        return cls.from_payload(item)

    @classmethod
    def from_payload(cls, item):
        keys = {'schema', 'contract_version', 'channel_map', 'left', 'right', 'provenance', 'measured'}
        if not isinstance(item, dict) or set(item) != keys or item['schema'] != SCHEMA:
            raise ValueError('invalid calibration schema or fields')
        if item['contract_version'] != reg.CONTRACT_VERSION:
            raise ValueError('calibration contract mismatch')
        if item['channel_map'] != {'left': 'QEI0_left_front', 'right': 'QEI1_right_front'}:
            raise ValueError('calibration wheel mapping mismatch')
        return cls(WheelCalibration(**item['left']), WheelCalibration(**item['right']),
                   item['provenance'], item['measured'])

    def apply(self, client, *, motor_disconnected=False):
        if motor_disconnected is not True:
            raise ValueError('calibration application requires disconnected motors')
        client.verify_contract()
        # Remove the driving lease and invalidate BOTH scales before changing
        # direction/filter. Never leave a partly configured channel usable.
        client.set_command(forward=False, valid=False)
        client.invalidate_qei_scales()
        try:
            expected = {}
            for i, wheel in enumerate((self.left, self.right)):
                for suffix, value in [('DIR', wheel.direction), ('FILTER', wheel.filter_ticks),
                                      ('ZERO', wheel.zero_ticks)]:
                    offset = getattr(reg, f'QEI{i}_{suffix}')
                    expected[offset] = value
                    client.io.write32(offset, value)
            client.configure_qei_scales(self.left.scale, self.right.scale)
            expected.update({reg.QEI0_SCALE: self.left.scale, reg.QEI1_SCALE: self.right.scale})
            for offset, value in expected.items():
                if client.io.read32(offset) != value:
                    raise ContractError(f'calibration readback mismatch at {offset:#x}')
        except Exception as exc:
            cleared, detail = client._clear_qei_scales()
            raise ContractError(f'calibration failed; scales cleared={cleared}; {detail}: {exc}') from exc
        return self.payload()
