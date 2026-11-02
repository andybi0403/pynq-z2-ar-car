"""Production Python->RTL 24-pixel metadata ABI, including stalled replay."""
from pathlib import Path
import sys,subprocess,json,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'pynq_fpga/preintegration/host'))
from frame_metadata import encode,decode,WORDS
B=ROOT/'build/tactical_metadata_gate';B.mkdir(parents=True,exist_ok=True)
cases=[]
for trend in range(4):
 raw={'US_DATA':500,'US_META':0x80000001,'RISK_STATE':0,'RISK_META':0x80000001,
      'US_FILTER_MM':487,'US_FILTER_META':0x80030001,'US_FILTER_LATEST_TS':995000000,
      'US_FILTER_OLDEST_TS':975000000,'US_TREND_STATE':(0x80000000|trend) if trend else 0,
      'IR_META':0x80000001,'IR_STATUS':4|(trend&3),'IR_TS':999000000,'SNAP_CAR_STATE':3}
 a={'valid':True,'frame_id':100+trend,'epoch':3,'estimated_frame_pl_ticks64':1000000000,
    'sample_age_ms':{'us':50,'risk':1},'registers':raw}
 words=encode(a);value=decode(words);assert value['filter_valid'] and value['filtered_mm']==487
 cases.append((words,1,1,trend))
words=cases[0][0][:];words[1]=0x020012;words[-1]^=0x020012^0x030018
cases.append((words,0,0,0))
words=cases[0][0][:];words[18]=1000000001&0xffffff;words[19]=1000000001>>24
words[-1]=0xffffff
for word in words[:-1]:words[-1]^=word
cases.append((words,1,0,0))
stim=''
for words,mv,fv,tr in cases:
 stim+='\n'+''.join(f' pixels[{i}]=24\'h{v:06x};' for i,v in enumerate(words))
 stim+=f' expected_metadata={mv};expected_filter={fv};expected_trend={tr};send_frame();\n'
tb=r'''`timescale 1ns/1ps
module tb_meta;
reg clk=0;always #5 clk=~clk;
reg rst=1,sv=0,su=0,sl=0,mr=0;reg [23:0] sd=0;
wire sr,mv,mu,ml,metadata_valid,filter_valid;wire [23:0] md;wire [11:0] filtered;
wire [1:0] trend;reg [23:0] pixels[0:31];integer accepted=0,seed=123;
reg expected_metadata,expected_filter;reg [1:0] expected_trend;
reg held=0;reg [25:0] last;
car_axis_frame_metadata dut(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tvalid(sv),
 .s_axis_tready(sr),.s_axis_tuser(su),.s_axis_tlast(sl),.m_axis_tdata(md),.m_axis_tvalid(mv),
 .m_axis_tready(mr),.m_axis_tuser(mu),.m_axis_tlast(ml),.metadata_valid(metadata_valid),
 .filtered_mm(filtered),.filter_valid(filter_valid),.trend_state(trend));
always @(negedge clk)if(!rst)mr=($random(seed)&3)!=0;
always @(posedge clk)if(!rst)begin
 if(held&&(!mv||{md,mu,ml}!==last))$fatal(1,"held payload changed");
 held=mv&&!mr;last={md,mu,ml};
 if(mv&&mr)begin
  if(mu!==(accepted==0)||ml!==(accepted==31))$fatal(1,"markers");
  if(md!==((expected_metadata&&accepted<24)?24'd0:pixels[accepted]))$fatal(1,"pixel mismatch %d",accepted);
  accepted=accepted+1;
 end
end
task send_frame;
 integer i,done;
 begin
  accepted=0;
  for(i=0;i<32;i=i+1)begin
   @(negedge clk);sv=1;su=i==0;sl=i==31;sd=pixels[i];
   done=0;while(!done)begin @(posedge clk);if(sr)done=1;end
   @(negedge clk);sv=0;su=0;sl=0;
  end
  while(accepted<32)@(negedge clk);
  @(negedge clk);
  if(metadata_valid!==expected_metadata||filter_valid!==expected_filter)$fatal(1,"validity mismatch");
  if(expected_filter&&(filtered!==12'd487||trend!==expected_trend))$fatal(1,"feature mismatch");
 end
endtask
integer j;
initial begin
 repeat(4)@(negedge clk);rst=0;
 for(j=0;j<32;j=j+1)pixels[j]=j;
 STIMULUS
 $display("TEST PASSED");$finish;
end
initial begin #1000000;$fatal(1,"watchdog");end
endmodule
'''.replace('STIMULUS',stim)
(B/'tb_meta.sv').write_text(tb,'ascii')
for i,c in enumerate([['xvlog.bat','--sv',str(ROOT/'pynq_fpga/fpga/rtl/car_axis_frame_metadata.v'),str(B/'tb_meta.sv')],['xelab.bat','tb_meta','-s','meta'],['xsim.bat','meta','-runall']]):
 c[0]='C:/AMDDesignTools/2026.1/Vivado/bin/'+c[0];r=subprocess.run(c,cwd=B,capture_output=True,text=True,timeout=90)
 log=r.stdout+r.stderr;(B/f'step{i}.log').write_text(log,'utf8');assert r.returncode==0,log[-2000:]
assert 'TEST PASSED' in log,log[-2000:]
result={'pass':True,'frames':len(cases),'metadata_words':WORDS,
        'sources':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                   ('pynq_fpga/fpga/rtl/car_axis_frame_metadata.v','pynq_fpga/preintegration/host/frame_metadata.py','pynq_fpga/preintegration/host/tactical_state.py')},
        'scope':'production Python/RTL ABI with backpressure; not board validation'}
(ROOT/'validation/tactical_metadata_gate.json').write_text(json.dumps(result,indent=2),'utf8');print(json.dumps(result))
