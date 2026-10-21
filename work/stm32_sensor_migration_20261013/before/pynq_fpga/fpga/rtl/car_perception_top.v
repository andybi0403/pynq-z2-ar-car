// Integrated perception/control-data top: one clock, one time base, one AXI slave,
// one global snapshot. Existing car_*_top modules remain verification wrappers.
`resetall
`timescale 1ns/1ps
`default_nettype none
`include "car_reg_defs.vh"
module car_perception_top(
 input wire clk,input wire rst,
 input wire us_echo,output wire us_trig,input wire ir_l_raw,input wire ir_r_raw,
 input wire qei0_a,input wire qei0_b,input wire qei1_a,input wire qei1_b,
 output wire risk_stop_o,output wire [1:0] risk_level_o,output wire [15:0] risk_reasons_o,
 output wire [11:0] osd_distance_mm_o,output wire osd_distance_valid_o,
 output wire [31:0] osd_speed_q16_o,output wire osd_speed_valid_o,
 output wire signed [63:0] osd_displacement_q16_o,output wire [63:0] osd_path_q16_o,
 output wire osd_odometry_valid_o,output wire osd_car_valid_o,output wire osd_car_locked_o,
 output wire [15:0] osd_car_fault_o,input wire [15:0] osd_errors_i,input wire [31:0] osd_frames_i,
 output wire [63:0] osd_live_ticks_o,
 input wire [31:0] display_frame_id_i,display_frame_state_i,
 input wire [63:0] display_frame_ticks_i,
 input wire [63:0] display_frame_sof_i,
 input wire [15:0] display_header_errors_i,
 input wire [31:0] display_repeats_i,display_tag_count_i,display_frame_age_i,
 input wire [11:0] s_axil_awaddr,input wire [2:0] s_axil_awprot,input wire s_axil_awvalid,output wire s_axil_awready,
 input wire [31:0] s_axil_wdata,input wire [3:0] s_axil_wstrb,input wire s_axil_wvalid,output wire s_axil_wready,
 output wire [1:0] s_axil_bresp,output wire s_axil_bvalid,input wire s_axil_bready,
 input wire [11:0] s_axil_araddr,input wire [2:0] s_axil_arprot,input wire s_axil_arvalid,output wire s_axil_arready,
 output wire [31:0] s_axil_rdata,output wire [1:0] s_axil_rresp,output wire s_axil_rvalid,input wire s_axil_rready
);
 wire [63:0] ticks;
 car_time_counter #(.WIDTH(64)) timebase(.clk(clk),.rst(rst),.count(ticks));
 assign osd_live_ticks_o=ticks;

 reg us_enable;reg [31:0] us_period,us_max_echo,us_trig_ticks,ir_filter;
 reg q0_dir_cfg,q1_dir_cfg;reg [31:0] q0_filter_cfg,q0_scale_cfg,q0_zero_cfg,q1_filter_cfg,q1_scale_cfg,q1_zero_cfg;
 reg command_forward,command_valid,risk_enable;reg [31:0] command_ts;
 wire [31:0] us_data,us_ts;wire us_valid,us_update;wire [15:0] us_seq,us_err;
 wire [2:0] ir_status;wire ir_valid,ir_update;wire [31:0] ir_ts;wire [15:0] ir_seq;
 car_sensors_core sensors(.clk(clk),.rst(rst),.now_ticks(ticks[31:0]),.us_echo(us_echo),.us_trig(us_trig),
  .ir_l_raw(ir_l_raw),.ir_r_raw(ir_r_raw),.us_enable(us_enable),.us_period(us_period),.us_max_echo(us_max_echo),
  .us_trig_ticks(us_trig_ticks),.ir_filter_ticks(ir_filter),.us_data(us_data),.us_valid(us_valid),.us_ts(us_ts),
  .us_seq(us_seq),.us_err(us_err),.us_update(us_update),.ir_status(ir_status),.ir_valid(ir_valid),.ir_ts(ir_ts),
  .ir_seq(ir_seq),.ir_update(ir_update));

 wire [31:0] q0_pos,q0_period,q0_vel,q0_ts,q0_info,q1_pos,q1_period,q1_vel,q1_ts,q1_info;
 wire q0_valid,q0_update,q1_valid,q1_update;wire [15:0] q0_seq,q1_seq;
 wire odo_clear;
 wire signed [63:0] odo0_disp;wire [63:0] odo0_path;
 wire [31:0] odo0_ts;wire odo0_valid,odo0_fault;wire [15:0] odo0_epoch,odo0_seq;
 wire signed [63:0] odo1_disp;wire [63:0] odo1_path;
 wire [31:0] odo1_ts;wire odo1_valid,odo1_fault;wire [15:0] odo1_epoch,odo1_seq;
 car_qei_core encoders(.clk(clk),.rst(rst),.odo_clear(odo_clear),.now_ticks(ticks[31:0]),.qei0_a(qei0_a),.qei0_b(qei0_b),
  .qei1_a(qei1_a),.qei1_b(qei1_b),.qei0_dir(q0_dir_cfg),.qei0_filter(q0_filter_cfg),
  .qei0_scale(q0_scale_cfg),.qei0_zero(q0_zero_cfg),.qei1_dir(q1_dir_cfg),.qei1_filter(q1_filter_cfg),
  .qei1_scale(q1_scale_cfg),.qei1_zero(q1_zero_cfg),.q0_pos(q0_pos),.q0_period(q0_period),.q0_vel(q0_vel),
  .q0_ts(q0_ts),.q0_valid(q0_valid),.q0_seq(q0_seq),.q0_info(q0_info),.q0_update(q0_update),
  .q1_pos(q1_pos),.q1_period(q1_period),.q1_vel(q1_vel),.q1_ts(q1_ts),.q1_valid(q1_valid),
  .q1_seq(q1_seq),.q1_info(q1_info),.q1_update(q1_update),
  .odo0_disp(odo0_disp),.odo0_path(odo0_path),.odo0_ts(odo0_ts),
  .odo0_valid(odo0_valid),.odo0_fault(odo0_fault),.odo0_epoch(odo0_epoch),.odo0_seq(odo0_seq),
  .odo1_disp(odo1_disp),.odo1_path(odo1_path),.odo1_ts(odo1_ts),
  .odo1_valid(odo1_valid),.odo1_fault(odo1_fault),.odo1_epoch(odo1_epoch),.odo1_seq(odo1_seq));

 // Match host qei_quality: a fresh divider result does not repair a missed
 // edge, diagnostic overrun, odometry fault or saturated velocity. Keep raw
 // snapshot META unchanged so diagnostics still expose the original batch.
 wire q0_trusted=q0_valid && !(|q0_info[19:4]) && !odo0_fault &&
                  q0_vel!=32'h7fffffff && q0_vel!=32'h80000000;
 wire q1_trusted=q1_valid && !(|q1_info[19:4]) && !odo1_fault &&
                  q1_vel!=32'h7fffffff && q1_vel!=32'h80000000;
 wire risk_stop,risk_valid,risk_update;wire [1:0] risk_level;wire [15:0] risk_reasons,risk_seq;
 wire [31:0] risk_required,risk_ts;
 car_risk_core risk(.clk(clk),.rst(rst),.now_ticks(ticks[31:0]),.enable(risk_enable),
  .command_forward(command_forward),.command_valid(command_valid),.command_ts(command_ts),
  .us_data(us_data),.us_valid(us_valid),.us_ts(us_ts),.us_seq(us_seq),.ir_status(ir_status),.ir_valid(ir_valid),
  .ir_ts(ir_ts),.ir_seq(ir_seq),.q0_vel(q0_vel),.q0_valid(q0_trusted),.q0_ts(q0_ts),.q0_seq(q0_seq),
  .q1_vel(q1_vel),.q1_valid(q1_trusted),.q1_ts(q1_ts),.q1_seq(q1_seq),.stop_request(risk_stop),
  .risk_level(risk_level),.reason_bits(risk_reasons),.required_mm(risk_required),.risk_ts(risk_ts),
  .risk_valid(risk_valid),.risk_seq(risk_seq),.risk_update(risk_update));
 assign risk_stop_o=risk_stop;assign risk_level_o=risk_level;assign risk_reasons_o=risk_reasons;
 assign osd_distance_mm_o=us_data[11:0];assign osd_distance_valid_o=us_valid;
 wire signed [32:0] osd_speed_sum=$signed({q0_vel[31],q0_vel})+$signed({q1_vel[31],q1_vel});
 assign osd_speed_q16_o=$signed(osd_speed_sum)>>>1;
 assign osd_speed_valid_o=q0_trusted&&q1_trusted;
 wire signed [64:0] displacement_sum=$signed({odo0_disp[63],odo0_disp})+$signed({odo1_disp[63],odo1_disp});
 wire [64:0] path_sum={1'b0,odo0_path}+{1'b0,odo1_path};
 assign osd_displacement_q16_o=displacement_sum>>>1;
 assign osd_path_q16_o=path_sum[64:1];
 assign osd_odometry_valid_o=odo0_valid&&odo1_valid&&!odo0_fault&&!odo1_fault;
 reg [31:0] car_state,car_age_stage,car_age_committed,car_ts;
 reg car_expired;
 wire [32:0] car_total_age={1'b0,(ticks[31:0]-car_ts)}+{1'b0,car_age_committed};
 assign osd_car_valid_o=car_state[1]&&!car_expired&&car_total_age<33'd70_000_000;
 assign osd_car_locked_o=car_state[0];assign osd_car_fault_o=car_state[31:16];


 wire [11:0] wr_addr,rd_addr;wire [31:0] wr_data;wire [3:0] wr_strb;wire wr_en,rd_en;reg [31:0] rd_data;
 axil_reg_if #(.DATA_WIDTH(32),.ADDR_WIDTH(12),.STRB_WIDTH(4),.TIMEOUT(4)) bus(
  .clk(clk),.rst(rst),.s_axil_awaddr(s_axil_awaddr),.s_axil_awprot(s_axil_awprot),.s_axil_awvalid(s_axil_awvalid),
  .s_axil_awready(s_axil_awready),.s_axil_wdata(s_axil_wdata),.s_axil_wstrb(s_axil_wstrb),.s_axil_wvalid(s_axil_wvalid),
  .s_axil_wready(s_axil_wready),.s_axil_bresp(s_axil_bresp),.s_axil_bvalid(s_axil_bvalid),.s_axil_bready(s_axil_bready),
  .s_axil_araddr(s_axil_araddr),.s_axil_arprot(s_axil_arprot),.s_axil_arvalid(s_axil_arvalid),.s_axil_arready(s_axil_arready),
  .s_axil_rdata(s_axil_rdata),.s_axil_rresp(s_axil_rresp),.s_axil_rvalid(s_axil_rvalid),.s_axil_rready(s_axil_rready),
  .reg_wr_addr(wr_addr),.reg_wr_data(wr_data),.reg_wr_strb(wr_strb),.reg_wr_en(wr_en),.reg_wr_wait(1'b0),.reg_wr_ack(1'b1),
  .reg_rd_addr(rd_addr),.reg_rd_en(rd_en),.reg_rd_data(rd_data),.reg_rd_wait(1'b0),.reg_rd_ack(1'b1));
 function [31:0] merge_bytes;input [31:0] oldv;input [31:0] newv;input [3:0] strb;begin
  merge_bytes=oldv;if(strb[0])merge_bytes[7:0]=newv[7:0];if(strb[1])merge_bytes[15:8]=newv[15:8];
  if(strb[2])merge_bytes[23:16]=newv[23:16];if(strb[3])merge_bytes[31:24]=newv[31:24];end endfunction
 assign odo_clear=wr_en&&(wr_addr==`CAR_REG_ODOM_CTRL)&&wr_strb[0]&&wr_data[0];
 wire snap_trigger=wr_en&&(wr_addr==`CAR_REG_CTRL)&&wr_strb[0]&&wr_data[0];
 wire time_latch=wr_en&&(wr_addr==`CAR_REG_CTRL)&&wr_strb[0]&&wr_data[1];
 reg snap_done,time_done;reg [15:0] snap_epoch;reg [31:0] time_lo,time_hi,scratch;
 reg [31:0] s_us_data,s_us_ts,s_us_meta,s_us_err,s_ir_status,s_ir_ts,s_ir_meta;
 reg [31:0] s_q0_pos,s_q0_period,s_q0_vel,s_q0_ts,s_q0_meta,s_q0_info;
 reg [31:0] s_q1_pos,s_q1_period,s_q1_vel,s_q1_ts,s_q1_meta,s_q1_info;
 reg [31:0] s_risk_state,s_risk_required,s_risk_ts,s_risk_meta,s_cmd_state,s_cmd_ts;
 reg [63:0] s_odo0_disp,s_odo0_path;reg [31:0] s_odo0_ts,s_odo0_meta,s_odo0_epoch;
 reg [63:0] s_odo1_disp,s_odo1_path;reg [31:0] s_odo1_ts,s_odo1_meta,s_odo1_epoch;
 always @(posedge clk) begin
  if(rst) begin
   car_state<=0;car_age_stage<=0;car_age_committed<=0;car_ts<=0;car_expired<=1;
   us_enable<=1;us_period<=6_000_000;us_max_echo<=3_000_000;us_trig_ticks<=1000;ir_filter<=5000;
   q0_dir_cfg<=0;q0_filter_cfg<=0;q0_scale_cfg<=0;q0_zero_cfg<=10_000_000;
   q1_dir_cfg<=0;q1_filter_cfg<=0;q1_scale_cfg<=0;q1_zero_cfg<=10_000_000;
   command_forward<=0;command_valid<=0;command_ts<=0;risk_enable<=1;scratch<=32'ha55a5a5a;
   snap_done<=1;time_done<=1;snap_epoch<=0;time_lo<=0;time_hi<=0;
   s_odo0_disp<=0;s_odo0_path<=0;s_odo0_ts<=0;s_odo0_meta<=0;s_odo0_epoch<=0;
   s_odo1_disp<=0;s_odo1_path<=0;s_odo1_ts<=0;s_odo1_meta<=0;s_odo1_epoch<=0;
   s_us_data<=0;s_us_ts<=0;s_us_meta<=0;s_us_err<=0;s_ir_status<=0;s_ir_ts<=0;s_ir_meta<=0;
   s_q0_pos<=0;s_q0_period<=0;s_q0_vel<=0;s_q0_ts<=0;s_q0_meta<=0;s_q0_info<=0;
   s_q1_pos<=0;s_q1_period<=0;s_q1_vel<=0;s_q1_ts<=0;s_q1_meta<=0;s_q1_info<=0;
   s_risk_state<=0;s_risk_required<=0;s_risk_ts<=0;s_risk_meta<=0;s_cmd_state<=0;s_cmd_ts<=0;
  end else begin
   if(car_total_age>=33'd70_000_000)car_expired<=1;
   snap_done<=!snap_trigger;time_done<=!time_latch;
   if(time_latch)begin time_lo<=ticks[31:0];time_hi<=ticks[63:32];end
   if(snap_trigger) begin
    snap_epoch<=snap_epoch+1'b1;
    s_odo0_disp<=odo0_disp;s_odo0_path<=odo0_path;s_odo0_ts<=odo0_ts;
    s_odo0_meta<={odo0_valid,odo0_fault,14'b0,odo0_seq};s_odo0_epoch<={16'b0,odo0_epoch};
    s_odo1_disp<=odo1_disp;s_odo1_path<=odo1_path;s_odo1_ts<=odo1_ts;
    s_odo1_meta<={odo1_valid,odo1_fault,14'b0,odo1_seq};s_odo1_epoch<={16'b0,odo1_epoch};

    s_us_data<=us_data;s_us_ts<=us_ts;s_us_meta<={us_valid,15'b0,us_seq};s_us_err<={16'b0,us_err};
    s_ir_status<={29'b0,ir_status};s_ir_ts<=ir_ts;s_ir_meta<={ir_valid,15'b0,ir_seq};
    s_q0_pos<=q0_pos;s_q0_period<=q0_period;s_q0_vel<=q0_vel;s_q0_ts<=q0_ts;s_q0_meta<={q0_valid,15'b0,q0_seq};s_q0_info<=q0_info;
    s_q1_pos<=q1_pos;s_q1_period<=q1_period;s_q1_vel<=q1_vel;s_q1_ts<=q1_ts;s_q1_meta<={q1_valid,15'b0,q1_seq};s_q1_info<=q1_info;
    s_risk_state<={risk_reasons,13'b0,risk_level,risk_stop};s_risk_required<=risk_required;
    s_risk_ts<=risk_ts;s_risk_meta<={risk_valid,15'b0,risk_seq};s_cmd_state<={30'b0,command_valid,command_forward};s_cmd_ts<=command_ts;
   end
   if(wr_en) case(wr_addr)
    `CAR_REG_DISPLAY_CAR_AGE: car_age_stage<=merge_bytes(car_age_stage,wr_data,wr_strb);
    `CAR_REG_DISPLAY_CAR_STATE: if(wr_strb==4'b1111)begin
     car_state<=wr_data;car_age_committed<=car_age_stage;car_ts<=ticks[31:0];
     car_expired<=!wr_data[1]||car_age_stage>=32'd70_000_000;
    end
    `CAR_REG_SCRATCH: scratch<=merge_bytes(scratch,wr_data,wr_strb);
    `CAR_REG_US_CTRL: if(wr_strb[0])us_enable<=wr_data[0];
    `CAR_REG_US_PERIOD: us_period<=merge_bytes(us_period,wr_data,wr_strb);
    `CAR_REG_US_MAX_ECHO: us_max_echo<=merge_bytes(us_max_echo,wr_data,wr_strb);
    `CAR_REG_US_TRIG_TICKS: us_trig_ticks<=merge_bytes(us_trig_ticks,wr_data,wr_strb);
    `CAR_REG_IR_FILTER: ir_filter<=merge_bytes(ir_filter,wr_data,wr_strb);
    `CAR_REG_QEI0_DIR: if(wr_strb[0])q0_dir_cfg<=wr_data[0];
    `CAR_REG_QEI0_FILTER: q0_filter_cfg<=merge_bytes(q0_filter_cfg,wr_data,wr_strb);
    `CAR_REG_QEI0_SCALE: q0_scale_cfg<=merge_bytes(q0_scale_cfg,wr_data,wr_strb);
    `CAR_REG_QEI0_ZERO: q0_zero_cfg<=merge_bytes(q0_zero_cfg,wr_data,wr_strb);
    `CAR_REG_QEI1_DIR: if(wr_strb[0])q1_dir_cfg<=wr_data[0];
    `CAR_REG_QEI1_FILTER: q1_filter_cfg<=merge_bytes(q1_filter_cfg,wr_data,wr_strb);
    `CAR_REG_QEI1_SCALE: q1_scale_cfg<=merge_bytes(q1_scale_cfg,wr_data,wr_strb);
    `CAR_REG_QEI1_ZERO: q1_zero_cfg<=merge_bytes(q1_zero_cfg,wr_data,wr_strb);
    `CAR_REG_RISK_CMD: if(wr_strb[0])begin command_forward<=wr_data[0];command_valid<=wr_data[1];command_ts<=ticks[31:0];end
    `CAR_REG_RISK_ENABLE: if(wr_strb[0])risk_enable<=wr_data[0];
   endcase
  end
 end
 always @(*) begin
  case(rd_addr)
   `CAR_REG_OSD_ERRORS:rd_data={16'b0,osd_errors_i};
   `CAR_REG_DISPLAY_FRAMES:rd_data=osd_frames_i;
   `CAR_REG_DISPLAY_FRAME_ID:rd_data=display_frame_id_i;
   `CAR_REG_DISPLAY_FRAME_STATE:rd_data=display_frame_state_i;
   `CAR_REG_DISPLAY_FRAME_TS_LO:rd_data=display_frame_ticks_i[31:0];
   `CAR_REG_DISPLAY_FRAME_TS_HI:rd_data=display_frame_ticks_i[63:32];
   `CAR_REG_DISPLAY_HEADER_ERRORS:rd_data={16'd0,display_header_errors_i};
   `CAR_REG_DISPLAY_REPEATS:rd_data=display_repeats_i;
   `CAR_REG_DISPLAY_TAG_COUNT:rd_data=display_tag_count_i;
   `CAR_REG_DISPLAY_FRAME_AGE:rd_data=display_frame_age_i;
   `CAR_REG_DISPLAY_FRAME_SOF_LO:rd_data=display_frame_sof_i[31:0];
   `CAR_REG_DISPLAY_FRAME_SOF_HI:rd_data=display_frame_sof_i[63:32];
   `CAR_REG_DISPLAY_CAR_STATE:rd_data={car_state[31:2],osd_car_valid_o,car_state[0]};
   `CAR_REG_DISPLAY_CAR_AGE:rd_data=car_age_stage;
   `CAR_REG_DISPLAY_CAR_TS:rd_data=car_ts;
   `CAR_REG_ID_VERSION:rd_data=`CAR_INTEGRATED_ID;`CAR_REG_CTRL:rd_data=0;
   `CAR_REG_STATUS:rd_data={30'b0,time_done,snap_done};`CAR_REG_SNAP_EPOCH:rd_data={16'b0,snap_epoch};
   `CAR_REG_TS_LIVE_LO:rd_data=ticks[31:0];`CAR_REG_TS_LIVE_HI:rd_data=ticks[63:32];
   `CAR_REG_TS_SNAP_LO:rd_data=time_lo;`CAR_REG_TS_SNAP_HI:rd_data=time_hi;`CAR_REG_SCRATCH:rd_data=scratch;
   `CAR_REG_US_DATA:rd_data=s_us_data;`CAR_REG_US_TS:rd_data=s_us_ts;`CAR_REG_US_META:rd_data=s_us_meta;`CAR_REG_US_ERR:rd_data=s_us_err;
   `CAR_REG_IR_STATUS:rd_data=s_ir_status;`CAR_REG_IR_TS:rd_data=s_ir_ts;`CAR_REG_IR_META:rd_data=s_ir_meta;
   `CAR_REG_QEI0_POS:rd_data=s_q0_pos;`CAR_REG_QEI0_PERIOD:rd_data=s_q0_period;`CAR_REG_QEI0_VEL:rd_data=s_q0_vel;
   `CAR_REG_QEI0_TS:rd_data=s_q0_ts;`CAR_REG_QEI0_META:rd_data=s_q0_meta;`CAR_REG_QEI0_INFO:rd_data=s_q0_info;
   `CAR_REG_QEI1_POS:rd_data=s_q1_pos;`CAR_REG_QEI1_PERIOD:rd_data=s_q1_period;`CAR_REG_QEI1_VEL:rd_data=s_q1_vel;
   `CAR_REG_QEI1_TS:rd_data=s_q1_ts;`CAR_REG_QEI1_META:rd_data=s_q1_meta;`CAR_REG_QEI1_INFO:rd_data=s_q1_info;
   `CAR_REG_RISK_STATE:rd_data=s_risk_state;`CAR_REG_RISK_REQUIRED_MM:rd_data=s_risk_required;
   `CAR_REG_RISK_TS:rd_data=s_risk_ts;`CAR_REG_RISK_META:rd_data=s_risk_meta;`CAR_REG_CMD_STATE:rd_data=s_cmd_state;`CAR_REG_CMD_TS:rd_data=s_cmd_ts;
   `CAR_REG_ODOM0_DISP_LO:rd_data=s_odo0_disp[31:0];
   `CAR_REG_ODOM0_DISP_HI:rd_data=s_odo0_disp[63:32];
   `CAR_REG_ODOM0_PATH_LO:rd_data=s_odo0_path[31:0];
   `CAR_REG_ODOM0_PATH_HI:rd_data=s_odo0_path[63:32];
   `CAR_REG_ODOM0_TS:rd_data=s_odo0_ts;
   `CAR_REG_ODOM0_META:rd_data=s_odo0_meta;
   `CAR_REG_ODOM0_EPOCH:rd_data=s_odo0_epoch;
   `CAR_REG_ODOM1_DISP_LO:rd_data=s_odo1_disp[31:0];
   `CAR_REG_ODOM1_DISP_HI:rd_data=s_odo1_disp[63:32];
   `CAR_REG_ODOM1_PATH_LO:rd_data=s_odo1_path[31:0];
   `CAR_REG_ODOM1_PATH_HI:rd_data=s_odo1_path[63:32];
   `CAR_REG_ODOM1_TS:rd_data=s_odo1_ts;
   `CAR_REG_ODOM1_META:rd_data=s_odo1_meta;
   `CAR_REG_ODOM1_EPOCH:rd_data=s_odo1_epoch;
   `CAR_REG_US_CTRL:rd_data={31'b0,us_enable};`CAR_REG_US_PERIOD:rd_data=us_period;`CAR_REG_US_MAX_ECHO:rd_data=us_max_echo;
   `CAR_REG_US_TRIG_TICKS:rd_data=us_trig_ticks;`CAR_REG_IR_FILTER:rd_data=ir_filter;
   `CAR_REG_QEI0_DIR:rd_data={31'b0,q0_dir_cfg};`CAR_REG_QEI0_FILTER:rd_data=q0_filter_cfg;`CAR_REG_QEI0_SCALE:rd_data=q0_scale_cfg;`CAR_REG_QEI0_ZERO:rd_data=q0_zero_cfg;
   `CAR_REG_QEI1_DIR:rd_data={31'b0,q1_dir_cfg};`CAR_REG_QEI1_FILTER:rd_data=q1_filter_cfg;`CAR_REG_QEI1_SCALE:rd_data=q1_scale_cfg;`CAR_REG_QEI1_ZERO:rd_data=q1_zero_cfg;
   `CAR_REG_RISK_ENABLE:rd_data={31'b0,risk_enable};default:rd_data=0;
  endcase
 end
endmodule
`resetall
