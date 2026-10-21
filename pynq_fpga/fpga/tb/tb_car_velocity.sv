`timescale 1ns/1ps
module tb_car_velocity;
 reg clk=0,rst=1,step=0,dir=1,pvalid=1;
 always #5 clk=~clk;
 reg [31:0] pos=0,period=10000,now_ticks=0,scale=65536,timeout=2000000;
 reg [5:0] shift=0;
 wire [31:0] vel,ts,spos,speriod;
 wire valid,update;
 wire [15:0] seq,overrun;
 car_qei_velocity dut(.clk(clk),.rst(rst),.pos_cnt(pos),.period_ticks(period),
 .now_ticks(now_ticks),.step_pulse(step),.step_dir(dir),.period_valid(pvalid),
 .cfg_scale(scale),.cfg_period(timeout),.cfg_shift(shift),.vel_q16(vel),
 .sample_ts(ts),.sample_pos(spos),.sample_period(speriod),.vel_valid(valid),
 .vel_seq(seq),.overrun_cnt(overrun),.live_update(update));
 integer errors=0,checks=0,i;
 reg [63:0] reference;
 reg [31:0] expected;
 task check(input string name,input [31:0] actual,input [31:0] want);
 begin checks++;if(actual!==want)begin errors++;$display("[FAIL] %s got=%h want=%h",name,actual,want);end end
 endtask
 task ticks(input integer n);repeat(n) @(negedge clk);endtask
 task measure(input [31:0] count,input [31:0] gain,input bit direction,input [31:0] stamp);
 begin
  scale=gain;dir=direction;period=count;now_ticks=stamp;ticks(8);
  pos=pos+1;step=1;ticks(1);step=0;
  ticks(64);
  reference=(64'd100000000*gain)/count;
  if(direction) expected=reference>2147483647 ? 32'h7fffffff:reference[31:0];
  else expected=reference>=2147483648 ? 32'h80000000:-reference[31:0];
  check("independent SI speed",vel,expected);check("valid",valid,1);
  check("sample timestamp",ts,stamp);check("sample position",spos,pos);check("sample period",speriod,count);
 end endtask
 initial begin
  ticks(4);rst=0;ticks(8);
  // Deterministic period sweep, fractional calibration, both signs and wrap stamps.
  for(i=0;i<20;i++) measure(1000+i*12347,65536+i*73,i%2,32'hfffffff0+i*9);
  measure(66,32'hffffffff,0,10);
  measure(66,32'hffffffff,1,20);
  // A normal calculation keeps the last complete observation valid until the
  // replacement batch is published; an input faster than divider throughput
  // is visible through overrun and invalidates the superseded observation.
  measure(10000,65536,1,30);
  period=10000;pvalid=1;scale=65536;ticks(8);
  step=1;ticks(1);step=0;ticks(10);check("valid held while divider busy",valid,1);
  ticks(54);check("replacement publish valid",valid,1);
  step=1;ticks(1);step=0;ticks(10);
  step=1;ticks(1);step=0;ticks(1);
  check("divider overrun counted",overrun,1);check("overrun invalidates stale value",valid,0);
  ticks(64);check("latest job recovers",valid,1);
  period=10000;step=1;ticks(1);step=0;ticks(20);scale=0;ticks(60);
  check("configuration abort",valid,0);
  scale=65536;ticks(8);period=65;step=1;ticks(1);step=0;ticks(70);
  check("too fast invalid",valid,0);
  period=10000;pvalid=0;step=1;ticks(1);step=0;ticks(70);
  check("first edge invalid",valid,0);
  timeout=0;ticks(10);check("zero timeout",valid,0);
  if(errors==0)$display("TEST PASSED (%0d checks)",checks);
  else $display("TEST FAILED (%0d errors)",errors);
  $finish;
 end
 initial begin #1000000;$display("TEST FAILED watchdog");$finish;end
endmodule
