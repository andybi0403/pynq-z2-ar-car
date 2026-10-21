cd {C:/Users/39909/Desktop/FPGA/pynq_fpga/fpga/build/task7_8_v09_hud_clear_20261011_r2/task7_8_integrated.runs/impl_1}
open_checkpoint preintegration_bd_wrapper_routed.dcp
set properties_file [open results/port_properties.rpt w]
foreach name {hdmi_tx_hpdn ir_l_raw ir_r_raw qei0_a qei0_b qei1_a qei1_b us_echo qei_oe_n us_trig} {
 set port [get_ports $name]
 puts $properties_file "PORT=$name"
 foreach property [list_property $port] {
  puts $properties_file "$property=[get_property $property $port]"
 }
}
close $properties_file
report_clocks -file results/clocks.rpt
report_clock_interaction -file results/clock_interaction.rpt
foreach name {hdmi_tx_hpdn ir_l_raw ir_r_raw qei0_a qei0_b qei1_a qei1_b us_echo} {
 report_timing -from [get_ports $name] -file results/input_${name}_timing.rpt
}
foreach name {qei_oe_n us_trig} {
 report_timing -to [get_ports $name] -file results/output_${name}_timing.rpt
}
close_design
