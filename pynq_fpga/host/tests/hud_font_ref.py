"""String-based Chinese HUD oracle, independent of RTL glyph selectors."""
import json
from pathlib import Path

RTL = Path(__file__).resolve().parents[2]/'fpga/rtl'
CHARS = json.loads((RTL/'font_16x16_hud.json').read_text(encoding='utf-8'))['chars']
FONT = [int(row,16) for row in (RTL/'font_16x16_hud.mem').read_text().splitlines()]

FONTS={size:[int(row,16) for row in (RTL/f'font_{size}x{size}_hud.mem').read_text().splitlines()] for size in (24,32)}

def text(pixels,width,height,x,y,label,color,columns=None,background=None,size=24):
    label=label.ljust(columns or len(label))
    for column,char in enumerate(label):
        glyph=CHARS.index(char)
        for yy in range(size):
            word=FONTS[size][glyph*32+yy]
            bits=word>>size
            outline=word&((1<<size)-1)
            for xx in range(size):
                px,py=x+column*size+xx,y+yy
                if 0<=px<width and 0<=py<height:
                    mask=1<<(size-1-xx)
                    if bits&mask:pixels[py*width+px]=color
                    elif background is not None:pixels[py*width+px]=background
                    elif outline&mask:pixels[py*width+px]=0x101010
