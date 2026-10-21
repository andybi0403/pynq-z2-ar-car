set work {C:/Users/39909/Desktop/FPGA/pynq_fpga/fpga/build/task7_8_v09_hud_clear_20261011_r2/task7_8_integrated.runs/impl_1}
cd $work
file mkdir results
open_checkpoint preintegration_bd_wrapper_routed.dcp
report_methodology -file results/methodology.rpt
report_methodology -json results/methodology.json
write_xdc -force -exclude_physical results/constraints.xdc
report_timing -max_paths 20 -file results/failing_paths.rpt
close_design
