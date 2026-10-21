// Dual QEI function core: no AXI and no private time base.
`resetall
`timescale 1ns/1ps
`default_nettype none
module car_qei_core(
 input wire clk,input wire rst,input wire [31:0] now_ticks,input wire odo_clear,
 input wire qei0_a,input wire qei0_b,input wire qei1_a,input wire qei1_b,
 input wire qei0_dir,input wire [31:0] qei0_filter,input wire [31:0] qei0_scale,input wire [31:0] qei0_zero,
 input wire qei1_dir,input wire [31:0] qei1_filter,input wire [31:0] qei1_scale,input wire [31:0] qei1_zero,
 output wire [31:0] q0_pos,output wire [31:0] q0_period,output wire [31:0] q0_vel,
 output wire [31:0] q0_ts,output wire q0_valid,output wire [15:0] q0_seq,
 output wire [31:0] q0_info,output wire q0_update,
 output wire [31:0] q1_pos,output wire [31:0] q1_period,output wire [31:0] q1_vel,
 output wire [31:0] q1_ts,output wire q1_valid,output wire [15:0] q1_seq,
 output wire [31:0] q1_info,output wire q1_update,
 output wire signed [63:0] odo0_disp,output wire [63:0] odo0_path,
 output wire [31:0] odo0_ts,output wire odo0_valid,output wire odo0_fault,
 output wire [15:0] odo0_epoch,output wire [15:0] odo0_seq,
 output wire signed [63:0] odo1_disp,output wire [63:0] odo1_path,
 output wire [31:0] odo1_ts,output wire odo1_valid,output wire odo1_fault,
 output wire [15:0] odo1_epoch,output wire [15:0] odo1_seq
);
 wire [31:0] p0_live,p1_live,per0_live,per1_live;
 wire d0_live,d1_live,seen0,seen1,pv0,pv1,step0,step1,stepdir0,stepdir1;
 wire [7:0] ill0,ill1,filt0,filt1;
 car_qei dec0(.clk(clk),.rst(rst),.a_raw(qei0_a),.b_raw(qei0_b),.cfg_dir(qei0_dir),.cfg_filt(qei0_filter),
  .pos_cnt(p0_live),.dir_pos(d0_live),.seen_edge(seen0),.ill_cnt(ill0),.filt_rej_cnt(filt0),
  .period_ticks(per0_live),.period_valid(pv0),.step_pulse(step0),.step_dir(stepdir0));
 car_qei dec1(.clk(clk),.rst(rst),.a_raw(qei1_a),.b_raw(qei1_b),.cfg_dir(qei1_dir),.cfg_filt(qei1_filter),
  .pos_cnt(p1_live),.dir_pos(d1_live),.seen_edge(seen1),.ill_cnt(ill1),.filt_rej_cnt(filt1),
  .period_ticks(per1_live),.period_valid(pv1),.step_pulse(step1),.step_dir(stepdir1));
 wire [15:0] over0,over1;
 car_qei_velocity vel0(.clk(clk),.rst(rst),.pos_cnt(p0_live),.period_ticks(per0_live),.now_ticks(now_ticks),
  .step_pulse(step0),.step_dir(stepdir0),.period_valid(pv0),.cfg_scale(qei0_scale),.cfg_period(qei0_zero),.cfg_shift(6'b0),
  .vel_q16(q0_vel),.sample_ts(q0_ts),.sample_pos(q0_pos),.sample_period(q0_period),.vel_valid(q0_valid),
  .vel_seq(q0_seq),.overrun_cnt(over0),.live_update(q0_update));
 car_qei_velocity vel1(.clk(clk),.rst(rst),.pos_cnt(p1_live),.period_ticks(per1_live),.now_ticks(now_ticks),
  .step_pulse(step1),.step_dir(stepdir1),.period_valid(pv1),.cfg_scale(qei1_scale),.cfg_period(qei1_zero),.cfg_shift(6'b0),
  .vel_q16(q1_vel),.sample_ts(q1_ts),.sample_pos(q1_pos),.sample_period(q1_period),.vel_valid(q1_valid),
  .vel_seq(q1_seq),.overrun_cnt(over1),.live_update(q1_update));
 // The exported 8-bit diagnostic saturates; truncation would hide every
 // 256th overrun even though the underlying divider counter is nonzero.
 wire [7:0] over0_export=(|over0[15:8]) ? 8'hff : over0[7:0];
 wire [7:0] over1_export=(|over1[15:8]) ? 8'hff : over1[7:0];
 assign q0_info={4'b0,filt0,over0_export,ill0,1'b0,pv0,seen0,d0_live};
 assign q1_info={4'b0,filt1,over1_export,ill1,1'b0,pv1,seen1,d1_live};

 // A missed/illegal edge makes physical distance unknowable. Saturation of
 // the decoder diagnostic remains a fault even after an odometer clear.
 reg [7:0] prev_ill0,prev_ill1;
 reg prev_dir0,prev_dir1;
 reg [31:0] prev_filter0,prev_filter1;
 always @(posedge clk) begin
  if(rst) begin
   prev_ill0<=0;prev_ill1<=0;prev_dir0<=0;prev_dir1<=0;
   prev_filter0<=0;prev_filter1<=0;
  end else begin
   prev_ill0<=ill0;prev_ill1<=ill1;
   prev_dir0<=qei0_dir;prev_dir1<=qei1_dir;
   prev_filter0<=qei0_filter;prev_filter1<=qei1_filter;
  end
 end
 car_qei_odometry odo0(.clk(clk),.rst(rst),.now_ticks(now_ticks),
  .step_pulse(step0),.step_positive(stepdir0),
  .count_fault((ill0!=prev_ill0)||(ill0==8'hff)),
  .clear(odo_clear||(prev_dir0!=qei0_dir)||(prev_filter0!=qei0_filter)),
  .cfg_scale(qei0_scale),.displacement_q16(odo0_disp),.travelled_q16(odo0_path),
  .valid(odo0_valid),.fault(odo0_fault),.sample_ts(odo0_ts),.epoch(odo0_epoch),.seq(odo0_seq));
 car_qei_odometry odo1(.clk(clk),.rst(rst),.now_ticks(now_ticks),
  .step_pulse(step1),.step_positive(stepdir1),
  .count_fault((ill1!=prev_ill1)||(ill1==8'hff)),
  .clear(odo_clear||(prev_dir1!=qei1_dir)||(prev_filter1!=qei1_filter)),
  .cfg_scale(qei1_scale),.displacement_q16(odo1_disp),.travelled_q16(odo1_path),
  .valid(odo1_valid),.fault(odo1_fault),.sample_ts(odo1_ts),.epoch(odo1_epoch),.seq(odo1_seq));
endmodule
`resetall
