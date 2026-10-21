// car_snapshot.v -- 原子快照（契约 §9）
// 结构参考：Severson-Group/AMDC-Firmware ip_repo/amdc_encoder_1.0/src/encoder.v 的
// trigger/done 锁存机制（BSD-3-Clause，commit 5cf9769d，仅借鉴握手结构，代码为本项目重写）。
//
// 原子性：先用 live_update 把生产者四元组提交到内部 committed bank，再由
// trigger 从 committed bank 整体复制到 host shadow。未提交的 live 总线变化永远
// 不可见；live_update 与 trigger 同拍时，新提交批次优先。
// live_update 是数据生产者完成一批同批写入后的单拍脉冲，seq 在该脉冲自增；
// 心跳/重复读取不产生该脉冲，因此 seq 不递增（契约 §4）。
// done 行为与 AMDC 一致：复位后 done=1（防止上层 trigger 等待挂死），
// trigger 拉低 done，锁存完成（下一拍）置回 1。
`resetall
`timescale 1ns / 1ps
`default_nettype none

module car_snapshot #(
    parameter integer DATA_W = 32,
    parameter integer TS_W   = 32,
    parameter integer SEQ_W  = 16
)(
    input  wire                 clk,
    input  wire                 rst,

    // live 侧：数据生产者同批写入（生产者负责四字段同批）
    input  wire [DATA_W-1:0]    live_data,
    input  wire                 live_valid,
    input  wire [TS_W-1:0]      live_sample_ts,
    input  wire                 live_update,   // 一拍：一批新样本提交

    // host 侧
    input  wire                 trigger,       // 一拍：锁存 live 到 shadow
    output reg  [DATA_W-1:0]    snap_data,
    output reg                  snap_valid,
    output reg  [TS_W-1:0]      snap_sample_ts,
    output reg  [SEQ_W-1:0]     snap_seq,
    output reg                  snap_done,
    output reg  [15:0]          snap_err_cnt   // trigger 时 live 无效的累计（16 位饱和）
);

reg [DATA_W-1:0] committed_data;
reg              committed_valid;
reg [TS_W-1:0]   committed_ts;
reg [SEQ_W-1:0]  committed_seq;
wire [SEQ_W-1:0] next_seq = committed_seq + {{(SEQ_W-1){1'b0}}, 1'b1};

// trigger/done 锁存（同拍整体采样 = 原子）
always @(posedge clk) begin
    if (rst) begin
        committed_data <= {DATA_W{1'b0}};
        committed_valid <= 1'b0;
        committed_ts <= {TS_W{1'b0}};
        committed_seq <= {SEQ_W{1'b0}};
        snap_data      <= {DATA_W{1'b0}};
        snap_valid     <= 1'b0;
        snap_sample_ts <= {TS_W{1'b0}};
        snap_seq       <= {SEQ_W{1'b0}};
        snap_done      <= 1'b1;   // AMDC 约定：复位后默认有效
        snap_err_cnt   <= 16'b0;
    end else begin
        if (live_update) begin
            committed_data <= live_data;
            committed_valid <= live_valid;
            committed_ts <= live_sample_ts;
            committed_seq <= next_seq;
        end
        if (trigger) begin
            // 同拍提交优先；否则只读已提交 bank，不读取可能正在变化的 live 总线。
            snap_data      <= live_update ? live_data : committed_data;
            snap_valid     <= live_update ? live_valid : committed_valid;
            snap_sample_ts <= live_update ? live_sample_ts : committed_ts;
            snap_seq       <= live_update ? next_seq : committed_seq;
            snap_done      <= 1'b0;
            if (!(live_update ? live_valid : committed_valid) && snap_err_cnt != 16'hFFFF)
                snap_err_cnt <= snap_err_cnt + 16'b1;
        end else begin
            snap_done <= 1'b1;
        end
    end
end

endmodule

`resetall
