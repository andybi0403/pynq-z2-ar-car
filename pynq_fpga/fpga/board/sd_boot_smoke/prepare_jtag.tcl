set here [file dirname [file normalize [info script]]]
open_checkpoint [file join $here output routed.dcp]
set_property BITSTREAM.STARTUP.STARTUPCLK JTAGCLK [current_design]
write_bitstream -force [file join $here output jtag_led.bit]
close_design
