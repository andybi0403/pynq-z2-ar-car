`timescale 1ns/1ps
module tb_ir_batch_repro;
reg clk=0,rst=1,l=1;always #5 clk=~clk;
reg[31:0]ticks=0;always @(posedge clk)ticks<=ticks+1;
wire[2:0]status;wire valid,update;wire[31:0]ts;wire[15:0]seq;
car_sensors_core dut(.clk(clk),.rst(rst),.now_ticks(ticks),.us_echo(1'b0),.ir_l_raw(l),.ir_r_raw(1'b1),
.us_enable(1'b0),.us_period(32'd20),.us_max_echo(32'd50),.us_trig_ticks(32'd2),.ir_filter_ticks(32'd3),
.ir_status(status),.ir_valid(valid),.ir_ts(ts),.ir_seq(seq),.ir_update(update));
reg[2:0]prev_status=0;reg[15:0]prev_seq=0;integer mixed=0;
always @(negedge clk)begin
 if(!rst && seq==prev_seq && status!=prev_status)begin mixed=mixed+1;$display("REPRO_IR_MIXED_BATCH status=%b seq=%d",status,seq);end
 prev_status=status;prev_seq=seq;
end
initial begin
 repeat(5)@(negedge clk);rst=0;repeat(20)@(negedge clk);l=0;repeat(20)@(negedge clk);l=1;repeat(20)@(negedge clk);
 if(mixed==0)$fatal(1,"IR mismatch not reproduced");
 $display("TEST PASSED (1 checks) -- known defect reproduced, not product acceptance");$finish;
end
initial begin #5000;$fatal(1,"watchdog");end
endmodule
