`timescale 1ns/1ps
module tb_car_status_osd;
 localparam W=480,H=320;
 reg clk=0,rst=1;always #5 clk=~clk;
 reg [23:0] sd=24'h112233;reg sv=0,su=0,sl=0;wire sr;
 wire [23:0] md;wire mv,mu,ml;reg mr=0;
 reg signed [63:0] net=-64'sd2752512;reg [63:0] path=64'd809086353408;
 reg valid=1,carvalid=1,locked=1,spvalid=1;
 reg [15:0] reasons=16'ha05f,carfault=16'h1234;
 reg signed [31:0] speed=-32'sd8060928;
 wire [31:0] frames;
 integer errors=0,checks=0,fh=0,count=0,seed=32'h05f2026;
 reg held=0;reg [25:0] held_payload;
 car_axis_status_osd #(.WIDTH(W),.HEIGHT(H)) dut(
  .clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tvalid(sv),.s_axis_tready(sr),
  .s_axis_tuser(su),.s_axis_tlast(sl),.m_axis_tdata(md),.m_axis_tvalid(mv),.m_axis_tready(mr),
  .m_axis_tuser(mu),.m_axis_tlast(ml),.state_displacement_q16(net),.state_path_q16(path),
  .state_odometry_valid(valid),.state_reasons(reasons),.state_car_valid(carvalid),
  .state_car_locked(locked),.state_car_fault(carfault),.state_speed_q16(speed),
  .state_speed_valid(spvalid),.committed_frames(frames));
 always @(negedge clk)if(!rst)mr=(($random(seed)&3)!=0);
 always @(posedge clk)if(!rst)begin
  if(held)begin
   checks++;if(!mv||{md,mu,ml}!==held_payload)begin errors++;$display("[FAIL] stalled payload");end
  end
  held=mv&&!mr;held_payload={md,mu,ml};
  if(fh!=0&&mv&&mr)begin
   $fwrite(fh,"%06x\n",md);checks+=2;
   if(mu!==(count==0)||ml!==((count%W)==W-1))begin errors++;$display("[FAIL] markers");end
   count++;
  end
 end
 task frame(input string filename);
  integer x,y,done;
  begin
   fh=$fopen(filename,"w");count=0;
   for(y=0;y<H;y++)for(x=0;x<W;x++)begin
    @(negedge clk);sv=1;su=(x==0&&y==0);sl=x==W-1;
    done=0;while(!done)begin @(posedge clk);if(sr)done=1;end
    @(negedge clk);sv=0;su=0;sl=0;
   end
   while(count<W*H)@(posedge clk);
   @(negedge clk);$fclose(fh);fh=0;
  end
 endtask
 initial begin
  repeat(4)@(posedge clk);@(negedge clk);rst=0;
  fork
   frame("status_f1.rgb");
   begin repeat(200)@(posedge clk);@(negedge clk);valid=0;carvalid=0;reasons=16'h0e13;spvalid=0;end
  join
  frame("status_f2.rgb");
  net=0;path=0;valid=1;carvalid=1;locked=0;carfault=0;reasons=0;speed=0;spvalid=1;
  frame("status_f3.rgb");
  path=64'd6553600000000;net=64'h8000000000000000;speed=65536;
  frame("status_f4.rgb");
  checks++;if(frames!=4)begin errors++;$display("[FAIL] frame commit count");end
  if(errors==0)$display("TEST PASSED (%0d checks)",checks);else $display("TEST FAILED (%0d errors)",errors);
  $finish;
 end
 initial begin #100000000;$display("TEST FAILED watchdog");$finish;end
endmodule
