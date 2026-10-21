"""Host-side contract for the integrated PL perception register bank.

The transport is deliberately small: PYNQ MMIO, a simulator, or a replay
adapter only needs ``read32`` and ``write32``.  Snapshot consistency is
proved with SNAP_EPOCH; STATUS is diagnostic and is not used as a pulse.
"""
from dataclasses import dataclass
try:
    from .qei_quality import snapshot_fault_reasons
except ImportError:
    from qei_quality import snapshot_fault_reasons
from typing import Protocol
import math

try:
    from . import car_regs as reg
    from .qei_calibration import NOMINAL_PRESETS
except ImportError:  # Allow direct execution from pynq_fpga/host.
    import car_regs as reg
    from qei_calibration import NOMINAL_PRESETS


class RegisterIO(Protocol):
    def read32(self, offset: int) -> int: ...
    def write32(self, offset: int, value: int) -> None: ...


class ContractError(RuntimeError):
    pass


class PynqMMIO:
    """Thin RegisterIO adapter for a real PYNQ ``MMIO`` region.

    Import is intentionally delayed until construction so replay/tests run on
    development PCs without pretending that hardware exists.
    """

    def __init__(self, base_addr: int, length: int):
        if base_addr < 0 or length < 4:
            raise ValueError("base_addr must be non-negative and length at least 4 bytes")
        try:
            from pynq import MMIO
        except ImportError as exc:
            raise RuntimeError(
                "PYNQ package is unavailable; --transport pynq requires a PYNQ image"
            ) from exc
        self.base_addr = int(base_addr)
        self.length = int(length)
        self._mmio = MMIO(self.base_addr, self.length)

    def _checked_offset(self, offset: int) -> int:
        offset = int(offset)
        if offset < 0 or offset & 3 or offset + 4 > self.length:
            raise ValueError(
                f"MMIO offset 0x{offset:X} is not an aligned 32-bit access "
                f"inside length 0x{self.length:X}"
            )
        return offset

    def read32(self, offset: int) -> int:
        return int(self._mmio.read(self._checked_offset(offset), 4)) & 0xFFFFFFFF

    def write32(self, offset: int, value: int) -> None:
        self._mmio.write(self._checked_offset(offset), int(value) & 0xFFFFFFFF)


@dataclass(frozen=True)
class Sample:
    data: int
    timestamp: int
    valid: bool
    sequence: int


@dataclass(frozen=True)
class Odometry:
    displacement_q16: int = 0
    travelled_q16: int = 0
    timestamp: int = 0
    valid: bool = False
    fault: bool = False
    epoch: int = 0
    sequence: int = 0


@dataclass(frozen=True)
class PerceptionSnapshot:
    epoch: int
    ultrasonic: Sample
    infrared: Sample
    qei0_position: int
    qei0_period: int
    qei0_velocity_q16: int
    qei0: Sample
    qei1_position: int
    qei1_period: int
    qei1_velocity_q16: int
    qei1: Sample
    risk_state: int
    risk_required_mm: int
    risk: Sample
    command_state: int
    command_timestamp: int
    odometry0: Odometry = Odometry()
    odometry1: Odometry = Odometry()
    qei0_info: int = 0
    qei1_info: int = 0

    @property
    def displacement_q16(self) -> int:
        return (self.odometry0.displacement_q16 + self.odometry1.displacement_q16) // 2

    @property
    def travelled_q16(self) -> int:
        return (self.odometry0.travelled_q16 + self.odometry1.travelled_q16) // 2

    @property
    def odometry_valid(self) -> bool:
        return all(o.valid and not o.fault for o in (self.odometry0, self.odometry1))


@dataclass(frozen=True)
class SafetyDecision:
    permit: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class LinkSample:
    """Sensor fields for ``CarLink.update_sample``.

    This deliberately excludes the driving request. Polling PL sensors must
    never renew the independent driving lease.
    """
    valid: bool
    distance_mm: int
    infrared_mask: int


def _signed32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


# Channel semantics frozen for the two-front-encoder configuration:
# QEI0 = LEFT FRONT wheel, QEI1 = RIGHT FRONT wheel.  Both wheels of one
# vehicle side share one TB6612 direction/PWM pair, so the front encoder is
# the per-side speed observation; the rear motors have no encoder and no
# independent feedback.
PROFILE_TT_48_ORIGINAL_WHEEL_FRONT_2 = "TT_48_ORIGINAL_WHEEL_FRONT_2"

