# Recreate the reviewable v0.6 RTL architecture project.  This is a PL-only
# project: PS/DDR/VDMA/HDMI and package-pin constraints are later integration.
set root [file normalize [file join [file dirname [info script]] ../..]]
set project_dir [file join $root fpga build car_architecture_v0_6]
create_project -force car_architecture_v0_6 $project_dir -part xc7z020clg400-1
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]

add_files -norecurse [glob [file join $root third_party verilog-axi rtl axil_reg_if*.v]]
add_files -norecurse [glob [file join $root fpga rtl *.v]]
add_files -norecurse [file join $root fpga rtl font_8x8_minimal.mem]
add_files -norecurse [file join $root fpga rtl font_16x16_hud.mem]
set_property include_dirs [list [file join $root fpga rtl]] [get_filesets sources_1]
add_files -fileset constrs_1 -norecurse [file join $root fpga constraints architecture_ooc.xdc]
set_property top car_perception_top [get_filesets sources_1]
update_compile_order -fileset sources_1

set_property strategy Flow_PerfOptimized_high [get_runs synth_1]
close_project
puts "ARCHITECTURE_PROJECT_CREATED: [file join $project_dir car_architecture_v0_6.xpr]"
