# Temporary PL-only LED diagnostic. No flash, EEPROM, PS, or motor writes.
set here [file dirname [file normalize [info script]]]
open_hw_manager
connect_hw_server -allow_non_jtag
set targets [get_hw_targets]
puts "LED_DIAG_TARGETS=$targets"
if {[llength $targets] != 1} {
    error "Expected exactly one connected JTAG target; no programming performed"
}
open_hw_target [lindex $targets 0]
set devices [get_hw_devices -filter {PART =~ "xc7z020*"}]
puts "LED_DIAG_DEVICES=$devices"
if {[llength $devices] != 1} {
    error "Expected exactly one xc7z020; no programming performed"
}
set device [lindex $devices 0]
current_hw_device $device
set_property PROGRAM.FILE [file join $here output jtag_led.bit] $device
program_hw_devices $device
refresh_hw_device $device
report_property $device
puts "LED_DIAG_PROGRAM_COMMAND_COMPLETED"
close_hw_target
disconnect_hw_server
close_hw_manager
