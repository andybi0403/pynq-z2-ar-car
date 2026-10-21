// This is a read-priority 1R1W memory
module ram_1r1w_sync
   #(parameter WIDTH_P = 16
    ,parameter DEPTH_P = 64
    )
    (input                  [0:0]     clk_i
    ,input                  [0:0]   wr_en_i
    ,input  [$clog2(DEPTH_P)-1:0] wr_addr_i
    ,input          [WIDTH_P-1:0] wr_data_i
    ,input  [$clog2(DEPTH_P)-1:0] rd_addr_i
    ,output         [WIDTH_P-1:0] rd_data_o
    );

    logic [WIDTH_P-1:0] rd_data_r;

    // This is the memory block
    logic [WIDTH_P-1:0] mem [DEPTH_P-1:0];

    assign rd_data_o = rd_data_r;

    // Write
    always_ff @(posedge clk_i) begin
        if (wr_en_i) begin
            mem[wr_addr_i] <= wr_data_i;
        end
    end

    // Read
    always_ff @(posedge clk_i) begin
        rd_data_r <= mem[rd_addr_i];
    end

endmodule

