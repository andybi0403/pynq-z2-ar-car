`timescale 1ns/1ps
module tb_plain_motor_demo;
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
  repeat(4)@(posedge clk);@(negedge clk);rst=0;repeat(12)@(posedge clk);
  rdreg('h000,rd);check("demo ABI",rd,32'hc425100c);
  rdreg('h024,rd);check("ordinary motor profile",rd,1);
  check("startup STOP",risk_stop,1);
  wr('h300,1);stage(900,0,1,1);wr('h31c,1);wr('h140,3);repeat(30)@(posedge clk);
  check("clear US permits forward with no QEI",risk_stop,0);
  check("green",risk_level,0);check("no QEI fault reasons",risk_reasons&16'h2f00,0);
  wr('h004,1);rdreg('h0c4,rd);check("fixed stop threshold",rd,250);
  rdreg('h090,rd);check("QEI0 remains invalid",rd[31],0);
  rdreg('h0a8,rd);check("QEI1 remains invalid",rd[31],0);
  rdreg('h214,rd);check("measured odometry remains invalid",rd[31],0);
  repeat(8)begin @(negedge clk);q0a=~q0a;q0b=~q0b;q1a=~q1a;q1b=~q1b;repeat(12)@(posedge clk);end
  wr('h004,1);rdreg('h094,rd);check("unused pins cannot inject left motion",rd,0);
  rdreg('h0ac,rd);check("unused pins cannot inject right motion",rd,0);
  stage(250,0,2,2);wr('h31c,2);repeat(30)@(posedge clk);
  check("250 mm boundary stops",risk_stop,1);check("distance RED",risk_level,2);
  stage(251,0,3,3);wr('h31c,3);repeat(30)@(posedge clk);
  check("251 mm gives advisory yellow",risk_level,1);check("yellow no hard STOP",risk_stop,0);
  stage(900,0,4,4,7);wr('h31c,4);repeat(30)@(posedge clk);
  check("IR remains warning only",risk_stop,0);check("IR warning retained",risk_reasons[7],1);
  stage(900,20_000_000,5,5);wr('h31c,5);repeat(30)@(posedge clk);
  check("stale US still stops",risk_stop,1);
  stage(900,0,6,6);wr('h31c,6);wr('h140,0);repeat(30)@(posedge clk);
  check("missing intent still stops",risk_stop,1);
  wr('h140,3);repeat(30)@(posedge clk);check("new clear sample and intent recovers risk only",risk_stop,0);
  force dut.ticks=64'd25_100_000;repeat(30)@(posedge clk);
  check("expired intent stops",risk_stop,1);release dut.ticks;
  if(errors)$fatal(1,"plain motor failures=%0d",errors);
  $display("TEST PASSED (%0d checks)",checks);$finish;
 end
 initial begin #2000000;$fatal(1,"timeout");end
endmodule
