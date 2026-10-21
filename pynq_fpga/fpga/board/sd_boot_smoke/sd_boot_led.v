// PYNQ-Z2 early SD boot indicator. Pure combinational logic, no clocks or PS I/O.
module sd_boot_led(output wire [3:0] led);
    assign led = 4'b0001;
endmodule
