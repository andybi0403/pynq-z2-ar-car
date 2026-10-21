// car_sensors_top.v -- 任务3 顶层：超声波+红外 接入任务2的公共基础设施
// 复用：car_time_counter、car_snapshot、alexforencich/verilog-axi 的 axil_reg_if（MIT）。
// 契约 v0.5：完整32位样本时间与独立metadata；0x030-0x04C为传感器状态/配置，
// 0x110-0x118为超声波参数。本顶层仅供模块验证，生产集成使用统一顶层。
// US sample time is captured at the synchronized falling-edge detection;
// physical pin-to-clock synchronization delay is not a claimed 1-tick accuracy.
// IR 样本时间 = 位图/稳定标志变化拍。
`resetall
`timescale 1ns / 1ps
`default_nettype none

module car_sensors_top (
    input  wire             clk,
    input  wire             rst,
    // 外部传感器信号（原始电平，模块内同步）
    input  wire             us_echo,
    output wire             us_trig,
    input  wire             ir_l_raw,
    input  wire             ir_r_raw,

    // AXI4-Lite 从机接口
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

// ── 配置寄存器（RW） ──
reg        us_enable;
reg [31:0] us_cfg_period;
reg [31:0] us_cfg_max_echo;
reg [31:0] us_cfg_trig_clk;
reg [31:0] ir_filt_q;
reg [31:0] scratch_q;
reg [31:0] ts_snap_lo, ts_snap_hi;
reg        ts_latch_done;

// ── 超声波实例 ──
wire        us_samp_update;
wire [31:0] us_samp_data;
wire        us_samp_valid;
wire [31:0] us_samp_ts;
wire [15:0] us_err_cnt;
wire [15:0] us_seq;

// Timestamp is supplied atomically by the ultrasonic producer.

car_ultrasonic #(.TS_W(32)) us_inst (
    .clk(clk), .rst(rst),
    .enable(us_enable),
    .echo(us_echo),
    .trig(us_trig),
    .cfg_period(us_cfg_period),
    .cfg_max_echo(us_cfg_max_echo),
    .cfg_trig_clk(us_cfg_trig_clk),
    .now_ticks(ts_count[31:0]), .sample_ts(us_samp_ts),
    .samp_data(us_samp_data),
    .samp_valid(us_samp_valid),
    .samp_update(us_samp_update),
    .err_cnt(us_err_cnt),
    .samp_seq(us_seq)
);

// ── 红外实例 ──
wire        ir_l_obs, ir_r_obs, ir_stable;

car_ir ir_inst (
    .clk(clk), .rst(rst),
    .ir_l_raw(ir_l_raw), .ir_r_raw(ir_r_raw),
    .filt_ticks(ir_filt_q),
    .obs_l(ir_l_obs), .obs_r(ir_r_obs),
    .stable(ir_stable)
);

// IR 变化检测：位图或稳定标志变化 = 一批新 IR 样本
reg [2:0]  ir_prev;
reg [31:0] ir_ts_q;
always @(posedge clk) begin
    if (rst) begin
        ir_prev <= 3'b0; ir_ts_q <= 32'b0;
    end else begin
        if ({ir_l_obs, ir_r_obs, ir_stable} != ir_prev) begin
            ir_prev <= {ir_l_obs, ir_r_obs, ir_stable};
            ir_ts_q <= ts_count[31:0];
        end
    end
end

// ── 原子快照 live 侧驱动 ──
// live_data 编码：超声波批=[11:0]mm [15:12]故障码 [19:16]IR位图；IR 批=[19:16]IR位图 [18]stable
// This snapshot is strictly ultrasonic; IR has its own status/change timestamp.
// An IR edge cannot renew distance age or replace its invalid flag.
wire        live_upd = us_samp_update;
wire [31:0] live_d   = us_samp_data;
wire        live_v   = us_samp_valid;
wire [31:0] live_ts  = us_samp_ts;

reg         snap_trigger;
wire [31:0] snap_data_q, snap_ts_q;
wire        snap_valid_q, snap_done_q;
wire [15:0] snap_seq_q, snap_err_q;

car_snapshot #(.DATA_W(32), .TS_W(32), .SEQ_W(16)) snap_inst (
    .clk(clk), .rst(rst),
    .live_data(live_d),
    .live_valid(live_v),
    .live_sample_ts(live_ts),
    .live_update(live_upd),
    .trigger(snap_trigger),
    .snap_data(snap_data_q),
    .snap_valid(snap_valid_q),
    .snap_sample_ts(snap_ts_q),
    .snap_seq(snap_seq_q),
    .snap_done(snap_done_q),
    .snap_err_cnt(snap_err_q)
);

// ── AXI-Lite 前端（任务2 同款，直接复用上游模块） ──
wire [11:0] reg_wr_addr, reg_rd_addr;
wire [31:0] reg_wr_data;
reg  [31:0] rd_mux_r;
wire [3:0]  reg_wr_strb;
wire        reg_wr_en, reg_rd_en;

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
wire wa_ctrl  = reg_wr_en && (reg_wr_addr == 12'h004);
wire wa_scr   = reg_wr_en && (reg_wr_addr == 12'h02C);
wire wa_usctl = reg_wr_en && (reg_wr_addr == 12'h044);
wire wa_ifilt = reg_wr_en && (reg_wr_addr == 12'h04C);
wire wa_uper  = reg_wr_en && (reg_wr_addr == 12'h110);
wire wa_upmax = reg_wr_en && (reg_wr_addr == 12'h114);
wire wa_utrig = reg_wr_en && (reg_wr_addr == 12'h118);

assign snap_trigger = wa_ctrl && reg_wr_strb[0] && reg_wr_data[0];
wire ts_latch       = wa_ctrl && reg_wr_strb[0] && reg_wr_data[1];

always @(posedge clk) begin
    if (rst) begin
        us_enable <= 1'b1;
        // 60 ms idle + at most two 30 ms waits => worst fault publication <120 ms,
        // leaving margin before the 200 ms control-data expiry.
        us_cfg_period <= 32'd6_000_000;
        us_cfg_max_echo <= 32'd3_000_000;
        us_cfg_trig_clk <= 32'd1000;
        ir_filt_q <= 32'd5000;
        scratch_q <= 32'hA55A5A5A;
        ts_snap_lo <= 32'b0; ts_snap_hi <= 32'b0; ts_latch_done <= 1'b1;
    end else begin
        ts_latch_done <= 1'b1;
        if (wa_usctl && reg_wr_strb[0]) us_enable <= reg_wr_data[0];
        if (wa_ifilt) begin
            if (reg_wr_strb[0]) ir_filt_q[7:0]     <= reg_wr_data[7:0];
            if (reg_wr_strb[1]) ir_filt_q[15:8]    <= reg_wr_data[15:8];
            if (reg_wr_strb[2]) ir_filt_q[23:16]   <= reg_wr_data[23:16];
            if (reg_wr_strb[3]) ir_filt_q[31:24]   <= reg_wr_data[31:24];
        end
        if (wa_uper) begin
            if (reg_wr_strb[0]) us_cfg_period[7:0]   <= reg_wr_data[7:0];
            if (reg_wr_strb[1]) us_cfg_period[15:8]  <= reg_wr_data[15:8];
            if (reg_wr_strb[2]) us_cfg_period[23:16] <= reg_wr_data[23:16];
            if (reg_wr_strb[3]) us_cfg_period[31:24] <= reg_wr_data[31:24];
        end
        if (wa_upmax) begin
            if (reg_wr_strb[0]) us_cfg_max_echo[7:0]   <= reg_wr_data[7:0];
            if (reg_wr_strb[1]) us_cfg_max_echo[15:8]  <= reg_wr_data[15:8];
            if (reg_wr_strb[2]) us_cfg_max_echo[23:16] <= reg_wr_data[23:16];
            if (reg_wr_strb[3]) us_cfg_max_echo[31:24] <= reg_wr_data[31:24];
        end
        if (wa_utrig) begin
            if (reg_wr_strb[0]) us_cfg_trig_clk[7:0]   <= reg_wr_data[7:0];
            if (reg_wr_strb[1]) us_cfg_trig_clk[15:8]  <= reg_wr_data[15:8];
            if (reg_wr_strb[2]) us_cfg_trig_clk[23:16] <= reg_wr_data[23:16];
            if (reg_wr_strb[3]) us_cfg_trig_clk[31:24] <= reg_wr_data[31:24];
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

// ── 读译码（组合；非法地址读 0） ──
always @(*) begin
    case (reg_rd_addr)
        12'h000: rd_mux_r = 32'hC425_0205;                           // magic/type=02/version=05
        12'h004: rd_mux_r = 32'b0;                                    // CTRL（写触发读 0）
        12'h008: rd_mux_r = {30'b0, ts_latch_done, snap_done_q};      // STATUS
        12'h00C: rd_mux_r = {16'b0, snap_err_q};                      // SNAP_ERR_CNT
        12'h010: rd_mux_r = ts_count[31:0];                           // TS_LIVE_LO
        12'h014: rd_mux_r = ts_count[63:32];                          // TS_LIVE_HI
        12'h018: rd_mux_r = ts_snap_lo;                               // TS_SNAP_LO
        12'h01C: rd_mux_r = ts_snap_hi;                               // TS_SNAP_HI
        12'h020: rd_mux_r = snap_data_q;                              // SNAP_DATA
        12'h024: rd_mux_r = snap_ts_q;                                // SNAP_TS full 32-bit
        12'h028: rd_mux_r = {snap_valid_q, 15'b0, snap_seq_q};        // SNAP_META
        12'h02C: rd_mux_r = scratch_q;                                // SCRATCH
        12'h030: rd_mux_r = us_samp_data;                             // US_DIST_MM
        12'h034: rd_mux_r = us_samp_ts;                               // US_SAMPLE_TS full 32-bit
        12'h038: rd_mux_r = {us_err_cnt, us_seq};                     // US_SEQ_ERR（高16=err，低16=seq）
        12'h03C: rd_mux_r = {29'b0, ir_stable, ir_r_obs, ir_l_obs};   // IR_STATUS
        12'h040: rd_mux_r = ir_ts_q;                                 // real clock timestamp
        12'h044: rd_mux_r = {31'b0, us_enable};                       // US_CTRL
        12'h048: rd_mux_r = {us_samp_valid, 15'b0, us_seq};           // US_META
        12'h04C: rd_mux_r = ir_filt_q;                                // IR_FILT_TICKS
        12'h110: rd_mux_r = us_cfg_period;                            // US_CFG_PERIOD
        12'h114: rd_mux_r = us_cfg_max_echo;                          // US_CFG_MAX_ECHO
        12'h118: rd_mux_r = us_cfg_trig_clk;                          // US_CFG_TRIG_CLK
        default: rd_mux_r = 32'b0;
    endcase
end

endmodule

`resetall
