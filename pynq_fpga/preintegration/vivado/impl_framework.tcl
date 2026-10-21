set pre_dir [file normalize [file join [file dirname [info script]] ..]]
set root [file normalize [file join $pre_dir ..]]
set_param board.repoPaths [file join $pre_dir board_repo]
set xpr [file join $root fpga build task7_8_preintegration task7_8_preintegration.xpr]
open_project $xpr
reset_run impl_1
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {[get_property STATUS [get_runs impl_1]] ne "route_design Complete!"} {
  error "Framework implementation failed: [get_property STATUS [get_runs impl_1]]"
}
open_run impl_1
set report_dir [file join $root fpga build task7_8_preintegration]
report_utilization -file [file join $report_dir utilization_impl.rpt]
report_timing_summary -file [file join $report_dir timing_impl.rpt]
report_drc -file [file join $report_dir drc_impl.rpt]
report_io -file [file join $report_dir io_impl.rpt]

set setup_path [get_timing_paths -setup -max_paths 1]
set hold_path [get_timing_paths -hold -max_paths 1]
if {[llength $setup_path] == 0 || [llength $hold_path] == 0} {
  error "Implementation has no constrained setup/hold timing path"
}
set wns [get_property SLACK $setup_path]
set whs [get_property SLACK $hold_path]
if {$wns < 0 || $whs < 0} {
  error "Implementation timing failed: WNS=$wns ns WHS=$whs ns"
}
set bad_drc [get_drc_violations -quiet -filter {SEVERITY == "Error" || SEVERITY == "Critical Warning"}]
if {[llength $bad_drc] != 0} {
  error "Implementation has blocking DRC violations: $bad_drc"
}
puts "PREINTEGRATION_FRAMEWORK_IMPL_WNS_NS=$wns"
puts "PREINTEGRATION_FRAMEWORK_IMPL_WHS_NS=$whs"
close_project
puts "PREINTEGRATION_FRAMEWORK_IMPL_PASS"
