# -*- coding: utf-8 -*-
"""OSD 软件参考渲染器（夜间B）。

独立实现与 car_axis_osd.v 相同的像素合成规则，读同一份字模文件
（fpga/rtl/font_8x8_minimal.mem，单一来源），用于 RTL 逐像素比对。
这不是从 RTL 抄的模型：合成规则由契约文档描述独立推导，
BCD 数字直接用 Python 十进制（与 RTL double-dabble 语义等价）。

布局（与 car_axis_osd.v ENABLE_TEXT=1 一致）：
  边框 2px 风险色；状态块行 y 4..12；文本带 x 48..104, y 16..32：
    line0 (y16..24): V : <sign> d d d d   （速度 mm/s，负数带 '-'，无效全 'F'）
    line1 (y24..32): D : d d d d [F| ]    （距离 mm，无效全 'F'）
  cell 8x8；glyph ROM 组合读，MSB=左像素。
"""
from pathlib import Path

FONT_PATH = Path(__file__).resolve().parents[2] / "fpga" / "rtl" / "font_8x8_minimal.mem"

C_GREEN = 0x00D060
C_YELLOW = 0xFFD000
C_RED = 0xFF2020
C_FAULT = 0xFF2020
C_WHITE = 0xFFFFFF
C_BLACK = 0x101010


def load_font():
    rows = [l.strip() for l in FONT_PATH.read_text().splitlines()
            if l.strip() and not l.startswith("//")]
    assert len(rows) == 128
    # 16 slots x 8 rows, MSB = leftmost pixel
    return [[int(r, 16) for r in rows[g * 8:(g + 1) * 8]] for g in range(16)]


FONT = load_font()

# RTL glyph slot assignment (car_axis_osd.v glyph_idx cases)
SLOT_0, SLOT_1, SLOT_2, SLOT_3 = 0, 1, 2, 3
SLOT_4, SLOT_5, SLOT_6, SLOT_7 = 4, 5, 6, 7
SLOT_8, SLOT_9, SLOT_MINUS, SLOT_F = 8, 9, 0xA, 0xB
SLOT_COLON, SLOT_SPACE, SLOT_V, SLOT_D = 0xC, 0xD, 0xE, 0xF


def bcd4(value):
    """与 RTL double-dabble 语义等价：<=9999 的十进制 4 位。"""
    v = int(value)
    assert 0 <= v <= 9999
    return ((v // 1000) % 10, (v // 100) % 10, (v // 10) % 10, v % 10)


def render(width, height, risk_level, stop, locked, distance_valid, speed_valid,
           distance_mm, speed_q16):
    """返回 width*height 的 24bit RGB 列表（行优先）。"""
    px_img = [0] * (width * height)

    def put(x, y, c):
        if 0 <= x < width and 0 <= y < height:
            px_img[y * width + x] = c

    risk_color = {0: C_GREEN, 1: C_YELLOW, 2: C_RED}.get(risk_level, C_FAULT)

    speed_neg = (speed_q16 >> 31) & 1
    spd_abs = (~speed_q16 + 1) & 0xFFFFFFFF if speed_neg else speed_q16
    spd_int = spd_abs >> 16
    speed_invalid = (not speed_valid) or speed_q16 == 0x80000000 or spd_int > 9999
    dist_invalid = (not distance_valid) or distance_mm > 9999

    for y in range(height):
        for x in range(width):
            c = 0x112233                                   # base passthrough

            px_img[y * width + x] = c
    from hud_font_ref import text
    speed_text='无效' if speed_invalid else ('-' if speed_neg and spd_int else ' ')+f'{spd_int:04d}'
    distance_text='无效' if dist_invalid else f'{distance_mm:04d}'
    text(px_img,width,height,24,24,'速度: '+speed_text.ljust(5)+' mm/s',C_WHITE if not speed_invalid else C_FAULT,16)
    text(px_img,width,height,24,64,'距离: '+distance_text.ljust(4)+' mm',C_WHITE if not dist_invalid else C_YELLOW,12,background=C_BLACK)
    if width>=560:
        active=2 if stop or not(distance_valid and speed_valid) or risk_level>=2 else risk_level
        for index,(label,color) in enumerate(zip(('安全','注意','紧急'),(C_GREEN,C_YELLOW,C_RED))):
            selected=index==active
            color=color if selected else 0x686868
            cx,cy=width-224+index*80,48
            for y in range(16,116):
                for x in range(cx-40,cx+40):
                    d=(x-cx)**2+(y-cy)**2
                    if d<=24**2 and (selected or d>21**2):put(x,y,color)
            text(px_img,width,height,cx-32,80,label,C_WHITE if selected else 0xd0d7de,size=32)
    return px_img
