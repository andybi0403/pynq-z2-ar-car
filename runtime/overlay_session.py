"""Verified Overlay attachment and an OS lock for the single device owner.

    A matching filename is insufficient if files were replaced in place.
    Attachment also checks our recorded hashes and PYNQ's device timestamp.
    State files are evidence of identity, never evidence of a live process;
    process ownership uses an operating-system lock, released on exit/crash.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def artifact_identity(bitfile, hwhfile):
    def digest(path):
        h = hashlib.sha256()
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    return {"bit_path": str(Path(bitfile).resolve()),
            "bit_sha256": digest(bitfile), "hwh_sha256": digest(hwhfile)}


def _pynq_loaded_state():
    # PYNQ 3.x saves a generation timestamp before programming, then gives the
    # local Device a different timestamp in post_download. PL.timestamp favors
    # that local value, so use the persistent generation consistently in every
    # process. The SDK boot check rejects a record left across a cold start.
    try:
        from pynq.pl_server.global_state import (
            initial_global_state_file_boot_check, global_state_file_exists,
            load_global_state,
        )
    except ImportError:
        from pynq import PL
        return PL.bitfile_name, PL.timestamp
    initial_global_state_file_boot_check()
    if not global_state_file_exists():
        return None, None
    state = load_global_state()
    return state.bitfile_name, state.timestamp


def _pynq_record_download(overlay):
    # 3.0.1 skips gen_cache() for cached metadata, leaving even the previous
    # file's global identity behind. Publish the completed programming event
    # through the SDK, including the memory and shutdown metadata it requires.
    try:
        from pynq.pl_server.global_state import GlobalState, save_global_state
    except ImportError:
        return
    parser = overlay.parser
    state = GlobalState(bitfile_name=overlay.bitfile_name,
                        active_name=overlay.device.name,
                        timestamp=overlay.device.timestamp,
                        psddr=parser.mem_dict.get("PSDDR", {}))
    for name, details in parser.ip_dict.items():
        if details["type"] in (
            "xilinx.com:ip:pr_axi_shutdown_manager:1.0",
            "xilinx.com:ip:dfx_axi_shutdown_manager:1.0",
        ):
            state.add(name=name, addr=details["phys_addr"])
    save_global_state(state)


class DeviceLease:
    """Nonblocking process lock; a leftover file never means a live owner."""
    def __init__(self, path=None):
        self.path = Path(path or Path(tempfile.gettempdir()) / "pynq_car_device.lock")
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0)
                if self.path.stat().st_size == 0:
                    self.stream.write(b"0")
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            self.stream = None
            raise RuntimeError("another process owns the car Overlay/UART session") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.stream is not None:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close()
            self.stream = None
        return False


def open_verified_overlay(bitfile, hwhfile, *, download=None,
                          overlay_factory=None, state_path=None,
                          loaded_state_reader=None):
    """Auto: reuse a verified matching load; download only when not loaded.

    download=False strictly attaches. download=True explicitly reloads and
    resets all PL calibration/leases. Caller must hold DeviceLease throughout
    hardware use; this helper intentionally does not release ownership early.
    Custom factories must provide a reader returning the live (path, timestamp).
    """
    identity = artifact_identity(bitfile, hwhfile)
    production_factory = overlay_factory is None
    if overlay_factory is None:
        try:
            from pynq import Overlay
        except ImportError as exc:
            raise RuntimeError("PYNQ package unavailable; run on PYNQ-Z2") from exc
        overlay_factory = Overlay
        if loaded_state_reader is None:
            loaded_state_reader = _pynq_loaded_state
    if loaded_state_reader is None:
        raise ValueError("custom Overlay factory requires a live loaded-state reader")

    def live_state():
        path, timestamp = loaded_state_reader()
        return (str(Path(path).resolve()) if path else None,
                str(timestamp) if timestamp else None)

    state_path = Path(state_path or Path(tempfile.gettempdir()) / "pynq_car_overlay_identity.json")
    # PYNQ 3.0.1's constructor sets device.bitfile_name even with download=False.
    # Read the active identity first; is_loaded() after construction alone can
    # therefore claim a requested file is loaded without programming it.
    before = live_state()
    overlay = overlay_factory(str(Path(bitfile).resolve()), download=False)
    loaded = (before[0] == identity["bit_path"] and before[1] is not None
              and overlay.is_loaded())
    if download is True or (download is None and not loaded):
        overlay.download()
        if production_factory:
            _pynq_record_download(overlay)
        after = live_state()
        if after[0] != identity["bit_path"] or after[1] is None or not overlay.is_loaded():
            raise RuntimeError("Overlay download/attachment could not be verified")
        identity["device_timestamp"] = after[1]
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(identity, sort_keys=True), encoding="utf-8")
        temporary.replace(state_path)
    else:
        if not loaded:
            raise RuntimeError("requested Overlay is not loaded; attachment refused")
        try:
            recorded = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("loaded Overlay identity is missing; explicit reload required") from exc
        identity["device_timestamp"] = before[1]
        if recorded != identity:
            raise RuntimeError("loaded Overlay hashes/timestamp differ; explicit reload required")
        if live_state() != before:
            raise RuntimeError("loaded Overlay changed during attachment; explicit reload required")
    if not overlay.is_loaded():
        raise RuntimeError("Overlay download/attachment could not be verified")
    return overlay
