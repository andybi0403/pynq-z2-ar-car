`timescale 1ns/1ps
// Real legal quadrature input, with alternating intervals that overrun the
// divider. No forced internal counter: test the exported diagnostic at 256.
module tb_car_qei_diagnostics;
 reg clk=0; always #5 clk=~clk;
 reg rst=1; reg [31:0] now_ticks=0;
 always @(posedge clk) now_ticks<=now_ticks+1;
 reg [1:0] ab=0;
 wire [31:0] info0,info1;
 integer checks=0,errors=0,i;
 car_qei_core dut(.clk(clk),.rst(rst),.now_ticks(now_ticks),.odo_clear(1'b0),
  .qei0_a(ab[1]),.qei0_b(ab[0]),.qei1_a(ab[1]),.qei1_b(ab[0]),
  .qei0_dir(1'b0),.qei0_filter(32'd0),.qei0_scale(32'd5362),.qei0_zero(32'd1000000),
  .qei1_dir(1'b0),.qei1_filter(32'd0),.qei1_scale(32'd5362),.qei1_zero(32'd1000000),
  .q0_info(info0),.q1_info(info1));
 task ticks(input integer n); repeat(n) @(negedge clk); endtask
 task advance(input integer dwell);
  begin
   case(ab) 0:ab=2;2:ab=3;3:ab=1;1:ab=0;endcase
   ticks(dwell);
  end
 endtask
 task check(input bit ok,input string label);
  begin checks++; if(!ok) begin errors++;$display("[FAIL] %s",label);end end
 endtask
 initial begin
  ticks(4);rst=0;ticks(20);
  check(info0[19:12]==0&&info1[19:12]==0,"clean reset diagnostic");
  // Prime a valid period, then a 10-cycle interval arrives during division.
  advance(100);advance(100);
  for(i=1;i<=257;i++) begin
   advance(10);advance(100);advance(100);advance(100);
   check(dut.vel0.overrun_cnt==i&&dut.vel1.overrun_cnt==i,"one genuine overrun per cycle");
   check(info0[19:12]==((i>255)?255:i)&&info1[19:12]==((i>255)?255:i),"export saturates across 255/256/257");
   check(info0[11:4]==0&&info1[11:4]==0,"legal quadrature; no illegal diagnostic contamination");
  end
  ticks(100);
  check(dut.q0_valid&&dut.q1_valid,"divider recovers valid velocity while retaining diagnostic");
  check(info0[19:12]==255&&info1[19:12]==255,"recovery never erases cumulative fault");
  if(errors==0)$display("TEST PASSED (%0d checks)",checks);
  else $display("TEST FAILED (%0d errors)",errors);
  $finish;
 end
 initial begin #2000000;$fatal(1,"TEST FAILED: watchdog");end
endmodule
