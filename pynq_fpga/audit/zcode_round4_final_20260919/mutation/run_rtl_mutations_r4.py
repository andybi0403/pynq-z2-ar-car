# -*- coding: utf-8 -*-
"""round4 RTL变异：R1快照漏锁US组、R2 epoch在time_latch也递增。
对car_perception_top.v副本注入，用tb_car_perception_arch(33项)判定。"""
import shutil, subprocess, sys, tempfile, pathlib, re
ROOT = pathlib.Path(r"C:\Users\39909\Desktop\FPGA")
RTL = ROOT / "pynq_fpga" / "fpga" / "rtl"
TB = ROOT / "pynq_fpga" / "fpga" / "tb"
AX = ROOT / "pynq_fpga" / "third_party" / "verilog-axi" / "rtl"
VIV = r"C:\AMDDesignTools\2026.1\Vivado\bin"
rtl = (RTL / "car_perception_top.v").read_text(encoding="utf-8")
SRCS = ([str(AX / n) for n in ("axil_reg_if.v", "axil_reg_if_rd.v", "axil_reg_if_wr.v")] +
        [str(RTL / n) for n in ("car_time_counter.v", "car_snapshot.v", "car_ultrasonic.v", "car_ir.v",
         "car_sensors_core.v", "car_qei.v", "car_qei_velocity.v", "car_qei_core.v", "car_risk_core.v")])
MUTS = {
    "R1_snapshot_miss_us": ("快照漏锁US组",
        "s_us_data<=us_data;s_us_ts<=us_ts;s_us_meta<={us_valid,15'b0,us_seq};s_us_err<={16'b0,us_err};", ""),
    "R2_epoch_early": ("epoch在time_latch时也递增",
        "if(time_latch)begin time_lo<=ticks[31:0];time_hi<=ticks[63:32];end",
        "if(time_latch)begin time_lo<=ticks[31:0];time_hi<=ticks[63:32];snap_epoch<=snap_epoch+1'b1;end"),
}
for tag, (note, pat, rep) in MUTS.items():
    n = rtl.count(pat)
    if n != 1:
        print(f"{tag}: PATTERN count={n}"); continue
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"r4_{tag}_"))
    try:
        (work / "car_perception_top.v").write_text(rtl.replace(pat, rep, 1), encoding="utf-8")
        shutil.copy(TB / "tb_car_perception_arch.sv", work / "tb_car_perception_arch.sv")
        def sh(cmd): return subprocess.run(cmd, cwd=str(work), capture_output=True, text=True)
        r1 = sh([VIV + r"\xvlog.bat", "-sv", "-i", str(RTL)] + SRCS +
                [str(work / "car_perception_top.v"), str(work / "tb_car_perception_arch.sv")])
        if r1.returncode: print(f"{tag} COMPILE-FAIL"); continue
        r2 = sh([VIV + r"\xelab.bat", "tb_car_perception_arch", "-debug", "typical", "-s", "r4sim"])
        if r2.returncode: print(f"{tag} ELAB-FAIL"); continue
        sh([VIV + r"\xsim.bat", "r4sim", "-runall", "--log", "xsim_console.log"])
        text = (work / "xsim_console.log").read_text(errors="ignore")
        if "TEST PASSED" in text:
            m = re.search(r"TEST PASSED \((\d+) checks\)", text)
            print(f"{tag} [{note}] -> SURVIVED (PASSED {m.group(1)} checks)")
        elif "TEST FAILED" in text:
            m = re.search(r"TEST FAILED \((\d+) errors\)", text)
            first = re.search(r"\[FAIL\] ([^\n]*)", text)
            print(f"{tag} [{note}] -> KILLED ({m.group(1)} errors; first: {first.group(1)[:60] if first else '?'})")
        else:
            print(f"{tag} [{note}] -> KILLED (watchdog)")
    finally:
        shutil.rmtree(work, ignore_errors=True)
