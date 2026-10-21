// car_qei_top.v -- 任务4 顶层：两路 QEI + PL 速度候选，接任务2/3 公共基础设施
// Contract v0.5 (ID 0xC4250405): T-method velocity and two independent
// coherent shadow tuples. Trigger before reading 0x120..0x14C.
`resetall
`timescale 1ns / 1ps
`default_nettype none

module car_qei_top (
    input  wire             clk,
    input  wire             rst,
    // 编码器原始信号
    input  wire             qei0_a, qei0_b,
    input  wire             qei1_a, qei1_b,

    // AXI4-Lite
    input  wire [11:0]      s_axil_awaddr,
    input  wire [2:0]       s_axil_awprot,
    input  wire             s_axil_awvalid,
    output wire             s_axil_awready,
    input  wire [31:0]      s_axil_wdata,
    input  wire [3:0]       s_axil_wstrb,
    input  wire             s_axil_wvalid,
    output wire             s_axil_wready,
    output wire [1:0]       s_axil_bresp,
    output wire             s_axil_bvalid,
    input  wire             s_axil_bready,
    input  wire [11:0]      s_axil_araddr,
    input  wire [2:0]       s_axil_arprot,
    input  wire             s_axil_arvalid,
    output wire             s_axil_arready,
    output wire [31:0]      s_axil_rdata,
    output wire [1:0]       s_axil_rresp,
    output wire             s_axil_rvalid,
    input  wire             s_axil_rready
);

// ── 公共时间基准 ──
wire [63:0] ts_count;
car_time_counter #(.WIDTH(64)) ts_inst (
    .clk(clk), .rst(rst), .count(ts_count)
);

// ── 配置寄存器 ──
reg        qei0_dir, qei1_dir;
reg [31:0] qei0_filt, qei1_filt;
reg [31:0] qei0_scale, qei1_scale;
reg [5:0]  qei0_shift, qei1_shift;
reg [31:0] qei0_velperiod, qei1_velperiod;
reg [31:0] scratch_q;
reg [31:0] ts_snap_lo, ts_snap_hi;
reg        ts_latch_done;

// ── QEI 实例 ──
wire [31:0] q0_pos, q1_pos;
wire        q0_dir, q1_dir, q0_seen, q1_seen;
wire [7:0]  q0_ill, q1_ill, q0_flt, q1_flt;
wire [31:0] q0_period, q1_period;
wire        q0_pvalid, q1_pvalid;
wire q0_step,q1_step,q0_stepdir,q1_stepdir;

car_qei q0 (
    .clk(clk), .rst(rst),
    .a_raw(qei0_a), .b_raw(qei0_b),
    .cfg_dir(qei0_dir), .cfg_filt(qei0_filt),
    .pos_cnt(q0_pos), .dir_pos(q0_dir), .seen_edge(q0_seen),
    .ill_cnt(q0_ill), .filt_rej_cnt(q0_flt),
    .period_ticks(q0_period), .period_valid(q0_pvalid),
    .step_pulse(q0_step), .step_dir(q0_stepdir)
);

car_qei q1 (
    .clk(clk), .rst(rst),
    .a_raw(qei1_a), .b_raw(qei1_b),
    .cfg_dir(qei1_dir), .cfg_filt(qei1_filt),
    .pos_cnt(q1_pos), .dir_pos(q1_dir), .seen_edge(q1_seen),
    .ill_cnt(q1_ill), .filt_rej_cnt(q1_flt),
    .period_ticks(q1_period), .period_valid(q1_pvalid),
    .step_pulse(q1_step), .step_dir(q1_stepdir)
);

// ── 速度候选（共享公共计数器时间戳） ──
wire [31:0] v0_q16, v1_q16;
wire        v0_valid, v1_valid, v0_upd, v1_upd;
wire [15:0] v0_seq, v1_seq;
wire [15:0] v0_overrun, v1_overrun;
wire [7:0] v0_overrun_export=(|v0_overrun[15:8]) ? 8'hff : v0_overrun[7:0];
wire [7:0] v1_overrun_export=(|v1_overrun[15:8]) ? 8'hff : v1_overrun[7:0];
wire [31:0] v0_ts,v1_ts,v0_pos,v1_pos,v0_period,v1_period;
car_qei_velocity v0 (
 .clk(clk),.rst(rst),.pos_cnt(q0_pos),.period_ticks(q0_period),
 .now_ticks(ts_count[31:0]),.step_pulse(q0_step),.step_dir(q0_stepdir),.period_valid(q0_pvalid),
 .cfg_scale(qei0_scale),.cfg_shift(qei0_shift),.cfg_period(qei0_velperiod),
 .vel_q16(v0_q16),.vel_valid(v0_valid),.vel_seq(v0_seq),.overrun_cnt(v0_overrun),.live_update(v0_upd),
 .sample_ts(v0_ts),.sample_pos(v0_pos),.sample_period(v0_period));
car_qei_velocity v1 (
 .clk(clk),.rst(rst),.pos_cnt(q1_pos),.period_ticks(q1_period),
 .now_ticks(ts_count[31:0]),.step_pulse(q1_step),.step_dir(q1_stepdir),.period_valid(q1_pvalid),
 .cfg_scale(qei1_scale),.cfg_shift(qei1_shift),.cfg_period(qei1_velperiod),
 .vel_q16(v1_q16),.vel_valid(v1_valid),.vel_seq(v1_seq),.overrun_cnt(v1_overrun),.live_update(v1_upd),
 .sample_ts(v1_ts),.sample_pos(v1_pos),.sample_period(v1_period));
wire snap_trigger;
reg snap_done_q;
reg [15:0] snap_err_q;
reg [31:0] s0_pos,s0_info,s0_period,s0_vel,s0_ts,s0_meta;
reg [31:0] s1_pos,s1_info,s1_period,s1_vel,s1_ts,s1_meta;
// Capture BOTH channels and full metadata at one edge; host sees only shadows.
always @(posedge clk) begin
 if(rst) begin
  snap_done_q<=1;snap_err_q<=0;
  s0_pos<=0;s0_info<=0;s0_period<=0;s0_vel<=0;s0_ts<=0;s0_meta<=0;
  s1_pos<=0;s1_info<=0;s1_period<=0;s1_vel<=0;s1_ts<=0;s1_meta<=0;
 end else begin
  snap_done_q<=!snap_trigger;
  if(snap_trigger) begin
   s0_pos<=v0_pos;s0_period<=v0_period;s0_vel<=v0_q16;s0_ts<=v0_ts;
   s0_meta<={v0_valid,15'b0,v0_seq};
   s0_info<={4'b0,q0_flt,v0_overrun_export,q0_ill,1'b0,q0_pvalid,q0_seen,q0_dir};
   s1_pos<=v1_pos;s1_period<=v1_period;s1_vel<=v1_q16;s1_ts<=v1_ts;
   s1_meta<={v1_valid,15'b0,v1_seq};
   s1_info<={4'b0,q1_flt,v1_overrun_export,q1_ill,1'b0,q1_pvalid,q1_seen,q1_dir};
   if((!v0_valid || !v1_valid) && snap_err_q!=16'hffff) snap_err_q<=snap_err_q+1'b1;
  end
 end
end

// ── AXI-Lite 前端 ──
wire [11:0] reg_wr_addr, reg_rd_addr;
wire [31:0] reg_wr_data;
wire [3:0]  reg_wr_strb;
wire        reg_wr_en, reg_rd_en;
reg  [31:0] rd_mux_r;

axil_reg_if #(
    .DATA_WIDTH(32), .ADDR_WIDTH(12), .STRB_WIDTH(4), .TIMEOUT(4)
) axil_if_inst (
    .clk(clk), .rst(rst),
    .s_axil_awaddr(s_axil_awaddr), .s_axil_awprot(s_axil_awprot),
    .s_axil_awvalid(s_axil_awvalid), .s_axil_awready(s_axil_awready),
    .s_axil_wdata(s_axil_wdata), .s_axil_wstrb(s_axil_wstrb),
    .s_axil_wvalid(s_axil_wvalid), .s_axil_wready(s_axil_wready),
    .s_axil_bresp(s_axil_bresp), .s_axil_bvalid(s_axil_bvalid),
    .s_axil_bready(s_axil_bready),
    .s_axil_araddr(s_axil_araddr), .s_axil_arprot(s_axil_arprot),
    .s_axil_arvalid(s_axil_arvalid), .s_axil_arready(s_axil_arready),
    .s_axil_rdata(s_axil_rdata), .s_axil_rresp(s_axil_rresp),
    .s_axil_rvalid(s_axil_rvalid), .s_axil_rready(s_axil_rready),
    .reg_wr_addr(reg_wr_addr), .reg_wr_data(reg_wr_data),
    .reg_wr_strb(reg_wr_strb), .reg_wr_en(reg_wr_en),
    .reg_wr_wait(1'b0), .reg_wr_ack(1'b1),
    .reg_rd_addr(reg_rd_addr), .reg_rd_en(reg_rd_en),
    .reg_rd_data(rd_mux_r),
    .reg_rd_wait(1'b0), .reg_rd_ack(1'b1)
);

// ── 写译码 ──
wire wa_ctrl   = reg_wr_en && (reg_wr_addr == 12'h004);
wire wa_scr    = reg_wr_en && (reg_wr_addr == 12'h02C);
wire wa_q0dir  = reg_wr_en && (reg_wr_addr == 12'h160);
wire wa_q0filt = reg_wr_en && (reg_wr_addr == 12'h164);
wire wa_q0scl  = reg_wr_en && (reg_wr_addr == 12'h168);
wire wa_q0shf  = reg_wr_en && (reg_wr_addr == 12'h16C);
wire wa_q0per  = reg_wr_en && (reg_wr_addr == 12'h170);
wire wa_q1dir  = reg_wr_en && (reg_wr_addr == 12'h174);
wire wa_q1filt = reg_wr_en && (reg_wr_addr == 12'h178);
wire wa_q1scl  = reg_wr_en && (reg_wr_addr == 12'h17C);
wire wa_q1shf  = reg_wr_en && (reg_wr_addr == 12'h180);
wire wa_q1per  = reg_wr_en && (reg_wr_addr == 12'h184);

assign snap_trigger = wa_ctrl && reg_wr_strb[0] && reg_wr_data[0];
wire ts_latch       = wa_ctrl && reg_wr_strb[0] && reg_wr_data[1];

always @(posedge clk) begin
    if (rst) begin
        qei0_dir <= 1'b0; qei1_dir <= 1'b0;
        qei0_filt <= 32'b0; qei1_filt <= 32'b0;
        qei0_scale <= 32'b0; qei1_scale <= 32'b0;      // 0=未配置（契约）
        qei0_shift <= 6'b0; qei1_shift <= 6'b0;
        qei0_velperiod <= 32'd10_000_000; qei1_velperiod <= 32'd10_000_000; // 100ms zero-speed candidate
        scratch_q <= 32'hA55A5A5A;
        ts_snap_lo <= 32'b0; ts_snap_hi <= 32'b0; ts_latch_done <= 1'b1;
    end else begin
        ts_latch_done <= 1'b1;
        if (wa_q0dir  && reg_wr_strb[0]) qei0_dir <= reg_wr_data[0];
        if (wa_q1dir  && reg_wr_strb[0]) qei1_dir <= reg_wr_data[0];
        if (wa_q0filt) begin
            if (reg_wr_strb[0]) qei0_filt[7:0]   <= reg_wr_data[7:0];
            if (reg_wr_strb[1]) qei0_filt[15:8]  <= reg_wr_data[15:8];
            if (reg_wr_strb[2]) qei0_filt[23:16] <= reg_wr_data[23:16];
            if (reg_wr_strb[3]) qei0_filt[31:24] <= reg_wr_data[31:24];
        end
        if (wa_q1filt) begin
            if (reg_wr_strb[0]) qei1_filt[7:0]   <= reg_wr_data[7:0];
            if (reg_wr_strb[1]) qei1_filt[15:8]  <= reg_wr_data[15:8];
            if (reg_wr_strb[2]) qei1_filt[23:16] <= reg_wr_data[23:16];
            if (reg_wr_strb[3]) qei1_filt[31:24] <= reg_wr_data[31:24];
        end
        if (wa_q0scl) begin
            if (reg_wr_strb[0]) qei0_scale[7:0]   <= reg_wr_data[7:0];
            if (reg_wr_strb[1]) qei0_scale[15:8]  <= reg_wr_data[15:8];
            if (reg_wr_strb[2]) qei0_scale[23:16] <= reg_wr_data[23:16];
            if (reg_wr_strb[3]) qei0_scale[31:24] <= reg_wr_data[31:24];
        end
        if (wa_q1scl) begin
            if (reg_wr_strb[0]) qei1_scale[7:0]   <= reg_wr_data[7:0];
            if (reg_wr_strb[1]) qei1_scale[15:8]  <= reg_wr_data[15:8];
            if (reg_wr_strb[2]) qei1_scale[23:16] <= reg_wr_data[23:16];
            if (reg_wr_strb[3]) qei1_scale[31:24] <= reg_wr_data[31:24];
        end
        if (wa_q0shf && reg_wr_strb[0]) qei0_shift <= reg_wr_data[5:0];
        if (wa_q1shf && reg_wr_strb[0]) qei1_shift <= reg_wr_data[5:0];
        if (wa_q0per) begin
            if (reg_wr_strb[0]) qei0_velperiod[7:0]   <= reg_wr_data[7:0];
            if (reg_wr_strb[1]) qei0_velperiod[15:8]  <= reg_wr_data[15:8];
            if (reg_wr_strb[2]) qei0_velperiod[23:16] <= reg_wr_data[23:16];
            if (reg_wr_strb[3]) qei0_velperiod[31:24] <= reg_wr_data[31:24];
        end
        if (wa_q1per) begin
            if (reg_wr_strb[0]) qei1_velperiod[7:0]   <= reg_wr_data[7:0];
            if (reg_wr_strb[1]) qei1_velperiod[15:8]  <= reg_wr_data[15:8];
            if (reg_wr_strb[2]) qei1_velperiod[23:16] <= reg_wr_data[23:16];
            if (reg_wr_strb[3]) qei1_velperiod[31:24] <= reg_wr_data[31:24];
        end
        if (wa_scr) begin
            if (reg_wr_strb[0]) scratch_q[7:0]   <= reg_wr_data[7:0];
            if (reg_wr_strb[1]) scratch_q[15:8]  <= reg_wr_data[15:8];
            if (reg_wr_strb[2]) scratch_q[23:16] <= reg_wr_data[23:16];
            if (reg_wr_strb[3]) scratch_q[31:24] <= reg_wr_data[31:24];
        end
        if (ts_latch) begin
            ts_snap_lo <= ts_count[31:0];
            ts_snap_hi <= ts_count[63:32];
            ts_latch_done <= 1'b0;
        end
    end
end

// ── 读译码 ──
always @(*) begin
    case (reg_rd_addr)
        12'h000: rd_mux_r = 32'hC425_0405;                              // magic/type=04/version=05
        12'h004: rd_mux_r = 32'b0;
        12'h008: rd_mux_r = {30'b0, ts_latch_done, snap_done_q};
        12'h00C: rd_mux_r = {16'b0, snap_err_q};
        12'h010: rd_mux_r = ts_count[31:0];
        12'h014: rd_mux_r = ts_count[63:32];
        12'h018: rd_mux_r = ts_snap_lo;
        12'h01C: rd_mux_r = ts_snap_hi;
        12'h020: rd_mux_r = s0_vel;
        12'h024: rd_mux_r = s0_ts;
        12'h028: rd_mux_r = s0_meta;
        12'h02C: rd_mux_r = scratch_q;
        12'h120: rd_mux_r = s0_pos;                                     // QEI0_POS
        12'h124: rd_mux_r = s0_info; // [0]dir [1]seen [2]pvalid [11:4]ill [19:12]overrun [27:20]filt
        12'h128: rd_mux_r = s0_period;                                  // QEI0_PERIOD
        12'h12C: rd_mux_r = s0_vel;                                     // QEI0_VEL
        12'h130: rd_mux_r = s0_ts;                                      // QEI0_VEL_TS
        12'h134: rd_mux_r = s0_meta;           // QEI0_VEL_VALID_SEQ
        12'h138: rd_mux_r = s1_pos;                                     // QEI1_POS
        12'h13C: rd_mux_r = s1_info; // QEI1_INFO 同上
        12'h140: rd_mux_r = s1_period;
        12'h144: rd_mux_r = s1_vel;
        12'h148: rd_mux_r = s1_ts;
        12'h14C: rd_mux_r = s1_meta;
        12'h150: rd_mux_r = q0_pos; // debug-only live counts
        12'h154: rd_mux_r = q1_pos;
        12'h160: rd_mux_r = {31'b0, qei0_dir};
        12'h164: rd_mux_r = qei0_filt;
        12'h168: rd_mux_r = qei0_scale;
        12'h16C: rd_mux_r = {26'b0, qei0_shift};
        12'h170: rd_mux_r = qei0_velperiod;
        12'h174: rd_mux_r = {31'b0, qei1_dir};
        12'h178: rd_mux_r = qei1_filt;
        12'h17C: rd_mux_r = qei1_scale;
        12'h180: rd_mux_r = {26'b0, qei1_shift};
        12'h184: rd_mux_r = qei1_velperiod;
        default: rd_mux_r = 32'b0;
    endcase
end

endmodule

`resetall
