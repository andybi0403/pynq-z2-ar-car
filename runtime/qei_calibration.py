"""Pure-software QEI SCALE calculator (interface contract v0.6).

This module only converts mechanical calibration inputs into the Q16.16
``CFG_SCALE`` register value consumed by the PL velocity core
(``floor(scale * 100_000_000 / period_ticks)``).  It never touches MMIO and
never selects a profile on its own; writing the registers is the caller's
explicit decision (see ``perception_client.configure_qei_scales``).

Contract semantics fixed by ``pynq_fpga/nightly/interface_contract.md``:

- ``SCALE`` is unsigned Q16.16, unit: mm per wheel-shaft x4 count.
- The production reset value is 0, meaning "uncalibrated, speed invalid".
  No nominal value may ever become an RTL or register reset default.
- ``SHIFT`` stays 0.

Sources of the nominal presets (verified 2026-09-19 against the vendor
manual ``霍尔编码器TT马达使用手册.pdf``):

- 13-line magnetic ring on the MOTOR shaft, AB quadrature, x4 legal-edge
  counting; counts per OUTPUT wheel revolution = 13 * gear_ratio * 4.
- Vendor STM32 demo (``C25 v5.zip``): gear 1:90, 4680 counts, 60 mm wheel.
- Vendor Arduino demo (``ard-end.zip``): gear 1:90, 4680 counts, 65 mm wheel.
  Both demos are generic examples; they do not override the user-confirmed
  1:48, original-wheel, two-front-motor configuration of this project.
"""
from __future__ import annotations

import math

ENCODER_PPR = 13          # motor-shaft lines (vendor manual, parameter table)
X4_FACTOR = 4             # QEI counts every legal AB transition
Q16_16_ONE = 65536
SCALE_MIN = 1
SCALE_MAX = 0xFFFFFFFF

# Nominal presets keyed by "<gear>_<diameter>".  ``scale`` is the rounded
# Q16.16 value for pi * diameter rollout.  ``TT_48_65MM`` is only the
# first-power-up temporary value for the user-confirmed profile
# TT_48_ORIGINAL_WHEEL_FRONT_2 (crude 65 mm measurement, original tyres);
# it must be replaced after a loaded rollout calibration.
NOMINAL_PRESETS: dict[str, dict] = {}


def counts_per_wheel_rev(gear_ratio: int) -> int:
    """x4 counts for one OUTPUT wheel revolution: 13 * gear_ratio * 4."""
    if isinstance(gear_ratio, bool) or not isinstance(gear_ratio, int):
        raise ValueError("gear_ratio must be an integer reduction ratio, e.g. 48")
    if gear_ratio <= 0:
        raise ValueError("gear_ratio must be positive")
    return ENCODER_PPR * gear_ratio * X4_FACTOR


def validate_wheel_diameter(diameter_mm: float) -> float:
    value = float(diameter_mm)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("wheel diameter must be a positive finite number")
    return value


def scale_from_rollout_mm(rollout_mm: float, counts_per_rev: int) -> int:
    """SCALE for one measured loaded rollout (mm travelled per wheel rev)."""
    rollout = float(rollout_mm)
    if not math.isfinite(rollout) or rollout <= 0:
        raise ValueError("rollout must be a positive finite number")
    if isinstance(counts_per_rev, bool) or not isinstance(counts_per_rev, int) \
            or counts_per_rev <= 0:
        raise ValueError("counts_per_rev must be a positive integer")
    scale = round(rollout / counts_per_rev * Q16_16_ONE)
    if not SCALE_MIN <= scale <= SCALE_MAX:
        raise ValueError(
            f"calculated scale {scale} is outside the register range "
            f"[{SCALE_MIN}, {SCALE_MAX}]"
        )
    return scale


def scale_from_diameter_mm(diameter_mm: float, counts_per_rev: int) -> int:
    """SCALE from a diameter estimate; loaded rollout = pi * diameter.

    Diameter estimates are coarse: prefer ``scale_from_rollout_mm`` with a
    real loaded measurement once the wheels are on the car.
    """
    diameter = validate_wheel_diameter(diameter_mm)
    return scale_from_rollout_mm(math.pi * diameter, counts_per_rev)


def scale_from_measurements(measured_distance_mm: float,
                            measured_wheel_revolutions: float,
                            counts_per_rev: int) -> int:
    """SCALE from a direct loaded calibration run.

    ``measured_distance_mm`` / ``measured_wheel_revolutions`` is the loaded
    rollout per revolution; measure several revolutions per wheel and use
    the wheel's own values (left and right may differ).
    """
    distance = float(measured_distance_mm)
    revolutions = float(measured_wheel_revolutions)
    if not math.isfinite(distance) or distance <= 0:
        raise ValueError("measured distance must be a positive finite number")
    if not math.isfinite(revolutions) or revolutions <= 0:
        raise ValueError("measured revolutions must be a positive finite number")
    return scale_from_rollout_mm(distance / revolutions, counts_per_rev)


def decode_scale(scale: int) -> float:
    """Decode a Q16.16 SCALE back to mm per x4 count."""
    if isinstance(scale, bool) or not isinstance(scale, int) \
            or not SCALE_MIN <= scale <= SCALE_MAX:
        raise ValueError(f"scale must be an integer in [{SCALE_MIN}, {SCALE_MAX}]")
    return scale / Q16_16_ONE


def _preset(name: str, gear_ratio: int, diameter_mm: float, note: str) -> None:
    counts = counts_per_wheel_rev(gear_ratio)
    scale = scale_from_diameter_mm(diameter_mm, counts)
    NOMINAL_PRESETS[name] = {
        "gear_ratio": gear_ratio,
        "wheel_diameter_mm": diameter_mm,
        "counts_per_wheel_rev": counts,
        "scale": scale,
        "scale_hex": f"0x{scale:08X}",
        "note": note,
    }


_preset("TT_48_60MM", 48, 60.0,
        "reference preset; vendor STM32 demo uses 1:90/60mm, not this project")
_preset("TT_48_65MM", 48, 65.0,
        "temporary first-power-up value for TT_48_ORIGINAL_WHEEL_FRONT_2; "
        "65mm is a crude hand measurement, replace after loaded rollout "
        "calibration")
_preset("TT_90_60MM", 90, 60.0,
        "reference preset matching the vendor STM32 demo (C25 v5)")
_preset("TT_90_65MM", 90, 65.0,
        "reference preset matching the vendor Arduino demo (ard-end)")

# Presets are documentation/calculator data only.  No preset here is
# auto-applied: the production path only writes registers through the
# explicit configure calls in perception_client.py.
