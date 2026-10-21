set pre_dir [file normalize [file join [file dirname [info script]] ..]]
set root [file normalize [file join $pre_dir ..]]
set_param board.repoPaths [file join $pre_dir board_repo]
set xpr [file join $root fpga build task7_8_preintegration task7_8_preintegration.xpr]
open_project $xpr
reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {error "Framework synthesis failed"}
open_run synth_1
report_utilization -file [file join $root fpga build task7_8_preintegration utilization_synth.rpt]
report_timing_summary -file [file join $root fpga build task7_8_preintegration timing_synth.rpt]
set worst_path [get_timing_paths -setup -max_paths 1]
if {[llength $worst_path] == 0} {error "No constrained setup timing path found"}
set wns [get_property SLACK $worst_path]
if {$wns < 0} {error "Negative framework synthesis WNS: $wns ns"}
puts "PREINTEGRATION_FRAMEWORK_WNS_NS=$wns"
close_project
puts "PREINTEGRATION_FRAMEWORK_SYNTH_PASS"
