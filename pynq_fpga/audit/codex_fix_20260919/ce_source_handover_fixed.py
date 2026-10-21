"""Post-fix oracle for AUD-02-01 using the exported production C helper."""
from __future__ import annotations

import ctypes
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DLL = ROOT / "pynq_fpga" / "host" / "c_build" / "safe_control.dll"


class SafeControl(ctypes.Structure):
    _fields_ = [
        ("sample_ms", ctypes.c_uint32), ("command_ms", ctypes.c_uint32),
        ("clear_ms", ctypes.c_uint32), ("distance_mm", ctypes.c_uint16),
        ("ir", ctypes.c_uint8), ("valid", ctypes.c_uint8),
        ("clear_tracking", ctypes.c_uint8), ("latched", ctypes.c_uint8),
        ("distance_blocked", ctypes.c_uint8), ("command", ctypes.c_uint8),
        ("reason", ctypes.c_uint8), ("speed", ctypes.c_int),
        ("left_req", ctypes.c_int), ("right_req", ctypes.c_int),
        ("drop_count", ctypes.c_uint16),
    ]


def main() -> int:
    lib = ctypes.CDLL(str(DLL))
    lib.safe_init.argtypes = [ctypes.POINTER(SafeControl)]
    lib.safe_source_handover.argtypes = [ctypes.POINTER(SafeControl)]
    lib.safe_pframe.argtypes = [ctypes.POINTER(SafeControl), ctypes.c_char_p,
                                ctypes.c_size_t, ctypes.c_uint32]
    lib.safe_pframe.restype = ctypes.c_int
    lib.safe_frame.argtypes = [ctypes.POINTER(SafeControl), ctypes.c_char_p,
                               ctypes.c_size_t, ctypes.c_uint32]
    lib.safe_frame.restype = ctypes.c_int
    state = SafeControl()
    lib.safe_init(ctypes.byref(state))
    pframe = b"$P,0,0,1,1000,0,0,2E#"
    for now in (1000, 1100, 1200, 1300):
        if lib.safe_pframe(ctypes.byref(state), pframe, len(pframe), now) != 1:
            raise RuntimeError("setup frame rejected")
    if not (state.valid and state.clear_tracking):
        raise RuntimeError("setup did not create a fresh clear snapshot")

    lib.safe_source_handover(ctypes.byref(state))
    stop = b"$0,0,0,0,0,0,0,0,0,0#"
    lib.safe_frame(ctypes.byref(state), stop, len(stop), 1399)
    passed = bool(state.latched and not state.valid and not state.clear_tracking
                  and state.left_req == 0 and state.right_req == 0)
    print({"latched": state.latched, "valid": state.valid,
           "clear_tracking": state.clear_tracking, "reason": state.reason,
           "left_req": state.left_req, "right_req": state.right_req})
    print("SOURCE_HANDOVER_FIX_PASS" if passed else "SOURCE_HANDOVER_FIX_FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
