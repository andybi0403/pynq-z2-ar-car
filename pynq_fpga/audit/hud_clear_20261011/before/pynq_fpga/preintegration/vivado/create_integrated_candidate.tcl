# Task 7/8 integrated candidate.  It consumes the accepted v0.6 perception
# top and OSD but remains non-release until the board/electrical gate passes.
set pre_dir [file normalize [file join [file dirname [info script]] ..]]
set project_root [file normalize [file join $pre_dir ..]]
set workspace [file normalize [file join $project_root ..]]
set board_repo [file join $pre_dir board_repo]
set build_dir [file join $project_root fpga build task7_8_integrated]
if {[info exists ::env(PYNQ_INTEGRATED_BUILD_DIR)]} {
 set build_dir [file normalize $::env(PYNQ_INTEGRATED_BUILD_DIR)]
}
set rtl_adapter [file join $pre_dir rtl axis32_to_rgb24.v]
set hdmi_xdc [file join $pre_dir constraints task7_8_integrated.xdc]
set pynq_ip_repo [file join $project_root third_party PYNQ boards ip]
set rtl_dir [file join $project_root fpga rtl]
set axil_dir [file join $project_root third_party verilog-axi rtl]
set wireless [expr {[info exists ::env(PYNQ_VIDEO_PROFILE)] && $::env(PYNQ_VIDEO_PROFILE) eq "wireless720"}]

set_param board.repoPaths [list $board_repo]
set board_part tul.com.tw:pynq-z2:part0:1.0
if {[llength [get_board_parts -quiet $board_part]] == 0} {
 error "Local PYNQ-Z2 board part not found at $board_repo"
}
create_project -force task7_8_integrated $build_dir -part xc7z020clg400-1
exec python [file join $pre_dir source_provenance.py] --capture [file join $build_dir source_contract.json]
set_property board_part $board_part [current_project]
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list $pynq_ip_repo] [current_project]
update_ip_catalog
add_files -norecurse $rtl_adapter
if {$wireless} {add_files -norecurse [file join $pre_dir rtl rgb24_to_axis32.v]}
add_files -norecurse [glob [file join $axil_dir axil_reg_if*.v]]
add_files -norecurse [glob [file join $rtl_dir *.v]]
add_files -norecurse [file join $rtl_dir car_reg_defs.vh]
add_files -norecurse [file join $rtl_dir font_8x8_minimal.mem]
add_files -norecurse [file join $rtl_dir font_16x16_hud.mem]
add_files -norecurse [file join $rtl_dir font_8x8_status.mem]
set_property include_dirs [list $rtl_dir] [get_filesets sources_1]
add_files -fileset constrs_1 -norecurse $hdmi_xdc
set_property PROCESSING_ORDER LATE [get_files $hdmi_xdc]

create_bd_design preintegration_bd
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {apply_board_preset "1" make_external "FIXED_IO, DDR" Master "Disable" Slave "Disable"} $ps
set_property CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100.000000} $ps
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_USE_S_AXI_HP0 {1} CONFIG.PCW_USE_FABRIC_INTERRUPT {1} CONFIG.PCW_IRQ_F2P_INTR {1} CONFIG.PCW_IRQ_F2P_MODE {DIRECT} CONFIG.PCW_UART1_PERIPHERAL_ENABLE {1} CONFIG.PCW_UART1_UART1_IO {EMIO}] $ps

set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_100m]
set gp [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:* gp_control_ic]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {5}] $gp
set car_system [create_bd_cell -type module -reference car_board_video_wrapper car_system]
if {$wireless} {set_property -dict [list CONFIG.VIDEO_WIDTH {1280} CONFIG.VIDEO_HEIGHT {720}] $car_system}

