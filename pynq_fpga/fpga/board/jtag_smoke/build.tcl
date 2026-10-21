set source_dir [file dirname [file normalize [info script]]]
set output_dir [file join $source_dir output]
file mkdir $output_dir

create_project -in_memory -part xc7z020clg400-1
read_verilog [file join $source_dir led_switch.v]
read_xdc [file join $source_dir led_switch.xdc]
synth_design -top led_switch -part xc7z020clg400-1
opt_design
place_design
route_design
report_drc -file [file join $output_dir drc.rpt]
write_bitstream -force [file join $output_dir led_switch.bit]
puts "JTAG_SMOKE_BIT=[file join $output_dir led_switch.bit]"
