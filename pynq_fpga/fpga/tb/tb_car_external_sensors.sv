`timescale 1ns/1ps
module tb_car_external_sensors;
 reg clk=0,rst=1,us_echo=0,ir_l_raw=1,ir_r_raw=1,q0a=0,q0b=0,q1a=0,q1b=0;
 always #5 clk=~clk;
 reg [11:0] awaddr=0,araddr=0;reg [2:0] awprot=0,arprot=0;reg awvalid=0,wvalid=0,arvalid=0;
 reg [31:0] wdata=0;reg [3:0] wstrb=15;wire awready,wready,bvalid,arready,rvalid;reg bready=0,rready=0;
 wire [1:0] bresp,rresp;wire [31:0] rdata;wire us_trig,risk_stop;wire [1:0] risk_level;wire [15:0] risk_reasons;
 wire car_valid,car_locked;wire [15:0] car_fault;
 car_perception_top dut(.clk(clk),.rst(rst),.us_echo(us_echo),.us_trig(us_trig),.ir_l_raw(ir_l_raw),.ir_r_raw(ir_r_raw),
  .qei0_a(q0a),.qei0_b(q0b),.qei1_a(q1a),.qei1_b(q1b),.risk_stop_o(risk_stop),.risk_level_o(risk_level),.risk_reasons_o(risk_reasons),
  .osd_car_valid_o(car_valid),.osd_car_locked_o(car_locked),.osd_car_fault_o(car_fault),
  .osd_errors_i(16'd9),.osd_frames_i(32'd12),
  .s_axil_awaddr(awaddr),.s_axil_awprot(awprot),.s_axil_awvalid(awvalid),.s_axil_awready(awready),
  .s_axil_wdata(wdata),.s_axil_wstrb(wstrb),.s_axil_wvalid(wvalid),.s_axil_wready(wready),
  .s_axil_bresp(bresp),.s_axil_bvalid(bvalid),.s_axil_bready(bready),.s_axil_araddr(araddr),.s_axil_arprot(arprot),
  .s_axil_arvalid(arvalid),.s_axil_arready(arready),.s_axil_rdata(rdata),.s_axil_rresp(rresp),.s_axil_rvalid(rvalid),.s_axil_rready(rready));
 integer errors=0,checks=0;reg [31:0] rd,held;
 task check(input string n,input [31:0] got,input [31:0] want);begin checks++;if(got!==want)begin errors++;$display("[FAIL] %s got=%h want=%h",n,got,want);end end endtask
 task wr(input [11:0] a,input [31:0] d,input [3:0] s=15);begin
  @(negedge clk);awaddr=a;wdata=d;wstrb=s;awvalid=1;wvalid=1;bready=0;
  do @(posedge clk);while(!(awready&&wready));@(negedge clk);awvalid=0;wvalid=0;bready=1;
  do @(posedge clk);while(!bvalid);@(negedge clk);bready=0;
 end endtask
 task rdreg(input [11:0] a,output [31:0] d);begin
  @(negedge clk);araddr=a;arvalid=1;rready=0;do @(posedge clk);while(!arready);
  @(negedge clk);arvalid=0;rready=1;do @(posedge clk);while(!rvalid);d=rdata;@(negedge clk);rready=0;
 end endtask
 task stage(input [31:0] mm,input [31:0] age,input [15:0] useq,input [15:0] iseq,input [31:0] ir=4);begin
  wr('h328,dut.ticks[31:0]);wr('h32c,dut.ticks[63:32]);
  wr('h304,mm);wr('h308,age);wr('h30c,{1'b1,15'd0,useq});
  wr('h310,ir);wr('h314,0);wr('h318,{1'b1,15'd0,iseq});
 end endtask
 initial begin
  repeat(4)@(posedge clk);@(negedge clk);rst=0;repeat(8)@(posedge clk);
  rdreg('h000,rd);check("new contract",rd,32'hc425100a);
  wr('h300,1);check("external starts invalid",dut.us_valid,0);
  stage(900,100,7,8);
  check("staging cannot leak",dut.us_valid,0);
  wr('h31c,1);check("atomic US valid",dut.us_valid,1);
  check("atomic IR valid",dut.ir_valid,1);check("atomic distance",dut.us_data,900);
  wr('h004,1);rdreg('h040,rd);check("external enters global snapshot",rd,900);
  rdreg('h048,rd);check("paired US metadata",rd,32'h80000007);
  rdreg('h058,rd);check("paired IR metadata",rd,32'h80000008);
  held=dut.us_ts;
  stage(900,0,7,8);wr('h31c,2);
  check("repeat sample retains timestamp",dut.us_ts,held);
  wr('h31c,3,0);check("WSTRB zero commit inert",dut.us_valid,1);
  force dut.ticks=64'd20_010_000;repeat(3)@(posedge clk);
  check("US expires at 200ms",dut.us_valid,0);check("IR expires independently",dut.ir_valid,0);
  force dut.ticks=64'h100000100;repeat(3)@(posedge clk);
  check("time wrap cannot resurrect US",dut.us_valid,0);
  stage(900,0,7,8);wr('h31c,3);check("queries cannot revive expired same sample",dut.us_valid,0);
  stage(800,0,8,9);wr('h31c,4);check("new actual sample recovers",dut.us_valid,1);
  check("new actual sample data",dut.us_data,800);
  stage(700,0,9,10);wr('h304,701,1);wr('h31c,5);
  check("partial batch invalidates rather than tearing",dut.us_valid,0);
  stage(600,0,10,11);wr('h31c,6);check("complete batch after failure",dut.us_valid,1);
  stage(500,0,11,12);wr('h31c,6);check("replayed transaction rejected",dut.us_valid,0);
  stage(400,20_000_000,12,13);wr('h31c,7);check("old age rejected at boundary",dut.us_valid,0);
  stage(300,0,13,14,5);wr('h31c,8);
  check("obstacle retained in snapshot",dut.ir_status,5);
  force dut.q0_trusted=1;force dut.q1_trusted=1;
  force dut.q0_vel=0;force dut.q1_vel=0;
  force dut.q0_ts=32'h100;force dut.q1_ts=32'h100;
  wr('h140,3);repeat(24)@(posedge clk);
  check("PL sees UART IR obstacle",risk_stop,1);
  check("PL records IR reason",risk_reasons[7],1);
  stage(1000,0,14,15,4);wr('h31c,9);repeat(24)@(posedge clk);
  check("PL risk gets complete new UART batch",risk_stop,0);
  wr('h300,1);check("mode write revokes old sensor snapshot",dut.us_valid,0);
  stage(900,0,15,16);
  force dut.ticks=64'h101312e00;repeat(3)@(posedge clk);
  wr('h31c,10);check("delayed MMIO commit cannot renew old sample",dut.us_valid,0);
  check("delayed MMIO commit also expires IR",dut.ir_valid,0);
  stage(900,0,16,17);
  force dut.ticks=64'h201312e00;repeat(3)@(posedge clk);
  wr('h31c,11);check("full low-word wrap before commit stays expired",dut.us_valid,0);
  stage(900,0,17,18);wr('h328,32'h01312e01);wr('h31c,12);
  check("future anchor rejected",dut.us_valid,0);
  release dut.ticks;
  if(errors)$fatal(1,"external sensor test failures=%0d",errors);
  $display("TEST PASSED (%0d checks)",checks);$finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
