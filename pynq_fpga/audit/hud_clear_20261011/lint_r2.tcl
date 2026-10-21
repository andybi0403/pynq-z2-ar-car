set rtl {C:/Users/39909/Desktop/FPGA/pynq_fpga/fpga/rtl}
create_project -in_memory -part xc7z020clg400-1
read_verilog [file join $rtl car_axis_osd.v]
add_files -norecurse [file join $rtl font_16x16_hud.mem]
add_files -norecurse [file join $rtl font_24x24_hud.mem]
add_files -norecurse [file join $rtl font_32x32_hud.mem]
synth_design -top car_axis_osd -part xc7z020clg400-1 -lint -file {C:/Users/39909/Desktop/FPGA/pynq_fpga/audit/hud_clear_20261011/car_axis_osd_lint_r2.csv}
close_project
create_project -in_memory -part xc7z020clg400-1
read_verilog [file join $rtl car_axis_status_osd.v]
add_files -norecurse [file join $rtl font_16x16_hud.mem]
add_files -norecurse [file join $rtl font_24x24_hud.mem]
add_files -norecurse [file join $rtl font_32x32_hud.mem]
synth_design -top car_axis_status_osd -part xc7z020clg400-1 -lint -file {C:/Users/39909/Desktop/FPGA/pynq_fpga/audit/hud_clear_20261011/car_axis_status_osd_lint_r2.csv}
close_project
create_project -in_memory -part xc7z020clg400-1
read_verilog [file join $rtl car_axis_front_overlay.v]
add_files -norecurse [file join $rtl font_16x16_hud.mem]
add_files -norecurse [file join $rtl font_24x24_hud.mem]
add_files -norecurse [file join $rtl font_32x32_hud.mem]
synth_design -top car_axis_front_overlay -part xc7z020clg400-1 -lint -file {C:/Users/39909/Desktop/FPGA/pynq_fpga/audit/hud_clear_20261011/car_axis_front_overlay_lint_r2.csv}
close_project
