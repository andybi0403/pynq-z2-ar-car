// Night-B text rendering and actual AXI output capture.
// Producer inserts deterministic TVALID gaps. Consumer inserts deterministic
// TREADY stalls. Pixels are dumped only on real m_axis TVALID&&TREADY events.
// Seeds: producer=0x20260919, consumer=0x0BADF00D.
`timescale 1ns/1ps
module tb_car_osd_text;
 localparam W=480, H=112, PIXELS=W*H;
 reg clk=0,rst=1;always #5 clk=~clk;
 reg [23:0] sd=24'h112233;reg sv=0,su=0,sl=0;wire sr;
 wire [23:0] md;wire mv,mu,ml;reg mr=0;
 reg [1:0] risk=0;reg stop=0,locked=0,dvalid=1,spvalid=1;
 reg [11:0] distance_r=1000;reg [31:0] speed=32'd200000000;
 wire [15:0] ferr;
 integer errors=0,checks=0,fh=0,out_count=0;
 integer seed_prod=32'h20260919,seed_cons=32'h0BADF00D;

 car_axis_osd #(.WIDTH(W),.HEIGHT(H),.ENABLE_TEXT(1)) dut(
  .clk(clk),.rst(rst),
  .s_axis_tdata(sd),.s_axis_tvalid(sv),.s_axis_tready(sr),
  .s_axis_tuser(su),.s_axis_tlast(sl),
  .m_axis_tdata(md),.m_axis_tvalid(mv),.m_axis_tready(mr),
  .m_axis_tuser(mu),.m_axis_tlast(ml),
  .state_risk_level(risk),.state_stop(stop),.state_locked(locked),
  .state_distance_valid(dvalid),.state_speed_valid(spvalid),
  .state_distance_mm(distance_r),.state_speed_q16(speed),
  .frame_error_count(ferr));

 always @(negedge clk) begin
  if(rst) mr=0;
  else mr=(($random(seed_cons)&32'h3)!=0);
 end

 always @(posedge clk) begin
  if(!rst && fh!=0 && mv && mr) begin
   $fwrite(fh,"%06x\n",md);
   checks=checks+1;
   if(mu !== (out_count==0)) begin
    errors=errors+1;$display("[FAIL] SOF mismatch out=%0d",out_count);
   end
   checks=checks+1;
   if(ml !== ((out_count%W)==W-1)) begin
    errors=errors+1;$display("[FAIL] EOL mismatch out=%0d",out_count);
   end
   out_count=out_count+1;
  end
 end

 task automatic send_frame_dump(input [8*32:1] path);
  integer x,y,gap,accepted;
  begin
   fh=$fopen(path,"w");
   if(fh==0)begin errors=errors+1;$display("[FAIL] cannot open %0s",path);end
   out_count=0;
   for(y=0;y<H;y=y+1)begin
    for(x=0;x<W;x=x+1)begin
     gap=$random(seed_prod)%3;if(gap<0)gap=-gap;
     @(negedge clk);sv=0;
     repeat(gap)@(negedge clk);
     sd=24'h112233;su=(x==0&&y==0);sl=(x==W-1);sv=1;
     accepted=0;
     while(!accepted)begin
      @(posedge clk);
      if(sr)accepted=1;
     end
     @(negedge clk);sv=0;su=0;sl=0;
    end
   end
   while(out_count<PIXELS)@(posedge clk);
   @(negedge clk);$fclose(fh);fh=0;
   checks=checks+1;
   if(out_count!=PIXELS)begin errors=errors+1;$display("[FAIL] pixel count %0d",out_count);end
  end
 endtask

 initial begin
  $dumpfile("tb_car_osd_text.vcd");$dumpvars(0,tb_car_osd_text);
  repeat(4)@(posedge clk);@(negedge clk);rst=0;repeat(2)@(posedge clk);
  risk=1;stop=0;locked=0;dvalid=1;spvalid=1;distance_r=1000;speed=32'd200000000;
  send_frame_dump("osd_rtl_f1.rgb");
  risk=1;dvalid=1;spvalid=1;distance_r=750;speed=-(32'd1234*65536);
  send_frame_dump("osd_rtl_f2.rgb");
  risk=3;stop=0;locked=0;dvalid=0;spvalid=0;distance_r=12'hFFF;speed=32'h80000000;
  send_frame_dump("osd_rtl_f3.rgb");
  risk=2;stop=1;locked=1;dvalid=1;spvalid=1;distance_r=500;speed=32'd100000000;
  fork
   send_frame_dump("osd_rtl_f4.rgb");
   begin
    repeat(200)@(posedge clk);
    risk=0;stop=0;locked=0;distance_r=2000;speed=32'd300000000;
   end
  join
  send_frame_dump("osd_rtl_f5.rgb");
  // Independent validity channels from the v0.6 US and QEI shadow groups.
  dvalid=1;spvalid=0;distance_r=321;speed=32'd65536;
  send_frame_dump("osd_rtl_f6.rgb");
  dvalid=0;spvalid=1;distance_r=12'hFFF;speed=-(32'd42*65536);
  send_frame_dump("osd_rtl_f7.rgb");
  if(errors==0)$display("TEST PASSED (%0d checks)",checks);
  else $display("TEST FAILED (%0d checks, %0d errors)",checks,errors);
  $finish;
 end
 initial begin #2_000_000_000;$display("TEST FAILED watchdog");$finish;end
endmodule
