"""Independent matrix-convolution oracle, from the forward-overlay contract.

Image computations operate on full arrays, rather than mirroring RTL buffers.
Sobel centre (x-1,y-1) is painted at (x,y), documenting the causal 1px phase.
"""
from pathlib import Path

GREEN,YELLOW,RED,FAULT=0x00d060,0xffd000,0xff2020,0xd020ff
FONT_PATH=Path(__file__).resolve().parents[2]/'fpga/rtl/font_8x8_status.mem'


def apply_front(pixels,width=640,height=480,valid=True,distance_valid=True,
                distance_mm=1000,risk=0,stop=False,threshold=160,previous_bbox=None,return_envelope=False):
    if len(pixels)!=width*height:raise ValueError('frame dimensions mismatch')
    out=list(pixels)
    color=GREEN
    gray=[((p>>16&255)+2*(p>>8&255)+(p&255))//4 for p in pixels]
    x0,x1,y0,y1=width//4,3*width//4,height//4,3*height//4
    kernels=[((-1,0,1),(-2,0,2),(-1,0,1)),((1,2,1),(0,0,0),(-1,-2,-1))]
    edges=[]
    for y in range(y0,y1):
        for x in range(x0,x1):
            edge=False
            if x0+2<=x<x1-2 and y0+2<=y<y1-2:
                values=[[gray[(y-2+j)*width+x-2+i] for i in range(3)] for j in range(3)]
                gradients=[sum(values[j][i]*kernel[j][i] for j in range(3) for i in range(3)) for kernel in kernels]
                edge=sum(map(abs,gradients))>=threshold
            if edge:
                out[y*width+x]=color
                edges.append((x,y))
    if return_envelope:
        return (min(x for x,y in edges),min(y for x,y in edges)) if edges else None
    if previous_bbox is not None:
        from hud_font_ref import text
        label='前方测距:'+('~'+f'{distance_mm//10:03d}' if valid and distance_valid else '无效  ')+' cm'
        x,y=previous_bbox
        text(out,width,height,min(x,width-192),max(0,y-20),label,color)
    return out


def edge_envelope(pixels,width=640,height=480,threshold=160):
    # Matrix convolution independently defines the gradient envelope.
    return apply_front(pixels,width,height,threshold=threshold,return_envelope=True)


def pattern(frame,x,y):
    if frame==0:return 0x112233
    if frame==1:return 0xf0f0f0 if 220<=x<410 and 165<=y<300 else 0x182030
    if frame==2:return ((x*3+y*5)&255)*0x010101
    if frame==3:return 0xffffff if ((x//8+y//8)&1) else 0
    if frame==4:return ((x*17+y*31)&255)<<16|((x*11+y*7)&255)<<8|((x*5+y*23)&255)
    return 0xffffff if x==320 or y==240 else 0


CASES=[dict(distance_mm=0,risk=0),dict(distance_mm=1234,risk=2),
       dict(distance_mm=4095,risk=1),dict(distance_mm=999,risk=0,stop=True),
       dict(distance_mm=2500,risk=0,distance_valid=False),
       dict(distance_mm=1800,risk=0,valid=False)]
