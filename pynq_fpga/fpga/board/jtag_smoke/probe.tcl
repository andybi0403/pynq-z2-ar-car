open_hw_manager
connect_hw_server -allow_non_jtag
set targets [get_hw_targets]
puts "JTAG_SMOKE_TARGETS=$targets"
foreach target $targets {
    if {[catch {open_hw_target $target} err]} {
        puts "JTAG_SMOKE_OPEN_ERROR=$target:$err"
    } else {
        puts "JTAG_SMOKE_DEVICES=[get_hw_devices]"
        close_hw_target
    }
}
disconnect_hw_server
close_hw_manager
