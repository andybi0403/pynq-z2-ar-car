// Physical wheel displacement and travelled distance in the PL.
// SCALE is unsigned Q16.16 mm per x4 count. No multiplier, private clock,
// or private timebase. Calibration/phase changes start a new zero epoch.
`resetall
`timescale 1ns/1ps
`default_nettype none
module car_qei_odometry(
 input wire clk,input wire rst,input wire [31:0] now_ticks,
 input wire step_pulse,input wire step_positive,input wire count_fault,
 input wire clear,input wire [31:0] cfg_scale,
 output reg signed [63:0] displacement_q16,
 output reg [63:0] travelled_q16,
 output reg valid,output reg fault,
 output reg [31:0] sample_ts,output reg [15:0] epoch,output reg [15:0] seq
);
 reg [31:0] saved_scale;
 wire signed [63:0] increment=$signed({32'b0,cfg_scale});
 wire signed [63:0] net_next=step_positive ? displacement_q16+increment : displacement_q16-increment;
 wire net_overflow=step_positive ? (!displacement_q16[63]&&net_next[63]) :
                                     (displacement_q16[63]&&!net_next[63]);
 wire [64:0] path_next={1'b0,travelled_q16}+{33'b0,cfg_scale};
 always @(posedge clk) begin
  if(rst) begin
   saved_scale<=0;displacement_q16<=0;travelled_q16<=0;valid<=0;fault<=0;
   sample_ts<=0;epoch<=0;seq<=0;
  end else if(clear||cfg_scale!=saved_scale) begin
   saved_scale<=cfg_scale;displacement_q16<=0;travelled_q16<=0;
   valid<=cfg_scale!=0;fault<=0;sample_ts<=now_ticks;epoch<=epoch+1'b1;seq<=seq+1'b1;
  end else if(count_fault) begin
   valid<=0;fault<=1;
   if(!fault) begin sample_ts<=now_ticks;seq<=seq+1'b1;end
  end else if(step_pulse&&cfg_scale!=0&&!fault) begin
   sample_ts<=now_ticks;seq<=seq+1'b1;
   if(net_overflow||path_next[64]) begin
    valid<=0;fault<=1;
    if(net_overflow) displacement_q16<=step_positive ? 64'h7fffffffffffffff : 64'h8000000000000000;
    else displacement_q16<=net_next;
    travelled_q16<=path_next[64] ? 64'hffffffffffffffff : path_next[63:0];
   end else begin
    displacement_q16<=net_next;travelled_q16<=path_next[63:0];valid<=1;
   end
  end
 end
endmodule
`resetall
