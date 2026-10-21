`timescale 1ns/1ps
module testbench();

    localparam WIDTH    = 640;
    localparam HEIGHT   = 480;
    localparam CHANNELS = 3;

    localparam DEBUG    = 0;
    localparam WAVEFORM = 1;

    logic  [0:0] clk;
    logic  [0:0] reset;

    logic [(CHANNELS*8)-1:0] image_r [WIDTH-1:0][HEIGHT-1:0];

    logic              [0:0] valid_i_r;
    wire               [0:0] ready_o_w;
    logic [(CHANNELS*8)-1:0] pixel_i_r;
    wire               [0:0] valid_o_w;
    logic              [0:0] ready_i_r;
    wire  [(CHANNELS*8)-1:0] pixel_o_w;
    wire               [0:0]  last_o_w;

    integer row_int;
    integer col_int;

    /* verilator lint_off WIDTH */
    sobel_pipeline
       #(.WIDTH_P(WIDTH)
        ,.HEIGHT_P(HEIGHT)
        ,.CHANNELS_P(CHANNELS)
        )
    sobel_pipeline_inst
        (.clk_i(clk)
        ,.resetn_i(~reset)
        ,.valid_i(valid_i_r)
        ,.ready_o(ready_o_w)
        ,.pixel_i(pixel_i_r)
        ,.valid_o(valid_o_w)
        ,.ready_i(ready_i_r)
        ,.pixel_o(pixel_o_w)
        ,.last_o(last_o_w)
        );
    /* verilator lint_on WIDTH */

    initial begin
        clk = 1;
        forever
            #5 clk = ~clk;
    end

    initial begin
        if (DEBUG || WAVEFORM) begin
`ifdef VERILATOR
            $dumpfile("verilator.fst");
`else
            $dumpfile("iverilog.vcd");
`endif
            $dumpvars;
        end

        row_int = 0;
        col_int = 0;

        valid_i_r = 1'b0;
        ready_i_r = 1'b1;
        pixel_i_r = '0;

        $display("Begin Test:");

        $display("   Reading image file: sample.hex");
        $readmemh("sample.hex", image_r);
        $display("   Image file is read.");
        if (DEBUG) begin
            $display("      Sample pixel at (%0d, %0d) = 0x%0h", 5, 5, image_r[5][5]);
        end

        $display("   Applying reset...");
        @(negedge clk);
        reset = 1'b1;
        for (int i = 0; i < 10; i = i + 1) begin
            @(negedge clk);
        end
        reset = 1'b0;
        $display("   Reset applied.");

        $display("   Starting to apply the filter.");
        @(posedge clk);
        #(1);
        while (row_int < HEIGHT) begin
            valid_i_r = 1'b1;
            pixel_i_r = image_r[col_int][row_int];
            if (ready_o_w) begin
                if (DEBUG) begin
                    $display("      Sending pixel (%0d, %0d) = 0x%0h", col_int, row_int, pixel_i_r);
                end
                col_int++;
                if (col_int == WIDTH) begin
                    row_int++;
                    col_int = 0;
                end
            end
            @(posedge clk);
            #(1);
        end

        // Disable input here
        valid_i_r = 1'b0;

        for (int i = 0 ; i < WIDTH * 2; i++) begin
            @(posedge clk);
        end
        $display("   Filter should be applied now.");

        if (DEBUG) begin
            $display("      Sample pixel at (%0d, %0d) = 0x%0h", 5, 5, image_r[5][5]);
        end

        $finish();
    end

    integer out_row_int = 0;
    integer out_col_int = 0;
    always_ff @(negedge clk) begin
        if (valid_o_w & ready_i_r) begin
            image_r[out_col_int][out_row_int] <= pixel_o_w;
            if (DEBUG) begin
                $display("      Receiving pixel (%0d, %0d) = 0x%0h", out_col_int, out_row_int, pixel_o_w);
            end
            out_col_int <= out_col_int + 1;
            if (out_col_int == WIDTH - 1) begin
                out_row_int <= out_row_int + 1;
                out_col_int <= 0;
            end
        end
    end

    final begin
        $display("End test:");
        $display("   Writing the output hex file.");
        $writememh("filtered.hex", image_r);
        $display("   Hex file is written.");
    end

endmodule