set vdma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:* video_vdma]
set_property -dict [list CONFIG.c_include_mm2s {1} CONFIG.c_include_s2mm {0} CONFIG.c_num_fstores {3} CONFIG.c_m_axi_mm2s_data_width {64} CONFIG.c_m_axis_mm2s_tdata_width {32} CONFIG.c_mm2s_genlock_mode {0}] $vdma
if {$wireless} {
 set_property -dict [list CONFIG.c_include_s2mm {1} CONFIG.c_m_axi_s2mm_data_width {64} CONFIG.c_s_axis_s2mm_tdata_width {32} CONFIG.c_s2mm_genlock_mode {0} CONFIG.c_use_fsync {0}] $vdma
}
set video_irq [create_bd_cell -type inline_hdl -vlnv xilinx.com:inline_hdl:ilconcat:1.0 video_irq_concat]
set_property CONFIG.NUM_PORTS {2} $video_irq
if {$wireless} {set_property CONFIG.NUM_PORTS {3} $video_irq}
# SmartConnect performs AXI4-to-AXI3 conversion without the legacy
# axi_protocol_converter burst-split FIFO that drove VDMA BRAM controls
# from asynchronously reset registers (REQP-1839 / PDCN-1569).
# Keep the VDMA, interconnect and PS HP0 on the same 100 MHz clock.
set mem [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 video_hp0_ic]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1} CONFIG.NUM_CLKS {1} CONFIG.HAS_ARESETN {1}] $mem
if {$wireless} {set_property CONFIG.NUM_SI {2} $mem}

set adapter [create_bd_cell -type module -reference axis32_to_rgb24 video_width_adapter]
set dynclk [create_bd_cell -type ip -vlnv digilentinc.com:ip:axi_dynclk:1.0 hdmi_dynclk]
set vtc [create_bd_cell -type ip -vlnv xilinx.com:ip:v_tc:6.2 hdmi_vtc]
set_property CONFIG.enable_detection {false} $vtc
set vidout [create_bd_cell -type ip -vlnv xilinx.com:ip:v_axi4s_vid_out:4.0 hdmi_axis_to_video]
set_property -dict [list CONFIG.C_ADDR_WIDTH {11} CONFIG.C_HAS_ASYNC_CLK {1} CONFIG.C_HYSTERESIS_LEVEL {1024} CONFIG.C_VTG_MASTER_SLAVE {1}] $vidout
set rgb2dvi [create_bd_cell -type ip -vlnv digilentinc.com:ip:rgb2dvi:1.2 hdmi_rgb2dvi]
set_property -dict [list CONFIG.kClkRange {2} CONFIG.kGenerateSerialClk {false} CONFIG.kRstActiveHigh {false}] $rgb2dvi
set hpd_gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 hdmi_hpd_gpio]
set_property -dict [list CONFIG.C_ALL_INPUTS {1} CONFIG.C_GPIO_WIDTH {1} CONFIG.C_INTERRUPT_PRESENT {1}] $hpd_gpio

make_bd_intf_pins_external [get_bd_intf_pins $rgb2dvi/TMDS]
set_property name hdmi_out [get_bd_intf_ports TMDS_0]
set hpd_port [create_bd_port -dir I hdmi_tx_hpdn]
connect_bd_net [get_bd_pins $hpd_gpio/gpio_io_i] $hpd_port

foreach pin {us_echo ir_l_raw ir_r_raw qei0_a qei0_b qei1_a qei1_b} {
 set port [create_bd_port -dir I $pin]
 connect_bd_net $port [get_bd_pins $car_system/$pin]
}
set trig_port [create_bd_port -dir O us_trig]
connect_bd_net $trig_port [get_bd_pins $car_system/us_trig]
set qei_oe_port [create_bd_port -dir O qei_oe_n]
connect_bd_net $qei_oe_port [get_bd_pins $car_system/qei_oe_n]
make_bd_intf_pins_external [get_bd_intf_pins $ps/UART_1]
set_property name uart [get_bd_intf_ports UART_1_0]

