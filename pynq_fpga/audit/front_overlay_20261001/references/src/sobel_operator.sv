// I got this module from Mahboob Karimian's website:
//     https://hellotech.altervista.org/sobel-method-simulation-and-implementation-on-fpga/
// I modified the code slightly but this module is essentialy an optimized sobel operator.
/* verilator lint_off WIDTH */
module sobel_operator
    (input  [7:0] p0_i
    ,input  [7:0] p1_i
    ,input  [7:0] p2_i
    ,input  [7:0] p3_i
    ,input  [7:0] p4_i
    ,input  [7:0] p5_i
    ,input  [7:0] p6_i
    ,input  [7:0] p7_i
    ,input  [7:0] p8_i
    ,output [7:0] p4_o
    );

    // 11 bits because max value of gx_w and gy_w is 255*4 and last bit for sign
    wire signed [10:0] gx_w, gy_w;
    wire signed [10:0] abs_gx_w, abs_gy_w;
    wire        [10:0] sum_w;

    // Horizontal mask
    assign gx_w = ((p2_i - p0_i) + ((p5_i - p3_i) << 1) + (p8_i - p6_i));
    // Vertical mask
    assign gy_w = ((p0_i - p6_i) + ((p1_i - p7_i) << 1) + (p2_i - p8_i));

    // Absolute values of both axes
    assign abs_gx_w = (gx_w[10] ? ~gx_w + 1 : gx_w);
    assign abs_gy_w = (gy_w[10] ? ~gy_w + 1 : gy_w);

    // Add both axes to find the combined value
    assign sum_w = (abs_gx_w + abs_gy_w);

    // Limit the max value to 255    
    assign p4_o = (|sum_w[10:8]) ? 8'hff : sum_w[7:0];

endmodule
/* verilator lint_on WIDTH */

