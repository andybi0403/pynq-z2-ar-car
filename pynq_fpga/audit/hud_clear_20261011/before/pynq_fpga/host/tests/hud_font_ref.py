"""String-based Chinese HUD oracle, independent of RTL glyph selectors."""
import json
from pathlib import Path

RTL = Path(__file__).resolve().parents[2]/'fpga/rtl'
CHARS = json.loads((RTL/'font_16x16_hud.json').read_text(encoding='utf-8'))['chars']
FONT = [int(row,16) for row in (RTL/'font_16x16_hud.mem').read_text().splitlines()]

def text(pixels,width,height,x,y,label,color,columns=None):
    label=label.ljust(columns or len(label))
    for column,char in enumerate(label):
        glyph=CHARS.index(char)
        for yy in range(16):
            bits=FONT[glyph*16+yy]
            for xx in range(16):
                px,py=x+column*16+xx,y+yy
                if 0<=px<width and 0<=py<height:
                    pixels[py*width+px]=color if bits & (1<<(15-xx)) else 0x101010