connect_bd_intf_net [get_bd_intf_pins $ps/M_AXI_GP0] [get_bd_intf_pins $gp/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins $gp/M00_AXI] [get_bd_intf_pins $vdma/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins $gp/M01_AXI] [get_bd_intf_pins $car_system/S_AXI]
connect_bd_intf_net [get_bd_intf_pins $gp/M02_AXI] [get_bd_intf_pins $dynclk/s00_axi]
connect_bd_intf_net [get_bd_intf_pins $gp/M03_AXI] [get_bd_intf_pins $vtc/ctrl]
connect_bd_intf_net [get_bd_intf_pins $gp/M04_AXI] [get_bd_intf_pins $hpd_gpio/S_AXI]
connect_bd_intf_net [get_bd_intf_pins $vdma/M_AXI_MM2S] [get_bd_intf_pins $mem/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins $mem/M00_AXI] [get_bd_intf_pins $ps/S_AXI_HP0]
connect_bd_intf_net [get_bd_intf_pins $vdma/M_AXIS_MM2S] [get_bd_intf_pins $adapter/S_AXIS]
connect_bd_net [get_bd_pins $vdma/mm2s_introut] [get_bd_pins $video_irq/In0]
connect_bd_net [get_bd_pins $hpd_gpio/ip2intc_irpt] [get_bd_pins $video_irq/In1]
connect_bd_net [get_bd_pins $video_irq/dout] [get_bd_pins $ps/IRQ_F2P]
connect_bd_intf_net [get_bd_intf_pins $adapter/M_AXIS] [get_bd_intf_pins $car_system/S_AXIS]
if {$wireless} {
 set capture_adapter [create_bd_cell -type module -reference rgb24_to_axis32 video_capture_adapter]
 connect_bd_intf_net [get_bd_intf_pins $car_system/M_AXIS] [get_bd_intf_pins $capture_adapter/S_AXIS]
 connect_bd_intf_net [get_bd_intf_pins $capture_adapter/M_AXIS] [get_bd_intf_pins $vdma/S_AXIS_S2MM]
 connect_bd_intf_net [get_bd_intf_pins $vdma/M_AXI_S2MM] [get_bd_intf_pins $mem/S01_AXI]
 connect_bd_net [get_bd_pins $vdma/s2mm_introut] [get_bd_pins $video_irq/In2]
 # HDMI debug uses the existing independent profile, never a READY fanout.
 set blank_data [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 hdmi_blank_data]
 set_property -dict [list CONFIG.CONST_WIDTH {24} CONFIG.CONST_VAL {0}] $blank_data
 set blank_valid [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 hdmi_blank_valid]
 set_property CONFIG.CONST_VAL {0} $blank_valid
 connect_bd_net [get_bd_pins $blank_data/dout] [get_bd_pins $vidout/s_axis_video_tdata]
 connect_bd_net [get_bd_pins $blank_valid/dout] [get_bd_pins $vidout/s_axis_video_tvalid] [get_bd_pins $vidout/s_axis_video_tuser] [get_bd_pins $vidout/s_axis_video_tlast]
} else {
 connect_bd_intf_net [get_bd_intf_pins $car_system/M_AXIS] [get_bd_intf_pins $vidout/video_in]
}
connect_bd_intf_net [get_bd_intf_pins $vtc/vtiming_out] [get_bd_intf_pins $vidout/vtiming_in]
connect_bd_intf_net [get_bd_intf_pins $vidout/vid_io_out] [get_bd_intf_pins $rgb2dvi/RGB]

set clk [get_bd_pins $ps/FCLK_CLK0]
set resetn [get_bd_pins $rst/peripheral_aresetn]
connect_bd_net $clk [get_bd_pins $ps/M_AXI_GP0_ACLK] [get_bd_pins $ps/S_AXI_HP0_ACLK]
connect_bd_net $clk [get_bd_pins $rst/slowest_sync_clk] [get_bd_pins $gp/ACLK] [get_bd_pins $gp/S00_ACLK] [get_bd_pins $gp/M00_ACLK] [get_bd_pins $gp/M01_ACLK] [get_bd_pins $gp/M02_ACLK] [get_bd_pins $gp/M03_ACLK] [get_bd_pins $gp/M04_ACLK]
connect_bd_net $clk [get_bd_pins $car_system/aclk] [get_bd_pins $vdma/s_axi_lite_aclk] [get_bd_pins $vdma/m_axi_mm2s_aclk] [get_bd_pins $vdma/m_axis_mm2s_aclk]
connect_bd_net $clk [get_bd_pins $mem/aclk] [get_bd_pins $adapter/aclk] [get_bd_pins $vidout/aclk]
if {$wireless} {
 connect_bd_net $clk [get_bd_pins $capture_adapter/aclk] [get_bd_pins $vdma/m_axi_s2mm_aclk] [get_bd_pins $vdma/s_axis_s2mm_aclk]
 connect_bd_net $resetn [get_bd_pins $capture_adapter/aresetn]
}
connect_bd_net $clk [get_bd_pins $dynclk/REF_CLK_I] [get_bd_pins $dynclk/s00_axi_aclk] [get_bd_pins $vtc/s_axi_aclk] [get_bd_pins $hpd_gpio/s_axi_aclk]
connect_bd_net [get_bd_pins $dynclk/PXL_CLK_O] [get_bd_pins $vidout/vid_io_out_clk] [get_bd_pins $vtc/clk] [get_bd_pins $rgb2dvi/PixelClk]
connect_bd_net [get_bd_pins $dynclk/PXL_CLK_5X_O] [get_bd_pins $rgb2dvi/SerialClk]
connect_bd_net [get_bd_pins $dynclk/LOCKED_O] [get_bd_pins $rgb2dvi/aRst_n]
connect_bd_net [get_bd_pins $ps/FCLK_RESET0_N] [get_bd_pins $rst/ext_reset_in]
connect_bd_net $resetn [get_bd_pins $gp/ARESETN] [get_bd_pins $gp/S00_ARESETN] [get_bd_pins $gp/M00_ARESETN] [get_bd_pins $gp/M01_ARESETN] [get_bd_pins $gp/M02_ARESETN] [get_bd_pins $gp/M03_ARESETN] [get_bd_pins $gp/M04_ARESETN]
connect_bd_net $resetn [get_bd_pins $car_system/aresetn] [get_bd_pins $vdma/axi_resetn]
connect_bd_net $resetn [get_bd_pins $mem/aresetn] [get_bd_pins $adapter/aresetn]
connect_bd_net $resetn [get_bd_pins $dynclk/s00_axi_aresetn] [get_bd_pins $vtc/s_axi_aresetn] [get_bd_pins $hpd_gpio/s_axi_aresetn]

