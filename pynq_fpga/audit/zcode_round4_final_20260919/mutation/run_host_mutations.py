# -*- coding: utf-8 -*-
"""round4主机层变异：V1版本检查移除/V2 epoch复核移除/V3 PS时间替换PL时间/V4 IR置V=0。
对perception_client.py副本注入，用discover三套件(32项)判定。基线V0必须OK。"""
import shutil, subprocess, sys, tempfile, pathlib, re
ROOT = pathlib.Path(r"C:\Users\39909\Desktop\FPGA")
def run_case(tag, patch):
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"hostmut5_{tag}_"))
    try:
        host = work / "host"
        shutil.copytree(ROOT / "pynq_fpga" / "host", host,
                        ignore=shutil.ignore_patterns("__pycache__", "c_build"))
        (host / "c_build").mkdir()
        shutil.copy(ROOT / "pynq_fpga" / "host" / "c_build" / "safe_control.dll",
                    host / "c_build" / "safe_control.dll")
        shutil.copy(ROOT / "stm32预备程序" / "pc" / "pynq_link.py", host / "pynq_link.py")
        (host / "tests" / "test_architecture_invariants.py").unlink()
        (host / "tests" / "test_register_generator.py").unlink()
        pc = host / "perception_client.py"
        src = pc.read_text(encoding="utf-8")
        if patch:
            assert patch[0] in src, f"pattern missing: {tag}"
            src = src.replace(patch[0], patch[1], 1)
        pc.write_text(src, encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests",
                            "-p", "test_*.py"], cwd=str(host), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        m = re.search(r"Ran (\d+) tests.*?(OK|FAILED)", out, re.S)
        return (m.group(1), m.group(2)) if m else ("?", "?")
    finally:
        shutil.rmtree(work, ignore_errors=True)

CASES = [
    ("V0_baseline", None, "OK"),
    ("V1_remove_version_check",
     ("if actual != reg.INTEGRATED_ID:", "if False and actual != reg.INTEGRATED_ID:"), "FAILED"),
    ("V2_remove_epoch_recheck",
     ("if after == epoch:", "if True or after == epoch:"), "FAILED"),
    ("V3_ps_minus_pl_time",
     ("now = self.read_pl_ticks64() & 0xFFFFFFFF", "now = 20000000"), "FAILED"),
    ("V4_ir_to_v0",
     ("valid=bool(us_fresh and ir_usable),", "valid=False,"), "FAILED"),
]
for tag, patch, expect in CASES:
    n, v = run_case(tag, patch)
    print(("  ok " if v == expect else "  UNEXPECTED"), f"{tag}: ran={n} verdict={v} (expect {expect})")
