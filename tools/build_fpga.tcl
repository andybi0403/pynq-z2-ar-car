# Reuse the checked-in BD recreation and timing/DRC gates in this isolated tree.
set variant [file normalize [file join [file dirname [info script]] ..]]
source [file join $variant pynq_fpga preintegration vivado rebuild_video_reliability.tcl]
source [file join $variant pynq_fpga preintegration vivado write_lab_only_bitstream.tcl]
puts "PLAIN_MOTOR_FPGA_AND_HWH_PASS"
