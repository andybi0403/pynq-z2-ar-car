// This is the sobel filter module for a single color channel
module sobel_channel_filter
   #(parameter WIDTH_P  = 10
    ,parameter HEIGHT_P = 10
    )
    (input  [0:0]   clk_i
    ,input  [0:0] reset_i
    ,input  [0:0] valid_i
    ,output [0:0] ready_o
    ,input  [7:0] pixel_i
    ,output [0:0] valid_o
    ,input  [0:0] ready_i
    ,output [7:0] pixel_o
    ,output [0:0]  last_o
    );

    // State registers
    enum logic [5:0] {LOAD_BUFFER_TOP_S  = 6'b000001
                     ,LOAD_BUFFER_BOT_S  = 6'b000010
                     ,PROCESSING_S       = 6'b000100
                     ,LAST_ROW_EMPTY_S   = 6'b001000
                     ,LAST_PIXEL_EMPTY_S = 6'b010000
                     } state_r, state_n;

    // Registers to manage AXI Lite
    logic [0:0] received_r, received_n;
    logic [7:0] pixel_in_r, pixel_in_n;

    // Pixel pointers
    logic [$clog2(HEIGHT_P)-1:0] row_ptr_r, row_ptr_n;
    logic  [$clog2(WIDTH_P)-1:0] col_ptr_r, col_ptr_n;

    // Wires for the ram buffer
    logic                 [0:0]   wr_en_r;
    logic [$clog2(WIDTH_P)-1:0] wr_addr_r;
    logic                [15:0] wr_data_r;
    logic [$clog2(WIDTH_P)-1:0] rd_addr_r;
    wire                 [15:0] rd_data_w;

    // The "real" 2x3 shift register buffer
    // 0: [0][1] -> top row
    // 1: [2][3] -> mid row
    // 2: [4][5] -> bot row
    logic [7:0] buffer_r [0:5];
    logic [7:0] buffer_n [0:5];

    // Wires for the sobel pixel mask module
    // 0: [0][1][2] -> top row
    // 1: [3][4][5] -> mid row
    // 2: [6][7][8] -> bot row
    logic [7:0] pixels_r [0:8];

    // Sobel filtered pixel
    wire [7:0] sobel_pixel_w;

    // Driver for the valid_o signal
    logic [0:0] ready_o_r;
    logic [0:0] valid_o_r;
    logic [0:0] last_o_r;

    // Output signals
    assign pixel_o = sobel_pixel_w;
    assign ready_o = ready_o_r;
    assign valid_o = valid_o_r;
    assign last_o  = last_o_r;

    //   This is the "shift register" buffer.
    //   We store 2 pixels in each row and store 2 rows of the image in the
    // entire buffer.
    //   [1][0]
    //   [1][0]
    //   [1][0]
    //   [1][0]
    //   [1][0]
    //    │  └── top row
    //    └───── bottom row
    ram_1r1w_sync
       #(.WIDTH_P(16)
        ,.DEPTH_P(WIDTH_P))
    ram_1r1w_sync_inst
        (.clk_i(clk_i)
        ,.wr_en_i(wr_en_r)
        ,.wr_addr_i(wr_addr_r)
        ,.wr_data_i(wr_data_r)
        ,.rd_addr_i(rd_addr_r)
        ,.rd_data_o(rd_data_w)
        );

    // This applies the sobel filter asynchronously
    sobel_operator
       #()
    sobel_operator_inst
        (.p0_i(pixels_r[0])
        ,.p1_i(pixels_r[1])
        ,.p2_i(pixels_r[2])
        ,.p3_i(pixels_r[3])
        ,.p4_i(pixels_r[4])
        ,.p5_i(pixels_r[5])
        ,.p6_i(pixels_r[6])
        ,.p7_i(pixels_r[7])
        ,.p8_i(pixels_r[8])
        ,.p4_o(sobel_pixel_w)
        );

    always_ff @(posedge clk_i) begin
        if (reset_i) begin
            state_r    <= LOAD_BUFFER_TOP_S;
            received_r <= 1'b0;
            pixel_in_r <= 8'h00;
            row_ptr_r  <= '0;
            col_ptr_r  <= '0;
            for (int i = 0; i < 9; i++) begin
                buffer_r[i] <= 8'h00;
            end
        end else begin
            state_r    <= state_n;
            received_r <= received_n;
            pixel_in_r <= pixel_in_n;
            row_ptr_r  <= row_ptr_n;
            col_ptr_r  <= col_ptr_n;
            for (int i = 0; i < 9; i++) begin
                buffer_r[i] <= buffer_n[i];
            end
        end
    end

    always_comb begin
        state_n    = state_r;
        received_n = received_r;
        pixel_in_n = pixel_in_r;
        row_ptr_n  = row_ptr_r;
        col_ptr_n  = col_ptr_r;
        for (int i = 0; i < 9; i++) begin
            pixels_r[i] = 8'h00;
        end
        for (int i = 0; i < 9; i++) begin
            buffer_n[i] = buffer_r[i];
        end
        wr_en_r    = 1'b0;
        wr_addr_r  = col_ptr_r;
        wr_data_r  = 16'h00;
        rd_addr_r  = col_ptr_r;
        ready_o_r  = ~received_r;
        valid_o_r  = received_r;
        last_o_r   = 1'b0;
        case (state_r)
            // In this state:
            //    Write a pixel to the top row at each cycle
            //    Don't give any output yet
            //    Continue with the bottom row after reaching the end
            LOAD_BUFFER_TOP_S: begin
                ready_o_r = 1'b1;
                // Input data needs to be valid
                if (valid_i) begin
                    // Increment pointers
                    col_ptr_n = col_ptr_r + 1;
                    // Write the input data
                    wr_en_r   = 1'b1;
                    wr_addr_r = col_ptr_r;
                    wr_data_r = {8'h0, pixel_i};
                    // Read the next address
                    rd_addr_r = col_ptr_r + 1;
                    // Reached the end of the row
                    if (col_ptr_r == WIDTH_P - 1) begin
                        state_n   = LOAD_BUFFER_BOT_S;
                        row_ptr_n = 1;
                        col_ptr_n = '0;
                        rd_addr_r = '0;
                    end
                end
            end
            // In this state:
            //    Write a pixel to the bottom row at each cycle
            //    Give "0" output (for the top row)
            //    Start processing the pixels after reaching the end
            LOAD_BUFFER_BOT_S: begin
                if (col_ptr_r == 0) begin
                    ready_o_r = 1'b1;
                    if (valid_i) begin
                        // Increment pointers
                        col_ptr_n = col_ptr_r + 1;
                        // Write the input data
                        wr_en_r   = 1'b1;
                        wr_addr_r = col_ptr_r;
                        wr_data_r = {8'h0, pixel_i};
                        // Read the next address
                        rd_addr_r = col_ptr_r + 1;
                    end
                end else begin
                    if (valid_i & ~received_r) begin
                        received_n = 1'b1;
                        pixel_in_n = pixel_i;
                    end
                    // Input data needs to be valid
                    if (ready_i & received_r) begin
                        received_n = 1'b0;
                        // Increment pointers
                        col_ptr_n  = col_ptr_r + 1;
                        // Write the input data
                        wr_en_r    = 1'b1;
                        wr_addr_r  = col_ptr_r;
                        wr_data_r  = {pixel_in_r, rd_data_w[7:0]};
                        // Read the next address
                        rd_addr_r  = col_ptr_r + 1;
                        // Starting from the second pixel in this row (*),
                        // output "0" data (pixels_r must be 0)
                        if (col_ptr_r > 0) begin
                            valid_o_r = 1'b1;
                        end
                        // Reached the end of the row
                        if (col_ptr_r == WIDTH_P - 1) begin
                            state_n   = PROCESSING_S;
                            row_ptr_n = 2;
                            col_ptr_n = '0;
                            rd_addr_r = '0;
                        end
                    end
                end
            end
            // In this state:
            //    Write the new pixel to the buffer
            //    Give the output for "top-left" pixel
            //    Switch to the next state when the last pixel is given
            PROCESSING_S: begin
                // Input data needs to be valid
                if (valid_i & ~received_r) begin
                    received_n = 1'b1;
                    pixel_in_n = pixel_i;
                end
                if (ready_i & received_r) begin
                    received_n = 1'b0;
                    if (col_ptr_r < WIDTH_P - 1) begin
                        col_ptr_n = col_ptr_r + 1;
                    end else begin
                        row_ptr_n = row_ptr_r + 1;
                        col_ptr_n = '0;
                    end
                    if (col_ptr_r == 0) begin
                        buffer_n[0] = rd_data_w[7:0];
                        buffer_n[2] = rd_data_w[15:8];
                        buffer_n[4] = pixel_in_r;
                        wr_en_r     = 1'b1;
                        wr_addr_r   = col_ptr_r;
                        wr_data_r   = {pixel_in_r, rd_data_w[15:8]};
                        rd_addr_r   = col_ptr_r + 1;
                    end
                    if (col_ptr_r == 1) begin
                        buffer_n[1] = rd_data_w[7:0];
                        buffer_n[3] = rd_data_w[15:8];
                        buffer_n[5] = pixel_in_r;
                        wr_en_r     = 1'b1;
                        wr_addr_r   = col_ptr_r;
                        wr_data_r   = {pixel_in_r, rd_data_w[15:8]};
                        rd_addr_r   = col_ptr_r + 1;
                    end
                    if (col_ptr_r > 1) begin
                        pixels_r[0] = buffer_r[0];
                        pixels_r[3] = buffer_r[2];
                        pixels_r[6] = buffer_r[4];
                        pixels_r[1] = buffer_r[1];
                        pixels_r[4] = buffer_r[3];
                        pixels_r[7] = buffer_r[5];
                        pixels_r[2] = rd_data_w[7:0];
                        pixels_r[5] = rd_data_w[15:8];
                        pixels_r[8] = pixel_in_r;
                        buffer_n[0] = buffer_r[1];
                        buffer_n[2] = buffer_r[3];
                        buffer_n[4] = buffer_r[5];
                        buffer_n[1] = rd_data_w[7:0];
                        buffer_n[3] = rd_data_w[15:8];
                        buffer_n[5] = pixel_in_r;
                        wr_en_r     = 1'b1;
                        wr_addr_r   = col_ptr_r;
                        wr_data_r   = {pixel_in_r, rd_data_w[15:8]};
                        rd_addr_r   = col_ptr_r + 1;
                        valid_o_r   = 1'b1;
                        if (col_ptr_r == WIDTH_P - 1) begin
                            col_ptr_n = '0;
                            rd_addr_r = '0;
                            if (row_ptr_r == HEIGHT_P - 1) begin
                                state_n   = LAST_ROW_EMPTY_S;
                            end
                        end
                    end
                end
            end
            LAST_ROW_EMPTY_S: begin
                ready_o_r = 1'b0;
                valid_o_r = 1'b1;
                if (ready_i) begin
                    col_ptr_n = col_ptr_r + 1;
                    if (col_ptr_r == WIDTH_P - 1) begin
                        state_n = LAST_PIXEL_EMPTY_S;
                    end
                end
            end
            LAST_PIXEL_EMPTY_S: begin
                ready_o_r = 1'b0;
                valid_o_r = 1'b1;
                last_o_r  = 1'b1;
                if (ready_i) begin
                    state_n    = LOAD_BUFFER_TOP_S;
                    received_n = 1'b0;
                    row_ptr_n  = '0;
                    col_ptr_n  = '0;
                end
            end
            default: begin
            end
        endcase
    end

endmodule

