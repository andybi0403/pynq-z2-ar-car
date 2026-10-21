set work {C:/Users/39909/Desktop/FPGA/pynq_fpga/fpga/build/task7_8_v09_hud_clear_20261011_r3/task7_8_integrated.runs/impl_1}
cd $work
file mkdir results
open_checkpoint preintegration_bd_wrapper_routed.dcp
report_methodology -file results/methodology.rpt
report_methodology -json results/methodology.json
write_xdc -force -exclude_physical results/constraints.xdc
set properties_file [open results/methodology_properties.rpt w]
foreach violation [get_methodology_violations] {
 puts $properties_file "VIOLATION=$violation"
 foreach property [list_property $violation] {
  puts $properties_file "$property=[get_property $property $violation]"
 }
}
close $properties_file
close_design
