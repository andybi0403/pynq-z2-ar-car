set pre_dir [file normalize [file join [file dirname [info script]] ..]]
set root [file normalize [file join $pre_dir ..]]
set_param board.repoPaths [file join $pre_dir board_repo]
set xpr [file join $root fpga build task7_8_preintegration task7_8_preintegration.xpr]
open_project $xpr
open_bd_design [get_files preintegration_bd.bd]
foreach cell {ps7 rst_100m gp_control_ic control_slot_stub video_vdma video_irq_concat video_hp0_ic video_width_adapter osd_slot_stub hdmi_dynclk hdmi_vtc hdmi_axis_to_video hdmi_rgb2dvi hdmi_hpd_gpio} {
 if {[llength [get_bd_cells -quiet $cell]] != 1} {error "Missing framework cell: $cell"}
}
set irq_net [get_bd_nets -quiet -of_objects [get_bd_pins video_vdma/mm2s_introut]]
set irq_concat_net [get_bd_nets -quiet -of_objects [get_bd_pins video_irq_concat/In0]]
if {[llength $irq_net] != 1 || $irq_net ne $irq_concat_net} {error "VDMA MM2S interrupt is not routed to the PS concat"}
set hpd_irq_net [get_bd_nets -quiet -of_objects [get_bd_pins hdmi_hpd_gpio/ip2intc_irpt]]
set hpd_concat_net [get_bd_nets -quiet -of_objects [get_bd_pins video_irq_concat/In1]]
if {[llength $hpd_irq_net] != 1 || $hpd_irq_net ne $hpd_concat_net} {error "HDMI HPD interrupt is not routed to the PS concat"}
set ps_irq_net [get_bd_nets -quiet -of_objects [get_bd_pins ps7/IRQ_F2P]]
set concat_out_net [get_bd_nets -quiet -of_objects [get_bd_pins video_irq_concat/dout]]
if {[llength $ps_irq_net] != 1 || $ps_irq_net ne $concat_out_net} {error "Video interrupt concat is not routed to PS IRQ_F2P"}
if {[llength [get_bd_intf_ports -quiet hdmi_out]] != 1} {error "Missing HDMI TMDS output"}
if {[llength [get_bd_ports -quiet hdmi_tx_hpdn]] != 1 || [get_property DIR [get_bd_ports hdmi_tx_hpdn]] ne "I"} {error "HDMI HPDN must be an input per local schematic sheet 6"}
set rgb2dvi_clock_xdc [get_files -quiet *rgb2dvi_clocks.xdc]
if {[llength $rgb2dvi_clock_xdc] != 1 || [get_property USED_IN_SYNTHESIS $rgb2dvi_clock_xdc] || [get_property USED_IN_IMPLEMENTATION $rgb2dvi_clock_xdc]} {error "External-clock rgb2dvi must not load its internal generated-clock XDC"}
foreach forbidden {car_perception_top.v car_axis_osd.v} {
 if {[llength [get_files -quiet *$forbidden]] != 0} {error "A-E production RTL leaked into framework: $forbidden"}
}
set slot_seg [get_bd_addr_segs -quiet ps7/Data/SEG_control_slot_stub_reg0]
set vdma_seg [get_bd_addr_segs -quiet ps7/Data/SEG_video_vdma_Reg]
set dynclk_seg [get_bd_addr_segs -quiet ps7/Data/SEG_hdmi_dynclk_reg0]
set vtc_seg [get_bd_addr_segs -quiet ps7/Data/SEG_hdmi_vtc_Reg]
set hpd_seg [get_bd_addr_segs -quiet ps7/Data/SEG_hdmi_hpd_gpio_Reg]
if {[llength $slot_seg] != 1 || [get_property OFFSET $slot_seg] ne "0x43C00000"} {error "Control slot address mismatch"}
if {[llength $vdma_seg] != 1 || [get_property OFFSET $vdma_seg] ne "0x43000000"} {error "VDMA address mismatch"}
if {[llength $dynclk_seg] != 1 || [get_property OFFSET $dynclk_seg] ne "0x43C10000"} {error "HDMI clock address mismatch"}
if {[llength $vtc_seg] != 1 || [get_property OFFSET $vtc_seg] ne "0x43C20000"} {error "HDMI VTC address mismatch"}
if {[llength $hpd_seg] != 1 || [get_property OFFSET $hpd_seg] ne "0x41230000"} {error "HDMI HPD address mismatch"}
validate_bd_design
close_project
puts "PREINTEGRATION_FRAMEWORK_CHECK_PASS"
