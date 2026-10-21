"""Generate native-size HUD glyphs and optional one-pixel glyph outlines."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
CHARS = '0123456789- :+~ms/cxABCDEF速度距离路程位移原因码锁车故障方向无效前测正反停是否安全注意紧急'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--font', type=Path, required=True)
    p.add_argument('--size', type=int, choices=(16,24,32), default=16)
    args = p.parse_args()
    chars = list(dict.fromkeys(CHARS))
    assert len(chars) <= 64
    size=args.size
    stride=16 if size==16 else 32
    font = ImageFont.truetype(str(args.font), size-2)
    if b'SemiBold' in font.get_variation_names():
        font.set_variation_by_name(b'SemiBold')
    rows = []
    for char in chars:
        im = Image.new('L', (size,size))
        draw = ImageDraw.Draw(im)
        box = draw.textbbox((0,0),char,font=font)
        draw.text(((size-(box[2]-box[0]))//2-box[0],(size-(box[3]-box[1]))//2-box[1]),char,font=font,fill=255)
        mask=im.point(lambda value:255 if value>=100 else 0)
        expanded=mask.filter(ImageFilter.MaxFilter(3))
        for y in range(stride):
            fg=outline=0
            if y<size:
                fg=sum(bool(mask.getpixel((x,y))) << (size-1-x) for x in range(size))
                outline=sum(bool(expanded.getpixel((x,y))) << (size-1-x) for x in range(size)) & ~fg
            rows.append(fg if size==16 else (fg<<size)|outline)
    rows += [0] * (64*stride-len(rows))
    basename=f'font_{size}x{size}_hud'
    word_digits=4 if size==16 else size//2
    (ROOT/f'rtl/{basename}.mem').write_text(''.join(f'{r:0{word_digits}x}\n' for r in rows), encoding='ascii')
    (ROOT/f'rtl/{basename}.json').write_text(json.dumps(dict(chars=chars, size=size,
        row_stride=stride, weight='SemiBold', threshold=100,
        planes='foreground' if size==16 else 'foreground_high_outline_low',
        font_sha256=hashlib.sha256(args.font.read_bytes()).hexdigest(),
        font_name='Noto Sans SC', license='SIL OFL 1.1',
        source='https://github.com/google/fonts/tree/main/ofl/notosanssc'), ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__ == '__main__':
    main()
