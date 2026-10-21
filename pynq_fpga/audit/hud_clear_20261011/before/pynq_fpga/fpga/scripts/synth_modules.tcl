# Reproducible module-only OOC synthesis, not a board design or timing closure.
set root [file normalize [file join [file dirname [info script]] ../..]]
set out [file join $root fpga build acceptance_synth]
if {[info exists ::env(PYNQ_OOC_OUT_DIR)]} {
 set out [file normalize $::env(PYNQ_OOC_OUT_DIR)]
}
file mkdir $out
set tops {car_qei_top car_sensors_top car_axil_regs car_risk_core car_perception_top car_axis_osd car_axis_front_overlay car_axis_status_osd car_axis_frame_metadata car_board_video_wrapper}
if {$argc > 0} {set tops $argv}
foreach top $tops {
 create_project -in_memory -part xc7z020clg400-1
 add_files -norecurse [file join $root fpga rtl font_8x8_minimal.mem]
 add_files -norecurse [file join $root fpga rtl font_16x16_hud.mem]
 add_files -norecurse [file join $root fpga rtl font_8x8_status.mem]
 read_verilog [glob [file join $root third_party verilog-axi rtl axil_reg_if*.v]]
 read_verilog -sv [glob [file join $root fpga rtl *.v]]
 synth_design -top $top -part xc7z020clg400-1 -mode out_of_context
 set clock_port [get_ports -quiet clk]
 if {[llength $clock_port]==0} {set clock_port [get_ports -quiet aclk]}
 if {[llength $clock_port]!=1} {error "Expected one 100MHz clock port for $top"}
 create_clock -name sys_clk -period 10.000 $clock_port
 report_utilization -file [file join $out ${top}_utilization.rpt]
 report_timing_summary -file [file join $out ${top}_timing.rpt]
 write_checkpoint -force [file join $out ${top}.dcp]
 close_project
}
puts "MODULE_SYNTHESIS_COMPLETED"
