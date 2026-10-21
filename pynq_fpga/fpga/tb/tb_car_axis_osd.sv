`timescale 1ns/1ps
module tb_car_axis_osd;
 localparam W=16,H=8;reg clk=0,rst=1;always #5 clk=~clk;
 reg [23:0] sd=24'h112233;reg sv=0,su=0,sl=0;wire sr;wire [23:0] md;wire mv,mu,ml;reg mr=0;
 reg [1:0] risk=2;reg stop=1,locked=1,distance_valid=1,speed_valid=1;
 reg [11:0] distance=1000;reg [31:0] speed=0;
 wire [15:0] ferr;integer errors=0,checks=0,x,y;reg [23:0] held;
 car_axis_osd #(.WIDTH(W),.HEIGHT(H)) dut(.clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tvalid(sv),.s_axis_tready(sr),
  .s_axis_tuser(su),.s_axis_tlast(sl),.m_axis_tdata(md),.m_axis_tvalid(mv),.m_axis_tready(mr),.m_axis_tuser(mu),.m_axis_tlast(ml),
  .state_risk_level(risk),.state_stop(stop),.state_locked(locked),
  .state_distance_valid(distance_valid),.state_speed_valid(speed_valid),
  .state_distance_mm(distance),.state_speed_q16(speed),.frame_error_count(ferr));
 task check(input string n,input [31:0] got,input [31:0] want);begin checks++;if(got!==want)begin errors++;$display("[FAIL] %s got=%h want=%h",n,got,want);end end endtask
 task pixel(input integer ix,input integer iy,input [23:0] expected);begin
  @(negedge clk);sd=24'h112233;su=(ix==0&&iy==0);sl=(ix==W-1);sv=1;mr=0;
  do @(posedge clk);while(!sr);@(negedge clk);sv=0;
  // The elastic font stage adds latency; inspect the accepted output event.
  while(!mv)@(negedge clk);
  check("output valid",mv,1);check("pixel color",md,expected);check("SOF passthrough",mu,su);check("EOL passthrough",ml,sl);
  held=md;repeat(3)begin @(posedge clk);check("backpressure stable",md,held);check("valid held",mv,1);end
  @(negedge clk);mr=1;@(posedge clk);@(negedge clk);mr=0;
 end endtask
 function [23:0] red_frame(input integer ix,input integer iy);begin
  red_frame=24'h112233;

 end endfunction
 initial begin
  repeat(4)@(posedge clk);@(negedge clk);rst=0;
  for(y=0;y<H;y++)for(x=0;x<W;x++)begin
   if(x==8&&y==3)risk=0; // must not affect the active frame
   pixel(x,y,red_frame(x,y));
  end
  check("complete frame no error",ferr,0);
  check("mid-frame risk preserved",dut.active_risk,2);
  // Next SOF commits green. Top-left border therefore changes exactly at SOF.
  pixel(0,0,24'h112233);
  check("SOF risk latch",dut.active_risk,0);
 // Deliberately assert EOL early; the module reports and resynchronizes the row.
  @(negedge clk);sd=0;su=0;sl=1;sv=1;mr=1;do @(posedge clk);while(!sr);@(negedge clk);sv=0;mr=0;
  repeat(2)@(posedge clk);check("short line diagnosed",ferr>0,1);
  // Drain the registered early-EOL output before issuing the next input.
  @(negedge clk);mr=1;@(posedge clk);@(negedge clk);mr=0;
  // An unexpected SOF while y!=0 must be diagnosed and must immediately
  // restore the coordinate origin for the accepted SOF pixel.
  pixel(0,0,24'h112233);
  check("SOF risk latch",dut.active_risk,0);
  check("unexpected SOF diagnosed",ferr>=2,1);
  pixel(1,0,24'h112233);
  // Mid-frame reset discards a blocked output, clears diagnostics/coordinates,
  // then the next accepted SOF starts a clean frame.
  @(negedge clk);sd=24'habcdef;su=0;sl=0;sv=1;mr=0;
  do @(posedge clk);while(!sr);
  @(negedge clk);sv=0;while(!mv)@(negedge clk);
  check("blocked output before reset",mv,1);rst=1;
  @(posedge clk);@(negedge clk);
  check("mid-frame reset clears output valid",mv,0);
  check("mid-frame reset clears diagnostic",ferr,0);
  rst=0;
  pixel(0,0,24'h112233);
  check("SOF risk latch",dut.active_risk,0);
  if(errors==0)$display("TEST PASSED (%0d checks)",checks);else $display("TEST FAILED (%0d errors)",errors);$finish;
 end
 initial begin #5000000;$display("TEST FAILED watchdog");$finish;end
endmodule
