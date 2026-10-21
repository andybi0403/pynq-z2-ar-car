// PYNQ-Z2 JTAG smoke test. No PS clock, SD card, or external wiring required.
module led_switch (
    input  wire [1:0] sw,
    input  wire [1:0] btn,
    output wire [3:0] led
);
    assign led = {btn[1], btn[0], sw[1], sw[0]};
endmodule
