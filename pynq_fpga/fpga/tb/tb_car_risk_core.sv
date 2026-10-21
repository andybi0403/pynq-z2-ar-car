`timescale 1ns/1ps
module tb_car_risk_core;
 reg clk=0,rst=1,enable=1,cmd_forward=1,cmd_valid=1,us_valid=1,ir_valid=1,q0_valid=1,q1_valid=1;
 always #5 clk=~clk;
 reg [31:0] now=100,cmd_ts=100,us_data=1500,us_ts=100,ir_ts=100,q0_vel=32'd65536000,q0_ts=100,q1_vel=32'd65536000,q1_ts=100;
 reg [15:0] us_seq=1,ir_seq=1,q0_seq=1,q1_seq=1;reg [2:0] ir_status=3'b100;
 wire stop,valid,update;wire [1:0] level;wire [15:0] reasons,seq;wire [31:0] required,risk_ts;
 integer errors=0,checks=0;reg [15:0] before_seq;
 integer k;reg [3:0] seen_burst;
 car_risk_core #(.DATA_MAX_AGE_TICKS(20),.COMMAND_LEASE_TICKS(25),.REACTION_MS(100)) dut(
  .clk(clk),.rst(rst),.now_ticks(now),.enable(enable),.command_forward(cmd_forward),.command_valid(cmd_valid),.command_ts(cmd_ts),
  .us_data(us_data),.us_valid(us_valid),.us_ts(us_ts),.us_seq(us_seq),.ir_status(ir_status),.ir_valid(ir_valid),.ir_ts(ir_ts),.ir_seq(ir_seq),
  .q0_vel(q0_vel),.q0_valid(q0_valid),.q0_ts(q0_ts),.q0_seq(q0_seq),.q1_vel(q1_vel),.q1_valid(q1_valid),.q1_ts(q1_ts),.q1_seq(q1_seq),
  .stop_request(stop),.risk_level(level),.reason_bits(reasons),.required_mm(required),.risk_ts(risk_ts),.risk_valid(valid),.risk_seq(seq),.risk_update(update));
 task check(input string n,input [31:0] got,input [31:0] want);begin checks++;if(got!==want)begin errors++;$display("[FAIL] %s got=%h want=%h",n,got,want);end end endtask
 task settle;begin repeat(12)@(posedge clk);end endtask
 initial begin
  repeat(3)@(posedge clk);check("reset fail safe",stop,1);@(negedge clk);rst=0;settle;
  check("required conservative physics",required,1202);check("safe green",level,0);check("safe permits",stop,0);check("result valid",valid,1);
  before_seq=seq;now=101;cmd_ts=101;settle;check("command renewal publishes",seq,before_seq+1'b1);
  // IR timestamp is a change timestamp. A continuously stable input must not
  // become stale just because its logical state did not change.
  now=120;cmd_ts=120;us_ts=120;q0_ts=120;q1_ts=120;ir_ts=100;settle;
  check("static IR does not false-expire",reasons[6],0);check("static IR remains safe",level,0);
  us_data=1300;settle;check("yellow band",level,1);check("yellow permits candidate",stop,0);
  us_data=1202;settle;check("red boundary",level,2);check("red stops",stop,1);check("distance reason",reasons[12],1);
  us_data=1500;ir_status=3'b101;settle;check("IR fault level",level,3);check("IR reason",reasons[7],1);
  ir_status=3'b100;now=140;settle;check("US age exact invalid",reasons[4],1);
  now=5;cmd_ts=32'hfffffff8;us_ts=32'hfffffff8;ir_ts=32'hfffffff8;q0_ts=32'hfffffff8;q1_ts=32'hfffffff8;settle;
  check("wrap age remains fresh",level,0);
  now=32'h11;settle;check("command lease exact stale",reasons[2],1);
  now=5;cmd_ts=5;us_ts=5;ir_ts=5;q0_ts=5;q1_ts=5;q0_valid=0;settle;check("QEI invalid fault",reasons[8],1);check("QEI invalid stops",stop,1);
  // 独立覆盖两路QEI年龄边界；同时递增序号，模拟真实采样提交并触发发布。
  q0_valid=1;q0_vel=32'd65536000;now=50;cmd_ts=50;us_ts=50;q1_ts=50;q0_ts=30;q0_seq=q0_seq+1'b1;settle;
  check("QEI0 age exact stale",reasons[10],1);check("QEI0 stale stops",stop,1);
  q0_ts=50;q0_seq=q0_seq+1'b1;settle;check("QEI0 freshness clears",reasons[10],0);
  q1_ts=30;q1_seq=q1_seq+1'b1;settle;
  check("QEI1 age exact stale",reasons[11],1);check("QEI1 stale stops",stop,1);
  q1_ts=50;q1_seq=q1_seq+1'b1;settle;check("QEI1 freshness clears",reasons[11],0);
  // ir_status[2]是硬件稳定/可用位；valid=1不能掩盖stable=0。
  ir_status=3'b000;ir_seq=ir_seq+1'b1;settle;
  check("IR unstable invalid",reasons[5],1);check("IR unstable stops",stop,1);
  ir_status=3'b100;ir_seq=ir_seq+1'b1;settle;check("IR stable clears invalid",reasons[5],0);
  q0_vel=32'hfc18_0000;settle;check("reverse wheel direction fault",reasons[13],1);check("direction fault stops",stop,1);
  // Back-to-back source tuples must keep their timestamp with the matching
  // arithmetic result through every DSP pipeline stage.
  @(negedge clk);q0_vel=32'd0;q1_vel=32'd0;now=200;cmd_ts=200;us_ts=200;q0_ts=200;q1_ts=200;us_data=1500;
  settle;seen_burst=0;
  for(k=0;k<4;k=k+1) begin
   @(negedge clk);now=201+k;cmd_ts=201+k;us_ts=201+k;q0_ts=201+k;q1_ts=201+k;
   q0_vel=(k*500)<<16;q1_vel=(k*500)<<16;us_seq=us_seq+1'b1;
  end
  for(k=0;k<16;k=k+1) begin
   @(negedge clk);
   if(update && risk_ts>=201 && risk_ts<=204) begin
    seen_burst[risk_ts-201]=1'b1;
    case(risk_ts)
     201:check("burst tuple 0",required,100);
     202:check("burst tuple 1",required,402);
     203:check("burst tuple 2",required,1202);
     204:check("burst tuple 3",required,2502);
    endcase
   end
  end
  check("all burst tuples published",seen_burst,4'hf);
  if(errors==0)$display("TEST PASSED (%0d checks)",checks);else $display("TEST FAILED (%0d errors)",errors);$finish;
 end
 initial begin #100000;$display("TEST FAILED watchdog");$finish;end
endmodule
