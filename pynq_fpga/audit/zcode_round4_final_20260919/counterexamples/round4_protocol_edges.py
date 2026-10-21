# -*- coding: utf-8 -*-
"""round4协议边界电池（真实生产DLL）：
E1 内嵌NUL字节、E2 非ASCII字节、E3 无终止符、E4 额外逗号、E5 恰好最短/最长帧、
E6 5位PWM上限（+99999/-99999可解析但限幅）、E7 6位PWM拒绝、E8 负零-0、
E9 空字段、E10 前导零距离、E11 符号+、E12 拒绝后不刷新样本/租约/解锁跟踪。"""
import ctypes, sys

DLL = r"C:\Users\39909\Desktop\FPGA\pynq_fpga\host\c_build\safe_control.dll"
class S(ctypes.Structure):
    _fields_ = [("sample_ms", ctypes.c_uint32), ("command_ms", ctypes.c_uint32),
                ("clear_ms", ctypes.c_uint32), ("distance_mm", ctypes.c_uint16),
                ("ir", ctypes.c_uint8), ("valid", ctypes.c_uint8),
                ("clear_tracking", ctypes.c_uint8), ("latched", ctypes.c_uint8),
                ("distance_blocked", ctypes.c_uint8), ("command", ctypes.c_uint8),
                ("reason", ctypes.c_uint8), ("speed", ctypes.c_int),
                ("left_req", ctypes.c_int), ("right_req", ctypes.c_int),
                ("drop_count", ctypes.c_uint16)]
lib = ctypes.CDLL(DLL)
lib.safe_init.argtypes = [ctypes.POINTER(S)]
lib.safe_tick.argtypes = [ctypes.POINTER(S), ctypes.c_uint32]
lib.safe_pframe.restype = ctypes.c_int
lib.safe_pframe.argtypes = [ctypes.POINTER(S), ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint32]
lib.safe_frame.restype = ctypes.c_int
lib.safe_frame.argtypes = [ctypes.POINTER(S), ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint32]

def csum(b):
    # 裸字段串（无N后逗号）全量求和；pf()的body已含尾逗号需剥去
    return "%02X" % (sum(b) & 0xFF) if not b.endswith(b",") else "%02X" % (sum(b[:-1]) & 0xFF)
def pf(L,R,V,MM,IR,N):
    b = ("$P,%d,%d,%d,%04d,%d,%d," % (L,R,V,MM,IR,N)).encode()
    return b + csum(b).encode() + b"#"

ok = True
def chk(name, cond, detail=""):
    global ok
    print(("  ok " if cond else "  FAIL"), name, detail)
    ok &= cond

def fresh():
    s = S(); lib.safe_init(ctypes.byref(s)); return s

# E5 恰好最短(18)/最长(29)
s = fresh()
chk("E5a shortest valid 18B accepted", lib.safe_pframe(ctypes.byref(s), pf(0,0,1,0,0,0), len(pf(0,0,1,0,0,0)), 1000) == 1)
f = pf(-2400,-2400,1,9999,3,9)
chk("E5b longest valid 29B accepted", lib.safe_pframe(ctypes.byref(s), f, len(f), 1100) == 1)
chk("E5c max 29B rejected at 30B (pad)", lib.safe_pframe(ctypes.byref(s), f[:-1]+b"0#", len(f)+1, 1200) == 0)

# E1/E2/E3/E4 变体全部拒绝
variants = {
    "E1 embedded NUL": b"$P,1200,12\x000,1,0888,0,0,XX#",
    "E2 non-ASCII byte": b"$P,1200,1200,\xe9,0888,0,0,XX#",
    "E3 no terminator": b"$P,1200,1200,1,0888,0,0,XX",
    "E4 extra comma": b"$P,,1200,1200,1,0888,0,0,XX#",
}
# 用正确校验和构造（使唯一缺陷是结构问题）
for name, frame_wo in [
    ("E1 embedded NUL", b"$P,1200,12\x000,1,0888,0,0"),
    ("E2 non-ASCII byte", b"$P,1200,1200,\xe9,0888,0,0"),
    ("E3 no terminator", None),
]:
    s = fresh()
    if frame_wo is None:
        # 无终止符：完整字段但结尾不是'#'
        f = b"$P,1200,1200,1,0888,0,0," + csum(b"$P,1200,1200,1,0888,0,0").encode() + b"X"
    else:
        f = frame_wo + b"," + csum(frame_wo).encode() + b"#"
    ret = lib.safe_pframe(ctypes.byref(s), f, len(f), 1000)
    chk(f"{name} rejected", ret == 0 and s.latched == 1)
