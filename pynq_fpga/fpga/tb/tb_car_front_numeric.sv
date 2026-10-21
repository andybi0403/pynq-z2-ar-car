`timescale 1ns/1ps
module tb_car_front_numeric;
 reg clk=0,rst=1,valid=0;always #5 clk=~clk;
 reg [11:0] distance=0;wire ready;wire [23:0] data;wire out_valid,user,last;
 integer mm,errors=0,checks=0;reg [11:0] expected;
 car_axis_front_overlay dut(.clk(clk),.rst(rst),.s_axis_tdata(24'h112233),
  .s_axis_tvalid(valid),.s_axis_tready(ready),.s_axis_tuser(1'b1),.s_axis_tlast(1'b1),
  .m_axis_tdata(data),.m_axis_tvalid(out_valid),.m_axis_tready(1'b1),
  .m_axis_tuser(user),.m_axis_tlast(last),.state_valid(1'b1),
  .state_distance_valid(1'b1),.state_distance_mm(distance),.state_risk_level(2'd0),.state_stop(1'b0));
 initial begin
  repeat(5)@(negedge clk);rst=0;
  // Independent decimal arithmetic covers every representable sensor value.
  for(mm=0;mm<4096;mm++)begin
   @(negedge clk);distance=mm;valid=1;
   do @(posedge clk);while(!ready);
   @(negedge clk);valid=0;repeat(14)@(negedge clk);
   expected=((mm/1000)<<8)|(((mm/100)%10)<<4)|((mm/10)%10);
   checks++;
   if(dut.cm_bcd!==expected||dut.converting)begin
    errors++;$display("[FAIL] distance=%0d got=%03x expected=%03x",mm,dut.cm_bcd,expected);
   end
  end
  if(errors==0)$display("TEST PASSED (%0d checks)",checks);else $display("TEST FAILED (%0d errors)",errors);
  $finish;
 end
 initial begin #2000000;$display("TEST FAILED watchdog");$finish;end
endmodule
