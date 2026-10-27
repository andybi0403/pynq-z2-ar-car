// T-method candidate: scale=Q16.16 mm/wheel-x4-count; period=zero timeout.
// Sequential restoring divider, 64 clocks, floor magnitude, signed saturation.
`timescale 1ns/1ps
`default_nettype none
module car_qei_velocity #(parameter integer CLK_HZ=100000000)(
 input wire clk,rst,
 input wire [31:0] pos_cnt,period_ticks,now_ticks,
 input wire step_pulse,step_dir,period_valid,
 input wire [31:0] cfg_scale,cfg_period,
 input wire [5:0] cfg_shift,
 output reg [31:0] vel_q16,sample_ts,sample_pos,sample_period,
 output reg vel_valid,
 output reg [15:0] vel_seq,
 output reg [15:0] overrun_cnt,
 output reg live_update
);
 reg [31:0] old_scale,old_timeout,age;
 reg [5:0] old_shift;
 reg busy,negative,zero_sent;
 reg [6:0] remaining;
 reg [63:0] quotient;
 reg [32:0] remainder;
 reg [31:0] divisor,job_ts,job_pos,job_period;
 reg [15:0] scale_lo_operand,scale_hi_operand;
 reg [47:0] scale_lo_product,scale_hi_product;
 reg [47:0] scale_lo_result,scale_hi_result;
 reg [63:0] numerator;
 reg [2:0] config_ready;
 // 100 MHz has eight low zero bits. Factor them out so each 16-bit scale
 // slice multiplies a 19-bit constant, which fits one DSP48E1 multiplier.
 // The zero-shift fallback keeps other CLK_HZ parameter values exact.
 localparam integer RATE_SHIFT=(CLK_HZ % 256 == 0) ? 8 : 0;
 localparam [47:0] RATE_FACTOR=CLK_HZ >> RATE_SHIFT;
 localparam integer RATE_FACTOR_WIDTH=(RATE_FACTOR <= 1) ? 1 : $clog2(RATE_FACTOR+1'b1);
 localparam [RATE_FACTOR_WIDTH-1:0] RATE_FACTOR_NARROW=RATE_FACTOR;
 wire [32:0] trial={remainder[31:0],quotient[63]};
 wire subtract=trial>={1'b0,divisor};
 wire [63:0] next_q={quotient[62:0],subtract};
 wire configured=cfg_scale!=0 && cfg_period>=66 && cfg_shift==0;
 wire changed=cfg_scale!=old_scale || cfg_period!=old_timeout || cfg_shift!=old_shift;
 always @(posedge clk) begin
  if(rst) begin
   old_scale<=0;old_timeout<=0;old_shift<=0;age<=0;busy<=0;
   negative<=0;zero_sent<=0;remaining<=0;quotient<=0;remainder<=0;
   divisor<=0;job_ts<=0;job_pos<=0;job_period<=0;
   vel_q16<=0;vel_valid<=0;vel_seq<=0;overrun_cnt<=0;live_update<=0;
   sample_ts<=0;sample_pos<=0;sample_period<=0;
   scale_lo_operand<=0;scale_hi_operand<=0;
   scale_lo_product<=0;scale_hi_product<=0;
   scale_lo_result<=0;scale_hi_result<=0;numerator<=0;config_ready<=0;
  end else begin
   live_update<=0;
   old_scale<=cfg_scale;old_timeout<=cfg_period;old_shift<=cfg_shift;
   // Pipeline the calibration constant, avoiding multiply+wide carry in
   // the divider load path. Ignore edges until the new constant is settled.
   scale_lo_operand<=cfg_scale[15:0];
   scale_hi_operand<=cfg_scale[31:16];
   scale_lo_product<=scale_lo_operand*RATE_FACTOR_NARROW;
   scale_hi_product<=scale_hi_operand*RATE_FACTOR_NARROW;
   scale_lo_result<=scale_lo_product<<RATE_SHIFT;
   scale_hi_result<=scale_hi_product<<RATE_SHIFT;
   numerator<={16'b0,scale_lo_result}+{scale_hi_result,16'b0};
   if(changed) config_ready<=0;
   else if(config_ready<4) config_ready<=config_ready+1'b1;
   if(age!=32'hffffffff) age<=age+1'b1;
   if(changed || !configured || config_ready<4) begin
    busy<=0;age<=0;zero_sent<=0;vel_valid<=0;vel_q16<=0;
   end else if(step_pulse) begin
    age<=0;zero_sent<=0;
    // Keep the last completed batch valid during an ordinary 64-cycle divide.
    // If a new edge outruns the divider, count it, invalidate stale velocity,
    // and restart from the newest period instead of failing silently.
    if(busy) begin
     if(overrun_cnt!=16'hffff) overrun_cnt<=overrun_cnt+1'b1;
     vel_valid<=0;
    end
    if(period_valid && period_ticks>=66 && period_ticks<cfg_period) begin
     quotient<=numerator;
     remainder<=0;divisor<=period_ticks;remaining<=64;busy<=1;
     negative<=!step_dir;job_ts<=now_ticks;job_pos<=pos_cnt;job_period<=period_ticks;
    end else begin busy<=0;vel_valid<=0;end
   end else if(age>=cfg_period-1) begin
    busy<=0;vel_q16<=0;vel_valid<=1;
    // A complete new no-edge observation window, not a host heartbeat.
    age<=0;zero_sent<=1;sample_ts<=now_ticks;sample_pos<=pos_cnt;sample_period<=0;
    vel_seq<=vel_seq+1'b1;live_update<=1;
   end else if(!period_valid && !zero_sent) begin
    busy<=0;vel_valid<=0;
   end else if(busy) begin
    quotient<=next_q;
    remainder<=subtract ? trial-{1'b0,divisor} : trial;
    remaining<=remaining-1'b1;
    if(remaining==1) begin
     busy<=0;vel_valid<=1;live_update<=1;vel_seq<=vel_seq+1'b1;
     sample_ts<=job_ts;sample_pos<=job_pos;sample_period<=job_period;
     if(negative) vel_q16<=next_q>=64'h80000000 ? 32'h80000000 : -next_q[31:0];
     else vel_q16<=next_q>64'h7fffffff ? 32'h7fffffff : next_q[31:0];
    end
   end
  end
 end
endmodule
`default_nettype wire
