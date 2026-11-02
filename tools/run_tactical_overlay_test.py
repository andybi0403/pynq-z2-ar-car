"""Full720 production RTL against independent geometry/string rendering."""
from pathlib import Path
import subprocess,shutil,json,hashlib
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'pynq_fpga'
B=ROOT/'build/tactical_overlay_gate';B.mkdir(parents=True,exist_ok=True)
shutil.copy2(P/'fpga/rtl/font_24x24_demo.mem',B)
cases=[(1,1,608,3,1,1,0,1),(1,1,250,3,2,1,1,1),(1,1,350,3,3,1,2,1),
       (1,0,0,0,0,0,0,0),(1,0,0,2,0,0,3,1),(0,1,608,3,1,1,0,1),(1,1,4095,3,0,0,0,1)]
calls='\n'.join(f' frame({i},{",".join(str(x) for x in c)});' for i,c in enumerate(cases))
tb=r'''`timescale 1ns/1ps
module tb_tactical;
reg clk=0;always #5 clk=~clk;reg rst=1;
reg [23:0] sd=0;reg sv=0,su=0,sl=0,mr=0;
wire sr,mv,mu,ml;wire [23:0] md;
reg en=0,dv=0,tv=0,iv=0;reg [11:0] distance=0;reg [1:0] samples=0,trend=0,ir=0;
integer received=0,fh=0,seed=746,errors=0;reg held=0;reg [25:0] held_word;
car_axis_tactical dut(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tvalid(sv),.s_axis_tready(sr),
 .s_axis_tuser(su),.s_axis_tlast(sl),.m_axis_tdata(md),.m_axis_tvalid(mv),.m_axis_tready(mr),
 .m_axis_tuser(mu),.m_axis_tlast(ml),.state_enabled(en),.state_filter_valid(dv),
 .state_distance_mm(distance),.state_sample_count(samples),.state_trend(trend),.state_trend_valid(tv),
 .state_ir(ir),.state_ir_valid(iv));
always @(negedge clk)if(!rst)mr=($random(seed)&3)!=0;
always @(posedge clk)if(!rst)begin
 if(held&&(!mv||{md,mu,ml}!==held_word))$fatal(1,"held payload");
 held=mv&&!mr;held_word={md,mu,ml};
 if(mv&&mr&&fh!=0)begin
  if(mu!==(received==0)||ml!==((received%1280)==1279))$fatal(1,"geometry markers");
  $fwrite(fh,"%06x\n",md);received=received+1;
 end
end
task frame(input integer number,a,b,c,d,e,f,g,h);
 integer pixel,done;
 begin
  @(negedge clk);en=a;dv=b;distance=c;samples=d;trend=e;tv=f;ir=g;iv=h;
  received=0;fh=$fopen($sformatf("frame%0d.rgb",number),"w");
  for(pixel=0;pixel<921600;pixel=pixel+1)begin
   @(negedge clk);sv=1;su=pixel==0;sl=(pixel%1280)==1279;sd=24'h315375^pixel;
   done=0;while(!done)begin @(posedge clk);if(sr)done=1;end
   @(negedge clk);sv=0;su=0;sl=0;
   if(pixel==100000)begin en=!a;dv=!b;distance=1;ir=~g;iv=!h;trend=0;end
  end
  while(received<921600)@(negedge clk);
  @(negedge clk);$fclose(fh);fh=0;
 end
endtask
initial begin
 repeat(4)@(negedge clk);rst=0;
 CALLS
 $display("TEST PASSED");$finish;
end
initial begin #500000000;$fatal(1,"watchdog");end
endmodule
'''.replace('CALLS',calls)
(B/'tb_tactical.sv').write_text(tb,'ascii')
for i,c in enumerate([['xvlog.bat','--sv',str(P/'fpga/rtl/car_axis_tactical.v'),str(B/'tb_tactical.sv')],['xelab.bat','tb_tactical','-s','tactical'],['xsim.bat','tactical','-runall']]):
 c[0]='C:/AMDDesignTools/2026.1/Vivado/bin/'+c[0];r=subprocess.run(c,cwd=B,capture_output=True,text=True,timeout=300)
 log=r.stdout+r.stderr;(B/f'step{i}.log').write_text(log,'utf8');assert r.returncode==0,log[-2500:]