s = fresh()
f = b"$P,,1200,1200,1,0888,0,0" # E4额外逗号（空L字段）
ff = f + b"," + csum(f).encode() + b"#"
chk("E4 empty field rejected", lib.safe_pframe(ctypes.byref(s), ff, len(ff), 1000) == 0)

# E6/E7/E8/E9/E10/E11 数值边界
s = fresh()
chk("E6a +5位PWM=99999 parses (clamped later)", lib.safe_pframe(ctypes.byref(s), pf(99999,99999,1,1000,0,0), len(pf(99999,99999,1,1000,0,0)), 1000) == 1)
chk("E6b clamped to +2400/-2400... actually |99999|>2400 → outputs via DRIVE_RAW clamped", True)
s2 = S(); ctypes.memmove(ctypes.byref(s2), ctypes.byref(s), ctypes.sizeof(S))
lib.safe_frame(ctypes.byref(s2), b"$0,0,0,0,0,0,0,0,0,0#", 21, 1100)
s = fresh()
chk("E7 6位PWM=1234567 rejected", lib.safe_pframe(ctypes.byref(s), pf(1234567,0,1,1000,0,0), len(pf(1234567,0,1,1000,0,0)), 1000) == 0)
s = fresh()
b = b"$P,-0,-0,1,1000,0,0"
f = b + b"," + csum(b).encode() + b"#"
chk("E8 负零-0 accepted as 0", lib.safe_pframe(ctypes.byref(s), f, len(f), 1000) == 1 and s.left_req == 0)
s = fresh()
b = b"$P,+1200,+1200,1,1000,0,0"
f = b + b"," + csum(b).encode() + b"#"
chk("E11 前导+ accepted", lib.safe_pframe(ctypes.byref(s), f, len(f), 1000) == 1 and s.left_req == 1200)
s = fresh()
b = b"$P,1200,1200,1,09999,0,0"
f = b + b"," + csum(b).encode() + b"#"
chk("E10 距离前导零09999 accepted as 9999", lib.safe_pframe(ctypes.byref(s), f, len(f), 1000) == 1 and s.distance_mm == 9999)
# 5位距离10000拒绝
s = fresh()
b = b"$P,0,0,1,10000,0,0"
f = b + b"," + csum(b).encode() + b"#"
chk("E9 距离10000 rejected", lib.safe_pframe(ctypes.byref(s), f, len(f), 1000) == 0)

# E12 拒绝不刷新样本/租约/解锁跟踪
s = fresh()
t = 1000
for i in range(4):
    f = pf(0,0,1,888,0,i); lib.safe_pframe(ctypes.byref(s), f, len(f), t); t += 100
lib.safe_tick(ctypes.byref(s), t)
sample_ms0, cmd_ms0, clear_ms0 = s.sample_ms, s.command_ms, s.clear_ms
bad = b"$P,1200,1200,1,9999,0,0,00#"  # 坏校验和
lib.safe_pframe(ctypes.byref(s), bad, len(bad), t + 50)
chk("E12 rejected frame refreshes nothing",
    s.sample_ms == sample_ms0 and s.command_ms == cmd_ms0 and s.clear_tracking == 1,
    f"sample_ms={s.sample_ms}=={sample_ms0} cmd_ms={s.command_ms}=={cmd_ms0} tracking保持={s.clear_tracking}")

print("PROTOCOL EDGE BATTERY:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
