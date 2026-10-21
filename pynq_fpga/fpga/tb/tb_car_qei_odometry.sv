`timescale 1ns/1ps
module tb_car_qei_odometry;
 reg clk=0;always #5 clk=~clk;
 reg rst=1;reg [31:0] now_ticks=0;always @(posedge clk) now_ticks<=now_ticks+1;
 reg step_pulse=0,step_positive=1,count_fault=0,clear=0;reg [31:0] scale=0;
 wire signed [63:0] displacement;wire [63:0] travelled;
 wire valid,fault;wire [31:0] sample_ts;wire [15:0] epoch,seq;
 integer checks=0,failures=0;reg [31:0] saved_ts;reg [15:0] saved_seq;
 car_qei_odometry dut(.clk(clk),.rst(rst),.now_ticks(now_ticks),.step_pulse(step_pulse),
  .step_positive(step_positive),.count_fault(count_fault),.clear(clear),.cfg_scale(scale),
  .displacement_q16(displacement),.travelled_q16(travelled),.valid(valid),.fault(fault),
  .sample_ts(sample_ts),.epoch(epoch),.seq(seq));
 task check(input bit ok,input string label);
  begin checks++;if(!ok)begin failures++;$display("[FAIL] %s",label);end end
 endtask
 task edge_count(input bit positive);
  begin @(negedge clk);step_positive=positive;step_pulse=1;
   @(negedge clk);step_pulse=0;end
 endtask
 initial begin
  repeat(3)@(negedge clk);rst=0;@(negedge clk);
  check(!valid&&displacement==0&&travelled==0,"uncalibrated reset");
  edge_count(1);check(!valid&&travelled==0,"uncalibrated edge ignored");
  scale=32'd32768;@(negedge clk);
  check(valid&&epoch==1&&displacement==0,"explicit half-mm calibration starts epoch");
  edge_count(1);edge_count(1);edge_count(1);
  check(displacement==98304&&travelled==98304,"three positive x4 counts = 1.5mm");
  edge_count(0);check(displacement==65536&&travelled==131072,"reverse decreases displacement only");
  saved_ts=sample_ts;saved_seq=seq;repeat(10)@(negedge clk);
  check(sample_ts==saved_ts&&seq==saved_seq&&valid,"no fictitious stationary samples");
  clear=1;@(negedge clk);clear=0;@(negedge clk);
  check(epoch==2&&displacement==0&&travelled==0&&valid,"explicit clear resets signed and path totals");
  edge_count(0);check(displacement==-32768&&travelled==32768,"negative half-mm displacement");
  scale=65536;@(negedge clk);
  check(epoch==3&&travelled==0&&displacement==0,"scale change never reinterprets old counts");
  edge_count(1);count_fault=1;@(negedge clk);count_fault=0;
  check(fault&&!valid&&travelled==65536,"illegal quadrature marks distance invalid");
  edge_count(1);check(travelled==65536&&!valid,"fault sticky; subsequent edges do not repair lost distance");
  clear=1;@(negedge clk);clear=0;@(negedge clk);
  check(valid&&!fault&&epoch==4,"explicit clear starts new trusted epoch");
  @(negedge clk);dut.displacement_q16=64'h7fffffffffff0000;
  edge_count(1);check(fault&&!valid&&displacement==64'h7fffffffffffffff,"positive saturation does not wrap");
  clear=1;@(negedge clk);clear=0;@(negedge clk);
  dut.displacement_q16=64'h8000000000000001;
  edge_count(0);check(fault&&!valid&&displacement==64'h8000000000000000,"negative saturation does not wrap");
  clear=1;@(negedge clk);clear=0;@(negedge clk);
  dut.travelled_q16=64'hffffffffffff0000;
  edge_count(1);check(fault&&!valid&&travelled==64'hffffffffffffffff,"path overflow saturates and invalidates");
  scale=0;@(negedge clk);edge_count(1);
  check(!valid&&!fault&&travelled==0&&displacement==0,"remove calibration returns to zero invalid");
  if(failures==0)$display("TEST PASSED (%0d checks)",checks);
  else $display("TEST FAILED: %0d/%0d",failures,checks);
  $finish;
 end
 initial begin #20000;$display("TEST FAILED: timeout");$finish;end
endmodule
