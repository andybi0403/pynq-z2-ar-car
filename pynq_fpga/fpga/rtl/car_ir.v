// car_ir.v -- 双路红外采集（契约 §8a）
// 只采集：两级同步 + 参数化稳定窗口滤波（clk 数，复位 5000=50µs@100MHz）；
// 硬件低有效（模块 OUT=0 为障碍）在同步后转换为"1=障碍"对外语义。
// 锁存判断由风险/安全层完成，本模块不做任何停车决策。
// 断线偏置（同步后恒定电平无法区分真无障碍/断线）为硬件待测项。
`resetall
`timescale 1ns / 1ps
`default_nettype none

module car_ir (
    input  wire             clk,
    input  wire             rst,
    input  wire             ir_l_raw,     // 左红外原始电平（低=障碍）
    input  wire             ir_r_raw,     // 右红外原始电平（低=障碍）
    input  wire [31:0]      filt_ticks,   // 稳定窗口 clk 数（复位 5000）
    output reg              obs_l,        // 1=左障碍（滤波后）
    output reg              obs_r,        // 1=右障碍（滤波后）
    output reg              stable        // 1=滤波窗口通过（输出可信）
);

// 两级同步
(* ASYNC_REG = "TRUE" *) reg l_ff1, l_ff2, r_ff1, r_ff2;
always @(posedge clk) begin
    if (rst) begin
        l_ff1 <= 1'b1; l_ff2 <= 1'b1;   // 复位按"无障碍"（高）
        r_ff1 <= 1'b1; r_ff2 <= 1'b1;
    end else begin
        l_ff1 <= ir_l_raw; l_ff2 <= l_ff1;
        r_ff1 <= ir_r_raw; r_ff2 <= r_ff1;
    end
end
wire l_obs_sync = !l_ff2;   // 低有效→1=障碍
wire r_obs_sync = !r_ff2;

// 稳定窗口滤波：电平需连续保持 filt_ticks 个 clk 才更新输出
reg [31:0] l_cnt, r_cnt;
reg        l_cand, r_cand;      // 候选电平（滤波中锁定的电平）
reg        l_stable, r_stable;

always @(posedge clk) begin
    if (rst) begin
        l_cnt <= 32'b0; r_cnt <= 32'b0;
        l_cand <= 1'b0; r_cand <= 1'b0;
        l_stable <= 1'b0; r_stable <= 1'b0;
        obs_l <= 1'b0; obs_r <= 1'b0;
        stable <= 1'b0;
    end else begin
        // 左路
        if (l_obs_sync == l_cand) begin
            if (!l_stable && (filt_ticks == 0 || l_cnt >= filt_ticks - 1'b1)) begin
                l_stable <= 1'b1;
                obs_l <= l_cand;
            end else if (!l_stable)
                l_cnt <= l_cnt + 1'b1;
        end else begin
            l_cand <= l_obs_sync;
            l_stable <= 1'b0;
            l_cnt <= 32'b0;
        end
        // 右路（同构）
        if (r_obs_sync == r_cand) begin
            if (!r_stable && (filt_ticks == 0 || r_cnt >= filt_ticks - 1'b1)) begin
                r_stable <= 1'b1;
                obs_r <= r_cand;
            end else if (!r_stable)
                r_cnt <= r_cnt + 1'b1;
        end else begin
            r_cand <= r_obs_sync;
            r_stable <= 1'b0;
            r_cnt <= 32'b0;
        end
        stable <= l_stable && r_stable;
    end
end

endmodule

`resetall
