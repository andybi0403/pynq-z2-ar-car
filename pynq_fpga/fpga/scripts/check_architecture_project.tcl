set root [file normalize [file join [file dirname [info script]] ../..]]
set xpr [file join $root fpga build car_architecture_v0_6 car_architecture_v0_6.xpr]
if {![file exists $xpr]} {error "missing architecture project: $xpr"}
open_project $xpr
update_compile_order -fileset sources_1
set actual_top [get_property top [get_filesets sources_1]]
if {$actual_top ne "car_perception_top"} {error "unexpected top: $actual_top"}
set missing {}
foreach required {car_perception_top.v car_risk_core.v car_sensors_core.v car_qei_core.v car_axis_osd.v} {
 if {[llength [get_files -quiet */$required]] == 0} {lappend missing $required}
}
if {[llength $missing] != 0} {error "missing architecture sources: $missing"}
close_project
puts "ARCHITECTURE_PROJECT_CHECK_PASS"
