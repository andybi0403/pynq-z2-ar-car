# Produce a bench-only bitstream from the already-routed integrated candidate.
# This script deliberately does not change board_manifest release_ready and the
# output name carries LAB_ONLY so it cannot be confused with a release image.
set pre_dir [file normalize [file join [file dirname [info script]] ..]]
set root [file normalize [file join $pre_dir ..]]
set_param board.repoPaths [file join $pre_dir board_repo]

set build_dir [file join $root fpga build task7_8_integrated]
if {[info exists ::env(PYNQ_INTEGRATED_BUILD_DIR)]} {
 set build_dir [file normalize $::env(PYNQ_INTEGRATED_BUILD_DIR)]
}
set xpr [file join $build_dir task7_8_integrated.xpr]
exec python [file join $pre_dir source_provenance.py] --check [file join $build_dir source_contract.json]
if {![info exists ::env(PYNQ_LAB_OUT_DIR)]} {error "Set explicit PYNQ_LAB_OUT_DIR or use build_complete.ps1"}
set out_dir [file normalize $::env(PYNQ_LAB_OUT_DIR)]
set bit_path [file join $out_dir task7_8_LAB_ONLY.bit]
set hwh_path [file join $out_dir task7_8_LAB_ONLY.hwh]
set hwh_source [file join $build_dir task7_8_integrated.gen sources_1 bd preintegration_bd hw_handoff preintegration_bd.hwh]

file mkdir $out_dir
open_project $xpr
if {[get_property STATUS [get_runs impl_1]] ne "route_design Complete!"} {
  error "LAB_ONLY requires the verified routed implementation; got [get_property STATUS [get_runs impl_1]]"
}
open_run impl_1
report_drc -file [file join $out_dir drc_LAB_ONLY.rpt]
report_bus_skew -warn_on_violation -file [file join $out_dir bus_skew_LAB_ONLY.rpt]
# Reliability warnings are build failures for the revised video path;
# do not suppress or lower their severity.
set video_drc [get_drc_violations -quiet -filter {NAME =~ "REQP-1839*" || NAME =~ "PDCN-1569*"}]
if {[llength $video_drc] != 0} {
  error "Video reliability DRC remains: $video_drc"
}

set setup_path [get_timing_paths -setup -max_paths 1]
set hold_path [get_timing_paths -hold -max_paths 1]
if {[llength $setup_path] == 0 || [llength $hold_path] == 0} {
  error "LAB_ONLY design has no constrained setup/hold timing path"
}
set wns [get_property SLACK $setup_path]
set whs [get_property SLACK $hold_path]
if {$wns < 0 || $whs < 0} {
  error "LAB_ONLY timing failed: WNS=$wns ns WHS=$whs ns"
}
set bad_drc [get_drc_violations -quiet -filter {SEVERITY == "Error" || SEVERITY == "Critical Warning" || SEVERITY == "Warning"}]
if {[llength $bad_drc] != 0} {
  error "LAB_ONLY DRC warnings/errors remain: $bad_drc"
}
if {![file isfile $hwh_source]} {
  error "Integrated HWH is missing: $hwh_source"
}

set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
write_bitstream -force $bit_path
file copy -force $hwh_source $hwh_path
exec python [file join $pre_dir source_provenance.py] --bind [file join $build_dir source_contract.json] --bit $bit_path --hwh $hwh_path --output [file join $out_dir artifact_source_binding.json]
report_timing_summary -file [file join $out_dir timing_LAB_ONLY.rpt]
report_drc -file [file join $out_dir drc_LAB_ONLY.rpt]
report_io -file [file join $out_dir io_LAB_ONLY.rpt]

puts "TASK7_8_LAB_ONLY_BIT=$bit_path"
puts "TASK7_8_LAB_ONLY_HWH=$hwh_path"
puts "TASK7_8_LAB_ONLY_WNS_NS=$wns"
puts "TASK7_8_LAB_ONLY_WHS_NS=$whs"
puts "TASK7_8_LAB_ONLY_PASS"
close_project
