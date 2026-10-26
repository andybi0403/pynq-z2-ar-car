`timescale 1ns/1ps
module tb_car_perception_arch;
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
 initial begin
  repeat(4)@(posedge clk);@(negedge clk);rst=0;repeat(8)@(posedge clk);
  rdreg('h000,rd);check("integrated id",rd,32'hc425100b);
  rdreg('h104,rd);check("US period default",rd,6000000);
  rdreg('h108,rd);check("US timeout default",rd,3000000);
  rdreg('h128,rd);check("QEI scale fail-safe",rd,0);
  check("risk defaults stop",risk_stop,1);
  wr('h020,32'h12345678,4'b0011);rdreg('h020,rd);check("WSTRB common",rd,32'ha55a5678);
  wr('h004,2);rdreg('h018,held);repeat(20)@(posedge clk);wr('h004,2);rdreg('h018,rd);check("single timebase advances",rd>held,1);
  force dut.us_data=32'h000003e8;force dut.us_valid=1;force dut.us_ts=32'h80000005;force dut.us_seq=16'h11;force dut.us_err=16'h22;
  force dut.ir_status=3'b100;force dut.ir_valid=1;force dut.ir_ts=32'h80000006;force dut.ir_seq=16'h12;
  force dut.q0_pos=32'h10;force dut.q0_period=32'h100;force dut.q0_vel=32'h00010000;force dut.q0_ts=32'h80000007;force dut.q0_valid=1;force dut.q0_seq=16'h13;force dut.q0_info=32'h1234;
  force dut.q1_pos=32'h20;force dut.q1_period=32'h200;force dut.q1_vel=32'h00020000;force dut.q1_ts=32'h80000008;force dut.q1_valid=1;force dut.q1_seq=16'h14;force dut.q1_info=32'h5678;
  force dut.risk_stop=0;force dut.risk_level=0;force dut.risk_reasons=0;force dut.risk_required=32'd123;force dut.risk_ts=32'h80000009;force dut.risk_valid=1;force dut.risk_seq=16'h15;
  wr('h004,1);rdreg('h00c,rd);check("snapshot epoch",rd,1);
  rdreg('h040,rd);check("US same snapshot",rd,1000);rdreg('h044,rd);check("US timestamp bit31",rd,32'h80000005);
  rdreg('h048,rd);check("US meta",rd,32'h80000011);rdreg('h054,rd);check("IR timestamp",rd,32'h80000006);
  rdreg('h058,rd);check("IR meta same snapshot",rd,32'h80000012);
  rdreg('h088,rd);check("Q0 velocity",rd,32'h00010000);rdreg('h08c,rd);check("Q0 timestamp",rd,32'h80000007);
  rdreg('h090,rd);check("Q0 meta same snapshot",rd,32'h80000013);
  rdreg('h0a0,rd);check("Q1 velocity",rd,32'h00020000);rdreg('h0a4,rd);check("Q1 timestamp",rd,32'h80000008);
  rdreg('h0a8,rd);check("Q1 meta same snapshot",rd,32'h80000014);
  rdreg('h0c4,rd);check("risk required",rd,123);rdreg('h0c8,rd);check("risk timestamp",rd,32'h80000009);
  rdreg('h0cc,rd);check("risk meta",rd,32'h80000015);
  force dut.us_data=32'hdeadbeef;rdreg('h040,rd);check("shadow stable without trigger",rd,1000);
  force dut.q0_vel=32'hfeed0001;force dut.risk_required=32'hfeed0002;
  rdreg('h088,rd);check("Q0 uncommitted live change hidden",rd,32'h00010000);
  rdreg('h0c4,rd);check("risk uncommitted live change hidden",rd,123);
  wr('h140,3);wr('h004,1);rdreg('h0d0,rd);check("command enters global snapshot",rd[1:0],3);
  rdreg('h00c,rd);check("snapshot epoch increments",rd,2);
  // A forced boundary avoids a 2^32-cycle run while testing the actual
  // 64-bit time latch and unsigned low-word wrap semantics.
  force dut.ticks=64'h00000001fffffffe;wr('h004,2);rdreg('h018,held);rdreg('h01c,rd);
  check("time before wrap low",held,32'hfffffffe);check("time before wrap high",rd,1);
  force dut.ticks=64'h0000000200000002;wr('h004,2);rdreg('h018,rd);check("time after wrap low",rd,2);
  check("time low unsigned delta",rd-held,4);rdreg('h01c,rd);check("time after wrap high",rd,2);
  release dut.ticks;
  rdreg('h3fc,rd);check("illegal address zero",rd,0);
  release dut.us_data;release dut.us_valid;release dut.us_ts;release dut.us_seq;release dut.us_err;
  release dut.ir_status;release dut.ir_valid;release dut.ir_ts;release dut.ir_seq;
  release dut.q0_pos;release dut.q0_period;release dut.q0_vel;release dut.q0_ts;release dut.q0_valid;release dut.q0_seq;release dut.q0_info;
  release dut.q1_pos;release dut.q1_period;release dut.q1_vel;release dut.q1_ts;release dut.q1_valid;release dut.q1_seq;release dut.q1_info;
  release dut.risk_stop;release dut.risk_level;release dut.risk_reasons;release dut.risk_required;release dut.risk_ts;release dut.risk_valid;release dut.risk_seq;
  // Drive actual synchronized AB inputs through decoder, odometer and AXI.
  wr('h128,32768);wr('h138,65536);repeat(20)@(posedge clk);
  @(negedge clk);q0a=1;q1b=1;repeat(12)@(posedge clk);
  @(negedge clk);q0b=1;q1a=1;repeat(12)@(posedge clk);
  wr('h004,1);
  rdreg('h200,rd);check("left physical +1mm",rd,65536);
  rdreg('h204,rd);check("left signed high",rd,0);
  rdreg('h208,rd);check("left travelled 1mm",rd,65536);
  rdreg('h220,rd);check("right physical -2mm",rd,32'hfffe0000);
  rdreg('h224,rd);check("right negative sign extension",rd,32'hffffffff);
  rdreg('h228,rd);check("right travelled +2mm",rd,131072);
  rdreg('h214,rd);check("left calibrated meta",rd,32'h80000003);
  @(negedge clk);q0b=0;repeat(12)@(posedge clk);
  rdreg('h200,rd);check("live edge hidden until snapshot",rd,65536);
  wr('h004,1);rdreg('h200,rd);check("reverse decreases displacement",rd,32768);
  rdreg('h208,rd);check("reverse increases path",rd,98304);
  // Illegal 10 -> 01 transition invalidates distance and stays sticky.
  @(negedge clk);q0a=0;q0b=1;repeat(12)@(posedge clk);
  wr('h004,1);rdreg('h214,rd);check("missed edge sticky invalid",rd[31:30],1);
  @(negedge clk);q0b=0;repeat(12)@(posedge clk);
  wr('h004,1);rdreg('h200,rd);check("fault freezes untrustworthy displacement",rd,32768);
  wr('h148,1);wr('h004,1);
  rdreg('h200,rd);check("explicit reset net",rd,0);
  rdreg('h208,rd);check("explicit reset path",rd,0);
  rdreg('h228,rd);check("explicit reset both wheels",rd,0);
  rdreg('h218,rd);check("reset new epoch",rd,2);
  wr('h120,1);wr('h004,1);rdreg('h218,rd);check("direction change new epoch",rd,3);
  // Prove low/high snapshot stability across a live 32-bit carry.
  force dut.odo0_path=64'h00000001ffffffff;wr('h004,1);
  force dut.odo0_path=64'h0000000200000000;
  rdreg('h208,rd);check("64-bit old low held",rd,32'hffffffff);
  rdreg('h20c,rd);check("64-bit old high held",rd,1);
  wr('h004,1);rdreg('h208,rd);check("64-bit next low",rd,0);
  rdreg('h20c,rd);check("64-bit next high",rd,2);release dut.odo0_path;
  check("missing UART status invalid",car_valid,0);
  force dut.ticks=64'd100;
  wr('h288,10000000);wr('h284,32'h12340003);
  check("fresh actual CAR valid",car_valid,1);check("actual CAR lock",car_locked,1);
  check("actual CAR fault",car_fault,16'h1234);
  force dut.ticks=64'd60000100;
  #1;
  check("UART total 700ms expires",car_valid,0);
  @(posedge clk);#1;force dut.ticks=64'h0000000100000064;#1;
  check("expired CAR cannot resurrect at 32-bit wrap",car_valid,0);
  wr('h284,1,1);check("partial STATE cannot refresh",car_valid,0);
  wr('h288,70000000);wr('h284,2);check("already stale RX invalid",car_valid,0);
  wr('h288,0);wr('h284,2);check("actual unlock valid",car_valid,1);check("actual unlock value",car_locked,0);
  rdreg('h280,rd);check("OSD errors readable",rd,9);rdreg('h290,rd);check("HDMI SOF count readable",rd,12);
  release dut.ticks;
  if(errors==0)$display("TEST PASSED (%0d checks)",checks);else $display("TEST FAILED (%0d errors)",errors);$finish;
 end
 initial begin #2000000;$display("TEST FAILED watchdog");$finish;end
endmodule