assert 'TEST PASSED' in log,log[-1500:]
font=[int(x,16) for x in (P/'fpga/rtl/font_24x24_demo.mem').read_text().splitlines()]
chars=json.loads((P/'fpga/rtl/font_24x24_demo.json').read_text('utf8'))['chars']
y,x=np.indices((720,1280));source=np.arange(921600,dtype=np.uint32).reshape(720,1280)^0x315375
def rect(a,b,c,d):return (x>=a)&(x<b)&(y>=c)&(y<d)
def render(case):
 en,dv,distance,samples,trend,tv,ir,iv=case;image=source.copy()
 if not en:return image
 panel=rect(992,1272,368,704)
 dark=np.zeros_like(source)
 for shift in (0,8,16):
  channel=(source>>shift)&255;dark|=((channel//4+channel//8+8)<<shift)
 image[panel]=dark[panel]
 green,red,yellow,gray=0x00b870,0xff3030,0xffd000,0x737d89
 image[rect(1104,1160,520,530)]=gray if not dv else red if distance<=250 else yellow if distance<=350 else green
 # Rotated obstacle rectangles: project onto normalized physical-edge directions.
 # Independent floating-point projection reference, including the exact edge limits.
 norm=float(np.hypot(23,28))
 def rotated_bar(cx,cy,dy):
  along=((x-cx)*23+(y-cy)*dy)/norm
  across=((x-cx)*28-(y-cy)*23*(1 if dy>0 else -1))/norm
  return (np.abs(along)<=1050/norm+1e-10)&(np.abs(across)<=200/norm+1e-10)
 for mask,color in [(rotated_bar(1072,550,-28)|rect(1099,1111,572,584),gray if not iv else red if ir&1 else green),
                    (rotated_bar(1192,550,28)|rect(1154,1166,572,584),gray if not iv else red if ir&2 else green)]:image[mask]=color
 image[(rect(1085,1093,606,624)|rect(1085,1093,646,664)|rect(1171,1179,606,624)|rect(1171,1179,646,664))]=gray
 # Rasterize each silhouette edge from its physical endpoints; 2px horizontal stroke.
 edge=rect(1093,1171,670,672)|rect(1116,1149,564,566)|rect(1093,1095,592,672)|rect(1169,1171,592,672)
 for yy in range(564,592):
  left=1093+(592-yy)*23/28;right=1171-(592-yy)*23/28
  edge[yy]|=((x[yy]>=left)&(x[yy]<left+2))|((x[yy]<=right)&(x[yy]>right-2))
 arrow=rect(1131,1133,612,636)
 for yy in range(602,612):arrow[yy]|=(x[yy]>=1132-(yy-602))&(x[yy]<=1132+(yy-602))
 image[edge|arrow]=0xffffff
 image[rect(1118,1129,560,570)|rect(1135,1146,560,570)]=0x83cfff
 label=f'滤波 {distance//10:3d}.{distance%10} cm' if dv else '滤波 --    cm'
 trend_label=('稳定','接近','远离')[trend-1] if dv and tv else ('采样中' if samples else '未知')
 def text(label,xx,yy):
  for col,ch in enumerate(label):
   glyph=chars.index(ch)
   for row in range(24):
    word=font[glyph*32+row]
    for bit in range(24):
     mask=1<<(23-bit)
     if word>>24&mask:image[yy+row,xx+col*24+bit]=0xffffff
     elif word&mask:image[yy+row,xx+col*24+bit]=0x101010
 text('周边态势',1008,380);text(label,1008,420);text(trend_label,1080,452)
 return image
for i,case in enumerate(cases):
 actual=np.loadtxt(B/f'frame{i}.rgb',dtype=str)
 actual=np.array([int(v,16) for v in actual],dtype=np.uint32).reshape(720,1280)
 expected=render(case);bad=np.argwhere(actual!=expected)
 assert not len(bad),(i,len(bad),bad[:12].tolist())
 if i==0:
  rgb=np.stack(((actual>>16)&255,(actual>>8)&255,actual&255),axis=-1).astype('uint8')
  Image.fromarray(rgb).save(B/'actual_preview.png')
result={'pass':True,'frames':len(cases),'pixels_compared':len(cases)*921600,'geometry':[1280,720],
        'midframe_changes_latched':True,'random_backpressure':True,'rtl_sha256':hashlib.sha256((P/'fpga/rtl/car_axis_tactical.v').read_bytes()).hexdigest()}
(ROOT/'validation/tactical_overlay_gate.json').write_text(json.dumps(result,indent=2),'utf8');print(json.dumps(result))
