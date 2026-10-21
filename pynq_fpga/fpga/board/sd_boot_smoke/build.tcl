set source_dir [file dirname [file normalize [info script]]]
set output_dir [file join $source_dir output]
file mkdir $output_dir
create_project -in_memory -part xc7z020clg400-1
read_verilog [file join $source_dir sd_boot_led.v]
read_xdc [file join $source_dir sd_boot_led.xdc]
synth_design -top sd_boot_led -part xc7z020clg400-1
opt_design
place_design
route_design
set_property BITSTREAM.STARTUP.STARTUPCLK CCLK [current_design]
set_property BITSTREAM.CONFIG.UNUSEDPIN Pullnone [current_design]
report_drc -file [file join $output_dir drc.rpt]
foreach violation [get_drc_violations] {
    if {[get_property SEVERITY $violation] eq "Error"} {error "DRC error: $violation"}
}
if {[llength [get_cells -hier -filter {REF_NAME == OBUF}]] != 4} {error "Expected exactly four LED outputs"}
report_io -file [file join $output_dir io.rpt]
report_utilization -file [file join $output_dir utilization.rpt]
write_checkpoint -force [file join $output_dir routed.dcp]
write_verilog -force [file join $output_dir implemented.v]
write_bitstream -force [file join $output_dir sd_boot_led.bit]
puts "SD_BOOT_SMOKE_STATIC_LED0_BUILD_PASS"
