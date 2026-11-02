"""Production ROM classification versus exact arithmetic at all transition edges."""
from pathlib import Path
import json,subprocess,hashlib
ROOT=Path(__file__).resolve().parents[1];B=ROOT/'build/tactical_lookup_gate';B.mkdir(parents=True,exist_ok=True)
rtl=ROOT/'pynq_fpga/fpga/rtl/car_ultrasonic_display_filter.v'
tb=r'''`timescale 1ns/1ps
module tb_lookup;
reg clk=0;always #5 clk=~clk;
reg rst=1;reg [11:0] a=0,b=0;reg [31:0] dt=0;
car_ultrasonic_display_filter dut(.clk(clk),.rst(rst),.clear_session(1'b0),
 .now_ticks(32'd0),.sample_event(1'b0),.source_valid(1'b1),.sample_mm(12'd0),
 .sample_seq(16'd0),.sample_ts(32'd0));
integer magnitude,sign_case,edge_case,expected,n=0;reg [3:0] covered=0;
reg [63:0] trial,scaled;
initial begin
 repeat(4)@(negedge clk);rst=0;
 force dut.state=4'd2;
 force dut.best_mm=a;force dut.work_mm=b;force dut.best_dt=dt;
 for(magnitude=0;magnitude<4096;magnitude=magnitude+1)
  for(sign_case=0;sign_case<2;sign_case=sign_case+1)
   for(edge_case=0;edge_case<9;edge_case=edge_case+1)begin
    case(edge_case)
     0:trial=40_000_000;1:trial=50_000_000;2:trial=60_000_000;
     3:trial=magnitude*64'd2_000_000-1;
     4:trial=magnitude*64'd2_000_000;
     5:trial=magnitude*64'd2_000_000+1;
     6:trial=magnitude*64'd5_000_000-1;
     7:trial=magnitude*64'd5_000_000;
     8:trial=magnitude*64'd5_000_000+1;
    endcase
    if(trial>=40_000_000&&trial<=60_000_000)begin
     @(negedge clk);dt=trial;
     a=sign_case?0:magnitude;b=sign_case?magnitude:0;
     scaled=magnitude*64'd100_000_000;
     expected=scaled>=trial*50?(sign_case?3:2):scaled<=trial*20?1:0;
     @(posedge clk);@(negedge clk);
     if(dut.classification!==expected[1:0])
      $fatal(1,"magnitude=%d sign=%d dt=%d actual=%d expected=%d",magnitude,sign_case,dt,dut.classification,expected);
     covered[expected]=1;n=n+1;
    end
   end
 if(covered!==4'b1111)$fatal(1,"classification coverage");
 $display("TEST PASSED %0d boundaries",n);$finish;
end
initial begin #5000000;$fatal(1,"watchdog");end
endmodule
'''
(B/'tb_lookup.sv').write_text(tb,'ascii')
for i,cmd in enumerate([['xvlog.bat','--sv',str(rtl),str(B/'tb_lookup.sv')],['xelab.bat','tb_lookup','-s','lookup'],['xsim.bat','lookup','-runall']]):
    cmd[0]='C:/AMDDesignTools/2026.1/Vivado/bin/'+cmd[0]
    r=subprocess.run(cmd,cwd=B,capture_output=True,text=True,timeout=90)
    log=r.stdout+r.stderr;(B/f'step{i}.log').write_text(log,'utf8')
    assert r.returncode==0,log[-2000:]
assert 'TEST PASSED' in log,log[-2000:]
import re
result={'pass':True,'boundary_cases':int(re.search(r'TEST PASSED (\d+)',log)[1]),
        'distance_deltas':'0..4095mm, both signs','reference_dt_ticks':[40000000,60000000],
        'all_classifications_covered':True,'rtl_sha256':hashlib.sha256(rtl.read_bytes()).hexdigest(),
        'scope':'production ROM/registered classifier versus exact wide arithmetic; not hardware validation'}
(ROOT/'validation/tactical_lookup_gate.json').write_text(json.dumps(result,indent=2),'utf8')
print(json.dumps(result))
