# Task 7/8 integrated candidate.  Board-side pin mapping is verified against
# local XDC, part0_pins.xml and TUL R12; external sensor electrical readiness
# remains blocked in fpga/board/board_manifest.json.
set_property -dict { PACKAGE_PIN W14 IOSTANDARD LVCMOS33 } [get_ports {qei0_a}]
set_property -dict { PACKAGE_PIN Y14 IOSTANDARD LVCMOS33 } [get_ports {qei0_b}]
set_property -dict { PACKAGE_PIN T11 IOSTANDARD LVCMOS33 } [get_ports {qei1_a}]
set_property -dict { PACKAGE_PIN T10 IOSTANDARD LVCMOS33 } [get_ports {qei1_b}]
set_property -dict { PACKAGE_PIN V16 IOSTANDARD LVCMOS33 } [get_ports {us_trig}]
set_property -dict { PACKAGE_PIN W16 IOSTANDARD LVCMOS33 } [get_ports {us_echo}]
set_property -dict { PACKAGE_PIN V12 IOSTANDARD LVCMOS33 } [get_ports {uart_txd}]
set_property -dict { PACKAGE_PIN W13 IOSTANDARD LVCMOS33 } [get_ports {uart_rxd}]
set_property -dict { PACKAGE_PIN Y18 IOSTANDARD LVCMOS33 } [get_ports {ir_l_raw}]
set_property -dict { PACKAGE_PIN Y19 IOSTANDARD LVCMOS33 } [get_ports {ir_r_raw}]
set_property -dict { PACKAGE_PIN W18 IOSTANDARD LVCMOS33 } [get_ports {qei_oe_n}]

set_property -dict { PACKAGE_PIN L17 IOSTANDARD TMDS_33 } [get_ports {hdmi_out_clk_n}]
set_property -dict { PACKAGE_PIN L16 IOSTANDARD TMDS_33 } [get_ports {hdmi_out_clk_p}]
set_property -dict { PACKAGE_PIN K18 IOSTANDARD TMDS_33 } [get_ports {hdmi_out_data_n[0]}]
set_property -dict { PACKAGE_PIN K17 IOSTANDARD TMDS_33 } [get_ports {hdmi_out_data_p[0]}]
set_property -dict { PACKAGE_PIN J19 IOSTANDARD TMDS_33 } [get_ports {hdmi_out_data_n[1]}]
set_property -dict { PACKAGE_PIN K19 IOSTANDARD TMDS_33 } [get_ports {hdmi_out_data_p[1]}]
set_property -dict { PACKAGE_PIN H18 IOSTANDARD TMDS_33 } [get_ports {hdmi_out_data_n[2]}]
set_property -dict { PACKAGE_PIN J18 IOSTANDARD TMDS_33 } [get_ports {hdmi_out_data_p[2]}]
set_property -dict { PACKAGE_PIN R19 IOSTANDARD LVCMOS33 } [get_ports {hdmi_tx_hpdn}]

# Do not add internal PULLUPs by guess.  Echo/QEI must be driven through the
# verified external level/output-type path; LM393 IR modules contain their own
# VCC-referenced pull-up.  Applying an FPGA pull-up could hide an open wire.
