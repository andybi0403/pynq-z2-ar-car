# Build the video fix in its own directory; keep the original routed project.
set script_dir [file dirname [file normalize [info script]]]
set root [file normalize [file join $script_dir ../..]]
if {![info exists ::env(PYNQ_INTEGRATED_BUILD_DIR)]} {
 error "Use build_complete.ps1 or set an explicit fresh PYNQ_INTEGRATED_BUILD_DIR"
}
source [file join $script_dir create_integrated_candidate.tcl]
open_project [file join $::env(PYNQ_INTEGRATED_BUILD_DIR) task7_8_integrated.xpr]
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {
 error "Video reliability synthesis failed"
}
close_project
source [file join $script_dir impl_integrated_candidate.tcl]
puts "VIDEO_RELIABILITY_BUILD_PASS"
