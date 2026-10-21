// Night-B full-size 640x480 AXI4-Stream frame capture.
// Random TVALID/TREADY stress is covered by tb_car_osd_text; this test keeps
// one pixel per cycle so the default production dimensions are practical to
// regress and the PNG is generated from a real RTL output frame.
`timescale 1ns/1ps
module tb_car_osd_fullframe;
 localparam W=640,H=480,PIXELS=W*H;
 reg clk=0,rst=1;always #5 clk=~clk;
 reg [23:0] sd=24'h112233;reg sv=0,su=0,sl=0;wire sr;
 wire [23:0] md;wire mv,mu,ml;reg mr=0;
 wire [15:0] ferr;
 integer x,y,fh,out_count=0,checks=0,errors=0;

 car_axis_osd #(.WIDTH(W),.HEIGHT(H),.ENABLE_TEXT(1)) dut(
  .clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tvalid(sv),.s_axis_tready(sr),
  .s_axis_tuser(su),.s_axis_tlast(sl),
  .m_axis_tdata(md),.m_axis_tvalid(mv),.m_axis_tready(mr),
  .m_axis_tuser(mu),.m_axis_tlast(ml),
  .state_risk_level(2),.state_stop(1),.state_locked(0),
  .state_distance_valid(1),.state_speed_valid(1),
  .state_distance_mm(12'd1234),.state_speed_q16(-(32'sd432*65536)),
  .frame_error_count(ferr));

 always @(posedge clk) begin
  if(!rst && fh!=0 && mv && mr) begin
   $fwrite(fh,"%06x\n",md);
   checks=checks+1;
   if(mu !== (out_count==0))begin errors=errors+1;$display("[FAIL] SOF at %0d",out_count);end
   checks=checks+1;
   if(ml !== ((out_count%W)==W-1))begin errors=errors+1;$display("[FAIL] EOL at %0d",out_count);end
   out_count=out_count+1;
  end
 end

 initial begin
  fh=$fopen("osd_rtl_640x480.rgb","w");
  if(fh==0)begin $display("TEST FAILED cannot open dump");$finish;end
  repeat(4)@(posedge clk);@(negedge clk);rst=0;mr=1;
  for(y=0;y<H;y=y+1)begin
   for(x=0;x<W;x=x+1)begin
    @(negedge clk);sd=24'h112233;su=(x==0&&y==0);sl=(x==W-1);sv=1;
    do @(posedge clk);while(!sr);
   end
  end
  @(negedge clk);sv=0;su=0;sl=0;
  while(out_count<PIXELS)@(posedge clk);
  @(negedge clk);$fclose(fh);fh=0;
  if(ferr!==0)begin errors=errors+1;$display("[FAIL] frame_error_count=%0d",ferr);end
  if(out_count!=PIXELS)begin errors=errors+1;$display("[FAIL] pixels=%0d",out_count);end
  if(errors==0)$display("TEST PASSED (%0d checks)",checks);
  else $display("TEST FAILED (%0d errors)",errors);
  $finish;
 end
 initial begin #20_000_000;$display("TEST FAILED watchdog");$finish;end
endmodule