assign_bd_address
assign_bd_address -offset 0x43000000 -range 0x00010000 -target_address_space [get_bd_addr_spaces $ps/Data] [get_bd_addr_segs $vdma/S_AXI_LITE/Reg] -force
assign_bd_address -offset 0x43C00000 -range 0x00001000 -target_address_space [get_bd_addr_spaces $ps/Data] [get_bd_addr_segs $car_system/S_AXI/reg0] -force
assign_bd_address -offset 0x43C10000 -range 0x00010000 -target_address_space [get_bd_addr_spaces $ps/Data] [get_bd_addr_segs $dynclk/s00_axi/reg0] -force
assign_bd_address -offset 0x43C20000 -range 0x00010000 -target_address_space [get_bd_addr_spaces $ps/Data] [get_bd_addr_segs $vtc/ctrl/Reg] -force
assign_bd_address -offset 0x41230000 -range 0x00010000 -target_address_space [get_bd_addr_spaces $ps/Data] [get_bd_addr_segs $hpd_gpio/S_AXI/Reg] -force
assign_bd_address -offset 0x00000000 -range 0x20000000 -target_address_space [get_bd_addr_spaces $vdma/Data_MM2S] [get_bd_addr_segs $ps/S_AXI_HP0/HP0_DDR_LOWOCM] -force
if {$wireless} {assign_bd_address -offset 0x00000000 -range 0x20000000 -target_address_space [get_bd_addr_spaces $vdma/Data_S2MM] [get_bd_addr_segs $ps/S_AXI_HP0/HP0_DDR_LOWOCM] -force}

validate_bd_design
save_bd_design
set bd_file [get_files preintegration_bd.bd]
generate_target all $bd_file
set rgb2dvi_clock_xdc [get_files -quiet *rgb2dvi_clocks.xdc]
if {[llength $rgb2dvi_clock_xdc] != 1} {error "Expected one rgb2dvi clock XDC"}
# With kGenerateSerialClk=false the two clocks arrive from axi_dynclk.  The
# upstream rgb2dvi XDC nevertheless declares SerialClk as a child of PixelClk;
# that relationship does not exist in this mode and produces an unconstrained
# duplicate clock in Vivado 2026.1.  Let the axi_dynclk output clocks propagate
# through the input ports instead.
set_property USED_IN_SYNTHESIS false $rgb2dvi_clock_xdc
set_property USED_IN_IMPLEMENTATION false $rgb2dvi_clock_xdc
make_wrapper -files $bd_file -top
add_files -norecurse [file join [file dirname $bd_file] hdl preintegration_bd_wrapper.v]
set_property top preintegration_bd_wrapper [get_filesets sources_1]
update_compile_order -fileset sources_1
close_project
puts "TASK7_8_INTEGRATED_CREATED: [file join $build_dir task7_8_integrated.xpr]"
