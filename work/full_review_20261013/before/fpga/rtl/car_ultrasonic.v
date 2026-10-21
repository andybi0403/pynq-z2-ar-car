// car_ultrasonic.v -- 超声波测距（契约 §8a）
// 结构参考：yunkai1841/HC-SR04-FPGA sonic.v（CC0-1.0，commit f4df022，外部自由计数器+
// trig 窗口+echo 沿锁存脉宽的思想）；本实现为独立重写，补齐上游缺失的全部安全项：
// 两级同步器、上电 echo 已高防护（不把复位后首个已高电平当新回波）、等待上升沿超时、
// 持续高超时、量程检查、测量间隔控制、故障码、实时样本时间戳与 seq。
//
// 距离换算（SI 推导）：声速 v=343 m/s（20℃ 常数）。往返 2d = v*T_echo。
//   dist_mm = echo_ticks * 10ns * 343e3 mm/s / 2
//           = echo_ticks * 343e3 / 2e8 = echo_ticks * 343 / 200000
//   K = round(343/200000 * 2^32) = 7365869;
//   dist_mm = (echo_ticks * K) >> 32, floor to integer millimetres.
//   echo_ticks 上限按 38ms 回波 = 3.8e6 ticks；乘积 3.8e6*7.37e6 ≈ 2.8e13 < 2^45，
//   用 48 位乘法中间量，无溢出。截断误差 < 1mm；实际精度由声速/模块决定。
`resetall
`timescale 1ns / 1ps
`default_nettype none

module car_ultrasonic #(
    parameter integer TS_W = 32   // 样本时间戳位宽（与公共计数器低 TS_W 位对齐）
)(
    input  wire             clk,
    input  wire             rst,
    input  wire             enable,          // 0=停止触发并保持失效发布
    input wire [31:0] now_ticks,
    output reg [31:0] sample_ts,
    input  wire             echo,            // 模块 Echo（原始电平，模块内同步）
    output reg              trig,            // Trig 输出
    // 配置（寄存器值，clk 单位）
    input  wire [31:0]      cfg_period,      // 完成后空闲（生产 6_000_000=60ms）
    input  wire [31:0]      cfg_max_echo,    // 单段Echo等待（生产 3_000_000=30ms）
    input  wire [31:0]      cfg_trig_clk,    // Trig 宽度（生产 1000=10µs）
    // 样本输出（对 car_snapshot live 侧）
    output reg  [31:0]      samp_data,       // [11:0]距离mm [15:12]故障码
    output reg              samp_valid,
    output reg              samp_update,     // 一拍：一批样本提交
    output reg  [15:0]      err_cnt,         // 异常测量累计（16 位饱和）
    output wire [15:0]      samp_seq         // 样本序号（真实测量完成才递增）
);

// ── 两级同步器 ──
(* ASYNC_REG = "TRUE" *) reg echo_ff1, echo_ff2, echo_ff3;
always @(posedge clk) begin
    if (rst) begin
        echo_ff1 <= 1'b0; echo_ff2 <= 1'b0; echo_ff3 <= 1'b0;
    end else begin
        echo_ff1 <= echo;
        echo_ff2 <= echo_ff1;
        echo_ff3 <= echo_ff2;   // 延迟一级用于边沿判定（等价 2FF 同步+1 历史）
    end
end
wire echo_rise =  echo_ff2 && !echo_ff3;
wire echo_fall = !echo_ff2 &&  echo_ff3;

// ── 状态机 ──
localparam [2:0] S_IDLE   = 3'd0,  // 周期计时
                 S_TRIG   = 3'd1,  // Trig 拉高
                 S_WAIT_R = 3'd2,  // 等 Echo 上升沿（超时→无回波）
                 S_WAIT_F = 3'd3,  // 等 Echo 下降沿（超时→卡高）
                 S_MUL1   = 3'd4,  // 乘法器内部乘积寄存器
                 S_MUL2   = 3'd5,  // 乘法器输出寄存器
                 S_EMIT   = 3'd6;  // 发布样本一拍

reg [2:0]  state;
reg [31:0] period_cnt;   // 周期计时
reg [31:0] wait_cnt;     // 超时计时
reg [31:0] pulse_start;  // Echo 上升沿时刻（ticks）
reg [31:0] echo_ticks;   // 脉宽
reg [15:0] seq_cnt;
reg        saw_high;     // 本轮测量中见过上升沿（上电卡高防护）
// A measurement uses one immutable configuration snapshot. AXI writes made
// while busy take effect on the next measurement and cannot shorten a pulse
// or timeout halfway through the current one.
reg [31:0] active_max_echo;
reg [31:0] active_trig_clk;

// 上电/复位后 echo 已高：echo_ff2 初始为 0（复位值），真实高电平同步进来时
// 会产生一个 echo_rise——但此时状态机不在 S_WAIT_R，该沿被忽略，不会误当
// 新回波；随后 S_WAIT_R 的超时机制兜底。saw_high 进一步防御。
reg [47:0] dist_product_m, dist_product_p;
wire [11:0] dist_mm = dist_product_p[47:32] > 16'd4095 ? 12'hFFF : dist_product_p[43:32];

always @(posedge clk) begin
    if (rst) begin
        state <= S_IDLE;
        sample_ts <= 0;
        period_cnt <= 32'b0;
        wait_cnt <= 32'b0;
        pulse_start <= 32'b0;
        echo_ticks <= 32'b0;
        dist_product_m <= 48'b0;
        dist_product_p <= 48'b0;
        active_max_echo <= 32'b0;
        active_trig_clk <= 32'b0;
        samp_data <= 32'b0;
        samp_valid <= 1'b0;
        samp_update <= 1'b0;
        err_cnt <= 16'b0;
        seq_cnt <= 16'b0;
        saw_high <= 1'b0;
        trig <= 1'b0;
    end else begin
        dist_product_m <= echo_ticks * 48'd7365869;
        dist_product_p <= dist_product_m;
        samp_update <= 1'b0;   // 默认单拍
        trig <= 1'b0;          // 默认低（S_TRIG 态覆盖）

        if (!enable || (state==S_IDLE &&
            (cfg_period==0 || cfg_max_echo==0 || cfg_trig_clk==0))) begin
            // 停止触发并持续发布无效（不清零样本寄存器内容，只降 valid）
            // enable是异步安全停机配置，任何状态立即生效；其余时序参数只在
            // IDLE检查，避免AXI中途改写破坏已经锁存的当前测量。
            state <= S_IDLE;
            period_cnt <= 32'b0;
            if (samp_valid) begin
                samp_valid <= 1'b0;
                samp_update <= 1'b1;
                sample_ts <= now_ticks;
                seq_cnt <= seq_cnt + 1'b1;
                samp_data <= {16'b0,4'd1,12'b0};
            end
        end else begin
            case (state)
                S_IDLE: begin
                    if (period_cnt >= cfg_period - 1'b1) begin
                        period_cnt <= 32'b0;
                        state <= S_TRIG;
                        saw_high <= 1'b0;
                        active_max_echo <= cfg_max_echo;
                        active_trig_clk <= cfg_trig_clk;
                    end else
                        period_cnt <= period_cnt + 1'b1;
                end
                S_TRIG: begin
                    trig <= 1'b1;
                    if (period_cnt >= active_trig_clk - 1'b1) begin
                        period_cnt <= 32'b0;
                        wait_cnt <= 32'b0;
                        state <= S_WAIT_R;
                    end else
                        period_cnt <= period_cnt + 1'b1;
                end
                S_WAIT_R: begin
                    wait_cnt <= wait_cnt + 1'b1;
                    if (echo_rise) begin
                        saw_high <= 1'b1;
                        pulse_start <= wait_cnt;   // 保持 wait_cnt 连续计数：
                        state <= S_WAIT_F;         // WAIT_F 用 wait_cnt-pulse_start
                                                   // 求脉宽；若在此清零，脉宽会短
                                                   // 掉 resp 段（DEF-3-08）
                    end else if (wait_cnt >= active_max_echo - 1'b1) begin
                        // 无回波：立即发布无效
                        sample_ts <= now_ticks;
                        samp_valid <= 1'b0;
                        samp_data <= {16'b0, 4'd1, 12'b0};
                        samp_update <= 1'b1;   /* samp_ts 由顶层锁存公共计数器 */
                        seq_cnt <= seq_cnt + 1'b1;
                        if (err_cnt != 16'hFFFF) err_cnt <= err_cnt + 1'b1;
                        state <= S_IDLE;
                        period_cnt <= 32'b0;
                    end
                end
                S_WAIT_F: begin
                    wait_cnt <= wait_cnt + 1'b1;
                    if (echo_fall && saw_high) begin
                        echo_ticks <= wait_cnt - pulse_start;
                        sample_ts <= now_ticks;
                        state <= S_MUL1;
                    end else if ((wait_cnt - pulse_start) >= active_max_echo - 1'b1) begin
                        // Unsigned elapsed interval survives counter wrap;
                        // wait_cnt is intentionally NOT reset at the rising edge.
                        // 卡高：立即发布无效
                        sample_ts <= now_ticks;
                        samp_valid <= 1'b0;
                        samp_data <= {16'b0, 4'd2, 12'b0};
                        samp_update <= 1'b1;   /* samp_ts 由顶层锁存公共计数器 */
                        seq_cnt <= seq_cnt + 1'b1;
                        if (err_cnt != 16'hFFFF) err_cnt <= err_cnt + 1'b1;
                        state <= S_IDLE;
                        period_cnt <= 32'b0;
                    end
                end
                S_MUL1: state <= S_MUL2;
                S_MUL2: state <= S_EMIT;
                S_EMIT: begin
                    // 量程检查：38ms 理论上限折算 ticks（cfg_max_echo 已含超时，此处查数值合理性）
                    if (echo_ticks == 32'b0 || echo_ticks > 32'd2_332_361) begin
                        samp_valid <= 1'b0;
                        samp_data <= {16'b0, 4'd3, 12'b0};
                    end else begin
                        samp_valid <= 1'b1;
                        samp_data <= {16'b0, 4'd0, dist_mm};
                    end
                    samp_update <= 1'b1;
                    seq_cnt <= seq_cnt + 1'b1;
                    if ((echo_ticks==0 || echo_ticks>32'd2_332_361) && err_cnt != 16'hFFFF)
                        err_cnt <= err_cnt + 1'b1;
                    state <= S_IDLE;
                    period_cnt <= 32'b0;
                end
                default: state <= S_IDLE;
            endcase
        end
    end
end

// 样本时间戳 = Echo 下降沿完成时刻（S_WAIT_F→S_EMIT 转移拍），
// Captured here from the top-level common counter, before publishing data.

assign samp_seq = seq_cnt;

endmodule

`resetall
