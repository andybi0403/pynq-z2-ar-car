// car_axil_regs.v -- 公共 AXI4-Lite 寄存器前端 + 时间基准 + 原子快照顶层（契约 §8）
//
// AXI-Lite 前端直接复用 alexforencich/verilog-axi 的 axil_reg_if（MIT，commit 516bd5d）：
//   AW/W 独立寄存（可任意顺序到达）、TIMEOUT=4 防挂死、resp 固定 OK（非法地址读 0 写忽略，
//   已知限制记录于契约 §8）。本项目代码只实现 reg_wr/reg_rd 简化接口后面的寄存器译码。
//
// 已知限制：本模块 reg_wr_ack/reg_rd_ack 恒为 1（零等待译码）。
`resetall
`timescale 1ns / 1ps
`default_nettype none

module car_axil_regs #(
    parameter integer TS_W = 64   // 时间戳总位宽（生产 64；仿真可缩短验证回绕）
)(
    input  wire                     clk,
    input  wire                     rst,

    // AXI4-Lite 从机接口
    input  wire [11:0]              s_axil_awaddr,   // 4KB 窗口内偏移
    input  wire [2:0]               s_axil_awprot,
    input  wire                     s_axil_awvalid,
    output wire                     s_axil_awready,
    input  wire [31:0]              s_axil_wdata,
    input  wire [3:0]               s_axil_wstrb,
    input  wire                     s_axil_wvalid,
    output wire                     s_axil_wready,
    output wire [1:0]               s_axil_bresp,
    output wire                     s_axil_bvalid,
    input  wire                     s_axil_bready,
    input  wire [11:0]              s_axil_araddr,
    input  wire [2:0]               s_axil_arprot,
    input  wire                     s_axil_arvalid,
    output wire                     s_axil_arready,
    output wire [31:0]              s_axil_rdata,
    output wire [1:0]               s_axil_rresp,
    output wire                     s_axil_rvalid,
    input  wire                     s_axil_rready,

    // live 侧样本输入（生产者同批写入，见契约 §9）
    input  wire [31:0]              live_data,
    input  wire                     live_valid,
    input  wire [31:0]              live_sample_ts,
    input  wire                     live_update
);

// ── 时间基准 ──
wire [TS_W-1:0] ts_count;
car_time_counter #(.WIDTH(TS_W)) ts_inst (
    .clk(clk), .rst(rst), .count(ts_count)
);

// ts_latch：写 CTRL.TS_LATCH 时把 64 位计数原子锁存为一对 32 位 shadow
// （同拍整体采样，无撕裂）；done 行为与快照一致：latch 时清 0，下一拍置回。
reg  [31:0] ts_snap_lo, ts_snap_hi;
reg         ts_latch_done;
wire        ts_latch;
always @(posedge clk) begin
    if (rst) begin
        ts_snap_lo <= 32'b0;
        ts_snap_hi <= 32'b0;
        ts_latch_done <= 1'b1;
    end else if (ts_latch) begin
        ts_snap_lo <= ts_count[31:0];
        ts_snap_hi <= ts_count[TS_W-1:32];
        ts_latch_done <= 1'b0;
    end else begin
        ts_latch_done <= 1'b1;
    end
end

// ── 原子快照 ──
wire        snap_trigger;
wire [31:0] snap_data_q;
wire        snap_valid_q;
wire [31:0] snap_ts_q;
wire [15:0] snap_seq_q;
wire        snap_done_q;
wire [15:0] snap_err_q;

car_snapshot #(.DATA_W(32), .TS_W(32), .SEQ_W(16)) snap_inst (
    .clk(clk), .rst(rst),
    .live_data(live_data),
    .live_valid(live_valid),
    .live_sample_ts(live_sample_ts),
    .live_update(live_update),
    .trigger(snap_trigger),
    .snap_data(snap_data_q),
    .snap_valid(snap_valid_q),
    .snap_sample_ts(snap_ts_q),
    .snap_seq(snap_seq_q),
    .snap_done(snap_done_q),
    .snap_err_cnt(snap_err_q)
);

// ── AXI-Lite 前端（上游 MIT 模块，见 OPEN_SOURCE_USAGE.md） ──
wire [11:0]       reg_wr_addr;
wire [31:0]       reg_wr_data;
wire [3:0]        reg_wr_strb;
wire              reg_wr_en;
wire [11:0]       reg_rd_addr;
wire              reg_rd_en;
wire [31:0]       reg_rd_data;

axil_reg_if #(
    .DATA_WIDTH(32),
    .ADDR_WIDTH(12),
    .STRB_WIDTH(4),
    .TIMEOUT(4)
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
    .reg_rd_data(reg_rd_data),
    .reg_rd_wait(1'b0), .reg_rd_ack(1'b1)
);

// ── 写译码 ──
// CTRL(0x004)：bit0=snapshot_trigger、bit1=ts_latch；一拍电平脉冲（契约 §8）
wire wr_ctrl = reg_wr_en && (reg_wr_addr == 12'h004);
assign snap_trigger = wr_ctrl && reg_wr_strb[0] && reg_wr_data[0];
assign ts_latch     = wr_ctrl && reg_wr_strb[0] && reg_wr_data[1];
wire wr_scratch = reg_wr_en && (reg_wr_addr == 12'h02C);

reg [31:0] scratch_q;
always @(posedge clk) begin
    if (rst)
        scratch_q <= 32'hA55A5A5A;
    else if (wr_scratch) begin
        if (reg_wr_strb[0]) scratch_q[7:0]   <= reg_wr_data[7:0];
        if (reg_wr_strb[1]) scratch_q[15:8]  <= reg_wr_data[15:8];
        if (reg_wr_strb[2]) scratch_q[23:16] <= reg_wr_data[23:16];
        if (reg_wr_strb[3]) scratch_q[31:24] <= reg_wr_data[31:24];
    end
end

// ── 读译码（组合；reg_rd_ack=1，非法地址读 0——契约 §8 已知限制） ──
reg [31:0] reg_rd_data_r;
always @(*) begin
    case (reg_rd_addr)
        12'h000: reg_rd_data_r = 32'hC425_0105;                    // magic/type=01/version=05
        12'h004: reg_rd_data_r = 32'b0;                              // CTRL（写触发，读 0）
        12'h008: reg_rd_data_r = {30'b0, ts_latch_done, snap_done_q}; // STATUS
        12'h00C: reg_rd_data_r = {16'b0, snap_err_q};                // SNAP_ERR_CNT
        12'h010: reg_rd_data_r = ts_count[31:0];                     // TS_LIVE_LO（调试，可撕裂）
        12'h014: reg_rd_data_r = (TS_W > 32) ? ts_count[TS_W-1:32] : 32'b0; // TS_LIVE_HI
        12'h018: reg_rd_data_r = ts_snap_lo;                         // TS_SNAP_LO
        12'h01C: reg_rd_data_r = ts_snap_hi;                         // TS_SNAP_HI
        12'h020: reg_rd_data_r = snap_data_q;                        // SNAP_DATA
        12'h024: reg_rd_data_r = snap_ts_q;                          // SNAP_TS (full 32-bit)
        12'h028: reg_rd_data_r = {snap_valid_q, 15'b0, snap_seq_q};  // SNAP_META
        12'h02C: reg_rd_data_r = scratch_q;                          // SCRATCH
        default: reg_rd_data_r = 32'b0;                              // 非法地址读 0
    endcase
end
assign reg_rd_data = reg_rd_data_r;

endmodule

`resetall
