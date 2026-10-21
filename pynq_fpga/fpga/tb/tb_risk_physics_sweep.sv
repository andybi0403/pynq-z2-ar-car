`timescale 1ns/1ps
module tb_risk_physics_sweep;
 reg clk=0,rst=1;always #5 clk=~clk;
 reg [31:0] velocity=0,distance=4095,stamp=100;
 reg [15:0] source_seq=0;
 wire stop,valid,update;wire [1:0] level;wire [15:0] reasons,seq;
 wire [31:0] required,risk_ts;
 integer errors=0,checks=0,v,old_required=0;
 real physical_speed,physical_required;
 car_risk_core dut(.clk(clk),.rst(rst),.now_ticks(stamp),.enable(1'b1),
  .command_forward(1'b1),.command_valid(1'b1),.command_ts(stamp),
  .us_data(distance),.us_valid(1'b1),.us_ts(stamp),.us_seq(source_seq),
  .ir_status(3'b100),.ir_valid(1'b1),.ir_ts(32'b0),.ir_seq(16'b1),
  .q0_vel(velocity),.q0_valid(1'b1),.q0_ts(stamp),.q0_seq(source_seq),
  .q1_vel(velocity),.q1_valid(1'b1),.q1_ts(stamp),.q1_seq(source_seq),
  .stop_request(stop),.risk_level(level),.reason_bits(reasons),.required_mm(required),
  .risk_ts(risk_ts),.risk_valid(valid),.risk_seq(seq),.risk_update(update));
 task check(input string name,input bit good);begin
  checks++;if(!good)begin errors++;if(errors<8)$display("[FAIL] %s speed=%f required=%d physical=%f",name,physical_speed,required,physical_required);end
 end endtask
 task settle;begin repeat(16)@(negedge clk);end endtask
 initial begin
  repeat(3)@(negedge clk);rst=0;
  for(v=0;v<=5000;v=v+1)begin
   velocity=(v<<16);if(v<5000)velocity=velocity+16'hffff;
   physical_speed=velocity/65536.0;
   physical_required=100+physical_speed*0.15+physical_speed*physical_speed/1000;
   stamp=stamp+1;source_seq=source_seq+1;distance=4095;settle;
   check("conservative real-valued stopping distance",required+0.00001>=physical_required);
   check("monotonic",required>=old_required);old_required=required;
   check("no invented sensor fault",valid && reasons[11:0]==0);
   if(required<=4095)begin
    distance=required;settle;check("red equality",stop && level==2);
    if(required<4095)begin distance=required+1;settle;check("yellow one millimeter",!stop && level==1);end
    if(required+101<=4095)begin distance=required+101;settle;check("green outside yellow",!stop && level==0);end
   end else check("unreachable clearance must stop",stop);
  end
  if(errors==0)$display("TEST PASSED (%0d checks)",checks);else $display("TEST FAILED (%0d errors)",errors);$finish;
 end
 initial begin #100000000;$display("TEST FAILED watchdog");$finish;end
endmodule
