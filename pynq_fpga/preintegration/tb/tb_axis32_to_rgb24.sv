`timescale 1ns/1ps
module tb_axis32_to_rgb24;
 reg clk=0,aresetn=0;
 reg [31:0] sd=0;reg [3:0] sk=0;reg sv=0;wire sr;reg su=0,sl=0;
 wire [23:0] md;wire mv;reg mr=0;wire mu,ml;wire [15:0] errors;
 reg auto_ready=1;
 integer checks=0,failures=0,sent=0,received=0,cycles=0;
 reg [23:0] exp_data[0:127];reg exp_user[0:127];reg exp_last[0:127];
 axis32_to_rgb24 dut(.aclk(clk),.aresetn(aresetn),.s_axis_tdata(sd),.s_axis_tkeep(sk),
  .s_axis_tvalid(sv),.s_axis_tready(sr),.s_axis_tuser(su),.s_axis_tlast(sl),
  .m_axis_tdata(md),.m_axis_tvalid(mv),.m_axis_tready(mr),.m_axis_tuser(mu),
  .m_axis_tlast(ml),.format_error_count(errors));
 always #5 clk=~clk;
 task check;input cond;input [255:0] msg;begin checks=checks+1;if(!cond)begin failures=failures+1;$display("[FAIL] %s",msg);end end endtask
 always @(posedge clk) begin
  if(aresetn) begin
   cycles<=cycles+1;
   if(auto_ready) mr<=((cycles%5)!=1);
   if(mv&&mr&&received<100)begin
    check(md===exp_data[received],"data mismatch");check(mu===exp_user[received],"tuser mismatch");check(ml===exp_last[received],"tlast mismatch");received<=received+1;
   end
  end
 end
 initial begin
  repeat(3)@(posedge clk);aresetn<=1;
  while(sent<100)begin
   @(negedge clk);
   // Drive with blocking assignments at the inactive edge so the scoreboard
   // records the same beat that the DUT will sample at the next posedge.
   sv=((sent+cycles)%4)!=0;
   sd={8'ha5,sent[23:0]};sk=(sent==37)?4'b1001:4'b1111;su=(sent==0);sl=((sent%20)==19);
   if(sv&&sr)begin exp_data[sent]=sent[23:0];exp_user[sent]=(sent==0);exp_last[sent]=((sent%20)==19);sent=sent+1;end
  end
  @(negedge clk);sv=0;
  while(received<100 && cycles<1000)@(posedge clk);
  check(received==100,"all beats received");check(errors==1,"one malformed keep counted");
  while(mv) @(posedge clk);
  @(negedge clk);auto_ready=0;mr=0;sv=1;sd=32'h12345678;sk=4'hf;su=1;sl=1;
  // An empty one-beat output register may accept one beat. It must then
  // deassert ready and hold that beat while the sink remains stalled.
  @(posedge clk);#1;
  repeat(4)begin @(posedge clk);#1;check(!sr,"backpressure reaches source");check(md==24'h345678,"stalled data stable");end
  aresetn<=0;@(posedge clk);#1;check(!mv,"reset clears valid");check(errors==0,"reset clears error counter");
  if(failures==0)$display("TEST PASSED (%0d checks)",checks);else $display("TEST FAILED (%0d/%0d)",failures,checks);
  $finish;
 end
 initial begin #200000;$display("TEST FAILED (watchdog)");$finish;end
endmodule
