// This is the sobel pipeline module
module sobel_pipeline
   #(parameter WIDTH_P  = 640
    ,parameter HEIGHT_P = 480
    ,parameter CHANNELS_P = 1
    )
    (input   [0:0]    clk_i
    ,input   [0:0] resetn_i
    ,input   [0:0]  valid_i
    ,output  [0:0]  ready_o
    ,input  [63:0]  pixel_i
    ,output  [0:0]  valid_o
    ,input   [0:0]  ready_i
    ,output [63:0]  pixel_o
    ,output  [0:0]   last_o
    );

    wire [CHANNELS_P-1:0] ready_o_w, valid_o_w, last_o_w;

    assign ready_o = |ready_o_w;
    assign valid_o = |valid_o_w;
    assign last_o  = |last_o_w;

    generate
        for (genvar itr = 0; itr < CHANNELS_P; itr++) begin
            sobel_channel_filter
               #(.WIDTH_P(WIDTH_P)
                ,.HEIGHT_P(HEIGHT_P)
                )
            sobel_channel_filter_inst
                (.clk_i(clk_i)
                ,.reset_i(~resetn_i)
                ,.valid_i(valid_i)
                ,.ready_o(ready_o_w[itr])
                ,.pixel_i(pixel_i[itr*8 +: 8])
                ,.valid_o(valid_o_w[itr])
                ,.ready_i(ready_i)
                ,.pixel_o(pixel_o[itr*8 +: 8])
                ,.last_o(last_o_w[itr])
                );
        end
    endgenerate

endmodule

