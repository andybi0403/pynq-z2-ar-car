"""Execute production display-filter RTL against the independent integer oracle."""
from pathlib import Path
import sys,random,subprocess,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from tactical_filter_reference import TacticalFilter,MS,MASK
B=ROOT/'build/tactical_filter_gate';B.mkdir(parents=True,exist_ok=True)
model=TacticalFilter();rows=[];seq=65520;t=MASK-1_000*MS
def sample(distance,valid=True,dt=100,repeat=False,back=False):
 global seq,t
 t=(t+dt*MS)&MASK
 if not repeat:seq=(seq+1)&65535
 sent=(seq-10)&65535 if back else seq
 expected=model.accept(sent,t,distance,valid,t)
 enum={'unknown':0,'stable':1,'approaching':2,'receding':3}
 rows.append((sent,t,distance,int(valid),int(expected['valid']),expected['filtered_mm'] or 0,enum[expected['trend']],expected['samples']))
for d in (600,610,2500,605,600,600,600,600,600,600,600,600):sample(d)
for d in range(1200,800,-20):sample(d)
sample(800,repeat=True);sample(800,back=True);sample(800,False)
for d in range(500,900,20):sample(d)
sample(700,dt=250)
for _ in range(15):sample(700)
rng=random.Random(146)
for _ in range(400):sample(rng.randrange(4096),rng.random()>.06,rng.choice((20,60,100,120,200,250)),repeat=rng.random()<.08,back=rng.random()<.02)
for _ in range(12):sample(700)
(B/'vectors.txt').write_text(''.join(' '.join(str(x) for x in row)+'\n' for row in rows),'ascii')
tb=r'''`timescale 1ns/1ps
module tb_filter;
reg clk=0;always #5 clk=~clk;
reg rst=1,clear_session=0,event_in=0,valid_in=1;reg [31:0] now=0,stamp=0;
reg [11:0] distance=0;reg [15:0] seq_in=0;
wire fv,tv,busy;wire [11:0] filtered;wire [1:0] count,trend;
car_ultrasonic_display_filter dut(.clk(clk),.rst(rst),.clear_session(clear_session),.now_ticks(now),
 .sample_event(event_in),.source_valid(valid_in),.sample_mm(distance),.sample_seq(seq_in),.sample_ts(stamp),
 .filter_valid(fv),.filtered_mm(filtered),.sample_count(count),.trend_state(trend),.trend_valid(tv),.busy(busy));
integer f,ret,n=0,s,ts,d,v,ev,ed,et,ec,pass;
initial begin
 repeat(4)@(negedge clk);rst=0;
 for(pass=0;pass<3;pass=pass+1)begin
 if(pass!=0)begin
  @(negedge clk);rst=pass==1;clear_session=pass==2;
  repeat(4)@(negedge clk);rst=0;clear_session=0;
 end
 f=$fopen("vectors.txt","r");
 while(!$feof(f))begin
  ret=$fscanf(f,"%d %d %d %d %d %d %d %d\n",s,ts,d,v,ev,ed,et,ec);
  if(ret==8)begin
   @(negedge clk);now=ts;stamp=ts;distance=d;seq_in=s;valid_in=v;event_in=1;
   @(negedge clk);event_in=0;repeat(64)@(negedge clk);
   if(busy||fv!==ev[0]||count!==ec[1:0]||trend!==et[1:0]||(ev&&filtered!==ed[11:0]))
    $fatal(1,"case %d got valid=%d d=%d trend=%d count=%d expected %d %d %d %d",n,fv,filtered,trend,count,ev,ed,et,ec);
   n=n+1;
  end
 end
 $fclose(f);
 end
 $display("TEST PASSED %d samples",n);$finish;
end
initial begin #10000000;$fatal(1,"watchdog");end
endmodule
'''
(B/'tb_filter.sv').write_text(tb,'ascii')
rtl=ROOT/'pynq_fpga/fpga/rtl/car_ultrasonic_display_filter.v'
for i,cmd in enumerate([['xvlog.bat','--sv',str(rtl),str(B/'tb_filter.sv')],['xelab.bat','tb_filter','-s','filter'],['xsim.bat','filter','-runall']]):
 cmd[0]='C:/AMDDesignTools/2026.1/Vivado/bin/'+cmd[0]
 r=subprocess.run(cmd,cwd=B,capture_output=True,text=True,timeout=90);log=r.stdout+r.stderr
 (B/f'step{i}.log').write_text(log,'utf8');assert r.returncode==0,log[-2500:]
assert 'TEST PASSED' in log,log[-2000:]
result={'pass':True,'samples':len(rows)*3,'reset_and_session_clear_with_dirty_history':True,'rtl_sha256':hashlib.sha256(rtl.read_bytes()).hexdigest(),'scope':'actual production RTL versus independent median/trend reference; not hardware validation'}
(ROOT/'validation/tactical_filter_gate.json').write_text(json.dumps(result,indent=2),'utf8')
print(json.dumps(result))

