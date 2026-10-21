// Sensor function core: no AXI, no private time base.
`resetall
`timescale 1ns/1ps
`default_nettype none
module car_sensors_core(
 input wire clk,input wire rst,input wire [31:0] now_ticks,
 input wire us_echo,output wire us_trig,input wire ir_l_raw,input wire ir_r_raw,
 input wire us_enable,input wire [31:0] us_period,input wire [31:0] us_max_echo,
 input wire [31:0] us_trig_ticks,input wire [31:0] ir_filter_ticks,
 output wire [31:0] us_data,output wire us_valid,output wire [31:0] us_ts,
 output wire [15:0] us_seq,output wire [15:0] us_err,output wire us_update,
 output reg [2:0] ir_status,output reg ir_valid,output reg [31:0] ir_ts,
 output reg [15:0] ir_seq,output reg ir_update
);
 car_ultrasonic us(
  .clk(clk),.rst(rst),.enable(us_enable),.now_ticks(now_ticks),.sample_ts(us_ts),
  .echo(us_echo),.trig(us_trig),.cfg_period(us_period),.cfg_max_echo(us_max_echo),
  .cfg_trig_clk(us_trig_ticks),.samp_data(us_data),.samp_valid(us_valid),
  .samp_update(us_update),.err_cnt(us_err),.samp_seq(us_seq));

 wire ir_l,ir_r,ir_stable;
 car_ir ir(.clk(clk),.rst(rst),.ir_l_raw(ir_l_raw),.ir_r_raw(ir_r_raw),
  .filt_ticks(ir_filter_ticks),.obs_l(ir_l),.obs_r(ir_r),.stable(ir_stable));
 wire [2:0] ir_observed={ir_stable,ir_r,ir_l};
 always @(posedge clk) begin
  if(rst) begin ir_status<=0;ir_valid<=0;ir_ts<=0;ir_seq<=0;ir_update<=0;end
  else begin
   ir_update<=0;
   if(ir_observed!=ir_status) begin
    ir_status<=ir_observed;ir_valid<=ir_stable;ir_ts<=now_ticks;
    ir_seq<=ir_seq+1'b1;ir_update<=1;
   end
  end
 end
endmodule
`resetall
