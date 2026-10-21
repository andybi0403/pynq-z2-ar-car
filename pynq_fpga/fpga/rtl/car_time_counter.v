// car_time_counter.v -- 自由运行时间计数器（契约 §2）
// 单位：1 tick = 1 clk 周期。生产配置 WIDTH=64（100MHz 下回绕周期约 5849 年）；
// 仿真允许参数化短位宽验证回绕，短位宽不得进入生产配置。
// 复位：同步高有效，复位后计数为 0。
`resetall
`timescale 1ns / 1ps
`default_nettype none

module car_time_counter #(
    parameter integer WIDTH = 64
)(
    input  wire             clk,
    input  wire             rst,
    output reg  [WIDTH-1:0] count
);

always @(posedge clk) begin
    if (rst)
        count <= {WIDTH{1'b0}};
    else
        count <= count + {{(WIDTH-1){1'b0}}, 1'b1};
end

endmodule

`resetall