# Explicit profile table.  The temporary nominal values come from the
# calculator's TT_48_65MM preset (1:48, crude 65 mm diameter, 2496 x4
# counts/wheel rev) and MUST be replaced by the measured left/right loaded
# rollout calibration.  Profiles are data only: nothing writes registers at
# import time, at construction time, or in replay mode.
QEI_SCALE_PROFILES: dict[str, dict] = {
    PROFILE_TT_48_ORIGINAL_WHEEL_FRONT_2: {
        "left_scale": NOMINAL_PRESETS["TT_48_65MM"]["scale"],
        "right_scale": NOMINAL_PRESETS["TT_48_65MM"]["scale"],
        "temporary": True,
        "channel_map": {"QEI0": "left_front", "QEI1": "right_front"},
        "note": (
            "1:48 gearing confirmed; original tyres; 65mm is a crude hand "
            "measurement. Replace both scales with the measured per-side "
            "loaded rollout after arrival checks."
        ),
    },
}


def _validated_qei_scale(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not 1 <= value <= 0xFFFFFFFF:
        raise ValueError(
            f"{name} must be in [1, 0xFFFFFFFF]; 0 means uncalibrated and "
            "cannot be written as a scale"
        )
    return value


def elapsed32(now: int, then: int) -> int:
    """Unsigned 32-bit elapsed ticks, valid across one counter wrap."""
    return (now - then) & 0xFFFFFFFF


class PerceptionClient:
    def __init__(self, io: RegisterIO, snapshot_attempts: int = 4):
        if snapshot_attempts < 1:
            raise ValueError("snapshot_attempts must be positive")
        self.io = io
        self.snapshot_attempts = snapshot_attempts

    def verify_contract(self) -> None:
        actual = self.io.read32(reg.ID_VERSION) & 0xFFFFFFFF
        if actual != reg.INTEGRATED_ID:
            raise ContractError(
                f"PL register contract mismatch: got 0x{actual:08X}, "
                f"expected 0x{reg.INTEGRATED_ID:08X}"
            )

    def _clear_qei_scales(self) -> tuple[bool, str]:
        """Best-effort fail-safe clear used after a configuration fault.

        SCALE=0 is the hardware contract's explicit uncalibrated state.  Both
        writes and both readbacks are attempted even if one access fails so a
        single broken channel cannot prevent the other from being disabled.
        """
        errors = []
        for name, offset in (("left", reg.QEI0_SCALE), ("right", reg.QEI1_SCALE)):
            try:
                self.io.write32(offset, 0)
            except Exception as exc:  # transport implementations define their own errors
                errors.append(f"{name} clear write failed: {exc}")
        for name, offset in (("left", reg.QEI0_SCALE), ("right", reg.QEI1_SCALE)):
            try:
                value = self.io.read32(offset) & 0xFFFFFFFF
                if value != 0:
                    errors.append(f"{name} clear readback was 0x{value:08X}")
            except Exception as exc:
                errors.append(f"{name} clear read failed: {exc}")
        return not errors, "; ".join(errors) if errors else "both SCALE registers read back 0"

    def invalidate_qei_scales(self) -> None:
        """Explicitly put both QEI channels in the uncalibrated state."""
        self.verify_contract()
        cleared, detail = self._clear_qei_scales()
        if not cleared:
            raise ContractError(f"could not invalidate both QEI scales: {detail}")

    def configure_qei_scales(self, left_scale: int, right_scale: int) -> tuple[int, int]:
        """Explicitly write QEI0/QEI1 ``CFG_SCALE`` and verify the readback.

        QEI0 is the left front wheel, QEI1 the right front wheel.  The reset
        value 0 means "uncalibrated, speed invalid"; this call is the only
        sanctioned way to leave that state, and it must be invoked
        deliberately by the operator (never at import/construction or inside
        replay).

        Validation contract: both scales must be integers in
        [1, 0xFFFFFFFF].  The integrated contract ID is verified first; on
        any mismatch, invalid value or readback difference an error is raised
        and the caller must NOT grant motion permission afterwards.  A write
        or readback fault triggers a best-effort clear of both SCALE registers
        to the fail-safe uncalibrated value 0.  If that clear cannot be fully
        verified, the ``ContractError`` says so and a bitstream reload is
        required before QEI speeds may be trusted.

        Returns the readback ``(left_scale, right_scale)``.
        """
        self.verify_contract()
        left = _validated_qei_scale(left_scale, "left_scale")
        right = _validated_qei_scale(right_scale, "right_scale")
        try:
            self.io.write32(reg.QEI0_SCALE, left)
            self.io.write32(reg.QEI1_SCALE, right)
            read_left = self.io.read32(reg.QEI0_SCALE) & 0xFFFFFFFF
            read_right = self.io.read32(reg.QEI1_SCALE) & 0xFFFFFFFF
            if read_left != left or read_right != right:
                raise ContractError(
                    "QEI scale readback mismatch: "
                    f"left wrote 0x{left:08X} read 0x{read_left:08X}, "
                    f"right wrote 0x{right:08X} read 0x{read_right:08X}"
                )
        except Exception as exc:
            cleared, detail = self._clear_qei_scales()
            state = "both channels invalidated" if cleared else f"cleanup incomplete: {detail}"
            raise ContractError(f"QEI scale configuration failed; {state}: {exc}") from exc
        return read_left, read_right

    def configure_qei_profile(self, profile_name: str) -> tuple[int, int]:
        """Apply one named QEI scale profile (temporary nominal values).

        Unknown profile names raise ``ContractError`` without writing any
        register.  Later per-side measured calibration overrides these
        values through ``configure_qei_scales``.
        """
        if profile_name not in QEI_SCALE_PROFILES:
            raise ContractError(
                f"unknown QEI scale profile: {profile_name!r}; "
                f"known profiles: {sorted(QEI_SCALE_PROFILES)}"
            )
        scales = QEI_SCALE_PROFILES[profile_name]
        return self.configure_qei_scales(
            scales["left_scale"], scales["right_scale"]
        )

    def set_command(self, *, forward: bool, valid: bool) -> None:
        # Every write renews the hardware command lease, including STOP.
        self.io.write32(reg.RISK_CMD, int(forward) | (int(valid) << 1))

    def configure_qei_filters(self, left_ticks: int, right_ticks: int, *, motor_disconnected=False):
        """Explicit uncalibrated LAB setup; never silently replace calibration."""
        if motor_disconnected is not True:
            raise ValueError('QEI filtering requires disconnected motor power')
        for value in (left_ticks, right_ticks):
            if type(value) is not int or not 0 <= value <= 1_000_000:
                raise ValueError('QEI filter must be an integer in 0..1000000 ticks')
        self.verify_contract()
        if self.io.read32(reg.QEI0_SCALE) or self.io.read32(reg.QEI1_SCALE):
            raise ContractError('apply a complete calibration to change a configured QEI filter')
        self.disable_risk_permit()
        try:
            for offset, value in ((reg.QEI0_FILTER, left_ticks), (reg.QEI1_FILTER, right_ticks)):
                self.io.write32(offset, value)
            if (self.io.read32(reg.QEI0_FILTER), self.io.read32(reg.QEI1_FILTER)) != (left_ticks, right_ticks):
                raise ContractError('QEI filter readback mismatch')
        except Exception:
            self.invalidate_qei_scales()
            raise
        return left_ticks, right_ticks

    def disable_risk_permit(self) -> None:
        self.io.write32(reg.RISK_ENABLE, 0)

    def read_pl_ticks64(self, poll_attempts: int = 8) -> int:
        """Atomically latch and read the PL timebase.

        PS monotonic time is never mixed with these ticks. STATUS.bit1 is a
        level-style completion indication; a missing completion is fail-safe.
        """
        if poll_attempts < 1:
            raise ValueError("poll_attempts must be positive")
        self.io.write32(reg.CTRL, 2)
        for _ in range(poll_attempts):
            if self.io.read32(reg.STATUS) & 2:
                lo = self.io.read32(reg.TS_SNAP_LO) & 0xFFFFFFFF
                hi = self.io.read32(reg.TS_SNAP_HI) & 0xFFFFFFFF
                return (hi << 32) | lo
        raise ContractError("PL time latch did not complete")

    def _sample(self, data_offset: int, ts_offset: int, meta_offset: int) -> Sample:
        meta = self.io.read32(meta_offset)
        return Sample(
            data=self.io.read32(data_offset) & 0xFFFFFFFF,
            timestamp=self.io.read32(ts_offset) & 0xFFFFFFFF,
            valid=bool(meta & 0x80000000),
            sequence=meta & 0xFFFF,
        )

    def snapshot(self) -> PerceptionSnapshot:
        for _ in range(self.snapshot_attempts):
            before = self.io.read32(reg.SNAP_EPOCH) & 0xFFFF
            self.io.write32(reg.CTRL, 1)
            epoch = self.io.read32(reg.SNAP_EPOCH) & 0xFFFF
            if epoch == before:
                continue

            us = self._sample(reg.US_DATA, reg.US_TS, reg.US_META)
            ir = self._sample(reg.IR_STATUS, reg.IR_TS, reg.IR_META)
            q0 = self._sample(reg.QEI0_VEL, reg.QEI0_TS, reg.QEI0_META)
            q1 = self._sample(reg.QEI1_VEL, reg.QEI1_TS, reg.QEI1_META)
            risk = self._sample(reg.RISK_STATE, reg.RISK_TS, reg.RISK_META)
            result = PerceptionSnapshot(
                epoch=epoch,
                ultrasonic=us,
                infrared=ir,
                qei0_position=_signed32(self.io.read32(reg.QEI0_POS)),
                qei0_period=self.io.read32(reg.QEI0_PERIOD) & 0xFFFFFFFF,
                qei0_velocity_q16=_signed32(q0.data),
                qei0=q0,
                qei1_position=_signed32(self.io.read32(reg.QEI1_POS)),
                qei1_period=self.io.read32(reg.QEI1_PERIOD) & 0xFFFFFFFF,
                qei1_velocity_q16=_signed32(q1.data),
                qei1=q1,
                risk_state=risk.data,
                risk_required_mm=self.io.read32(reg.RISK_REQUIRED_MM) & 0xFFFFFFFF,
                risk=risk,
                command_state=self.io.read32(reg.CMD_STATE) & 0x3,
                command_timestamp=self.io.read32(reg.CMD_TS) & 0xFFFFFFFF,
                odometry0=self._odometry(0),
                odometry1=self._odometry(1),
                qei0_info=self.io.read32(reg.QEI0_INFO) & 0xFFFFFFFF,
                qei1_info=self.io.read32(reg.QEI1_INFO) & 0xFFFFFFFF,
            )
            after = self.io.read32(reg.SNAP_EPOCH) & 0xFFFF
            if after == epoch:
                return result
        raise ContractError("global snapshot did not become stable")

    def _odometry(self, channel: int) -> Odometry:
        def read(suffix):
            return self.io.read32(getattr(reg, f"ODOM{channel}_{suffix}")) & 0xFFFFFFFF
        displacement = read("DISP_LO") | (read("DISP_HI") << 32)
        if displacement & (1 << 63):
            displacement -= 1 << 64
        travelled = read("PATH_LO") | (read("PATH_HI") << 32)
        meta = read("META")
        return Odometry(displacement, travelled, read("TS"),
                        bool(meta & 0x80000000), bool(meta & 0x40000000),
                        read("EPOCH") & 0xFFFF, meta & 0xFFFF)

    def reset_odometry(self) -> None:
        """Explicit reset; caller must stop motors before requesting this."""
        self.verify_contract()
        shot = self.snapshot()
        now = self.read_pl_ticks64() & 0xFFFFFFFF
        if any(not q.valid or elapsed32(now, q.timestamp) >= DATA_MAX_AGE_TICKS
               or _signed32(q.data) != 0 for q in (shot.qei0, shot.qei1)):
            raise ContractError("odometry reset requires fresh zero wheel velocities")
        before = (shot.odometry0.epoch, shot.odometry1.epoch)
        self.io.write32(reg.ODOM_CTRL, 1)
        for _ in range(self.snapshot_attempts):
            after = self.snapshot()
            pair = (after.odometry0, after.odometry1)
            if all(o.epoch == ((e + 1) & 0xFFFF) and o.displacement_q16 == 0
                   and o.travelled_q16 == 0 for o, e in zip(pair, before)):
                return
        raise ContractError("odometry reset did not read back a new zero epoch")

    def publish_car_status(self, car: dict | None, age_s: float | None) -> None:
        """Display-only UART feedback. Call once per new CAR reception."""
        valid = (car is not None and age_s is not None and math.isfinite(age_s)
                 and 0 <= age_s < 0.7)
        if valid:
            lock, fault = car.get("lock"), car.get("fault")
            if type(lock) is not int or lock not in (0, 1) or type(fault) is not int or not 0 <= fault <= 65535:
                raise ValueError("invalid CAR display fields")
            age = min(70_000_000, math.ceil(age_s * 100_000_000))
            word = (fault << 16) | 2 | lock
        else:
            age, word = 70_000_000, 0
        self.io.write32(reg.DISPLAY_CAR_AGE, age)
        self.io.write32(reg.DISPLAY_CAR_STATE, word)

    def display_diagnostics(self) -> dict:
        for _ in range(self.snapshot_attempts):
            before=self.io.read32(reg.DISPLAY_TAG_COUNT)&0xffffffff
            result={name:self.io.read32(getattr(reg,name))&0xffffffff for name in
                    ('OSD_ERRORS','DISPLAY_FRAMES','DISPLAY_CAR_STATE','DISPLAY_CAR_TS',
                     'DISPLAY_FRAME_ID','DISPLAY_FRAME_STATE','DISPLAY_FRAME_TS_LO','DISPLAY_FRAME_TS_HI',
                     'DISPLAY_HEADER_ERRORS','DISPLAY_REPEATS','DISPLAY_FRAME_AGE',
                     'DISPLAY_FRAME_SOF_LO','DISPLAY_FRAME_SOF_HI')}
            after=self.io.read32(reg.DISPLAY_TAG_COUNT)&0xffffffff
            if before==after:
                result['DISPLAY_TAG_COUNT']=after
                return result
        raise ContractError('display frame identity changed during diagnostic read')

    def sample_and_decide(self) -> tuple[int, PerceptionSnapshot, SafetyDecision]:
        """Read one stable snapshot and conservatively decide forward permit."""
        self.verify_contract()
        shot = self.snapshot()
        now = self.read_pl_ticks64() & 0xFFFFFFFF
        return now, shot, evaluate_snapshot(shot, now)


DATA_MAX_AGE_TICKS = 20_000_000
COMMAND_LEASE_TICKS = 25_000_000


def snapshot_to_link_sample(
    shot: PerceptionSnapshot,
    now_ticks: int,
    *,
    data_max_age_ticks: int = DATA_MAX_AGE_TICKS,
) -> LinkSample:
    """Preserve P-frame sensor semantics without folding in drive permission.

    A valid IR obstacle remains ``V=1, IR!=0`` so the STM32 records
    ``FAULT_IR``. QEI/risk/command failures stop driving via ``SafetyDecision``
    but do not relabel a valid distance/IR observation as a sensor failure.
    """
    us_fault = (shot.ultrasonic.data >> 12) & 0xF
    us_fresh = (
        shot.ultrasonic.valid
        and elapsed32(now_ticks, shot.ultrasonic.timestamp) < data_max_age_ticks
        and us_fault == 0
    )
    ir_usable = shot.infrared.valid and bool(shot.infrared.data & 0x4)
    return LinkSample(
        valid=bool(us_fresh and ir_usable),
        distance_mm=shot.ultrasonic.data & 0xFFF,
        infrared_mask=shot.infrared.data & 0x3,
    )


def evaluate_snapshot(
    shot: PerceptionSnapshot,
    now_ticks: int,
    *,
    data_max_age_ticks: int = DATA_MAX_AGE_TICKS,
    command_lease_ticks: int = COMMAND_LEASE_TICKS,
) -> SafetyDecision:
    """Fail-safe host interpretation of one v0.6 global snapshot.

    IR_TS is a state-change timestamp, so it is deliberately not subjected to
    periodic sample aging. IR validity/stability and obstacle bits are checked.
    """
    reasons: list[str] = []

    def require_fresh(name: str, sample: Sample) -> None:
        if not sample.valid:
            reasons.append(f"{name}_invalid")
        elif elapsed32(now_ticks, sample.timestamp) >= data_max_age_ticks:
            reasons.append(f"{name}_stale")

    require_fresh("us", shot.ultrasonic)
    require_fresh("qei0", shot.qei0)
    require_fresh("qei1", shot.qei1)
    for channel in (0, 1):
        reasons.extend(f'qei{channel}_{reason}' for reason in snapshot_fault_reasons(shot, channel))
    require_fresh("risk", shot.risk)
    if not shot.infrared.valid or not (shot.infrared.data & 0x4):
        reasons.append("ir_invalid")
    if shot.infrared.data & 0x3:
        reasons.append("ir_obstacle")
    if not (shot.command_state & 0x2):
        reasons.append("command_invalid")
    elif elapsed32(now_ticks, shot.command_timestamp) >= command_lease_ticks:
        reasons.append("command_stale")

    risk_reasons = (shot.risk_state >> 16) & 0xFFFF
    if shot.risk_state & 1:
        reasons.append("risk_stop")
    if risk_reasons & (1 << 13):
        reasons.append("wheel_direction")
    return SafetyDecision(permit=not reasons, reasons=tuple(reasons))
