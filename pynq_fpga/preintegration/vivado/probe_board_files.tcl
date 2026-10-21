set pre_dir [file normalize [file join [file dirname [info script]] ..]]
set board_repo [file join $pre_dir board_repo]
set_param board.repoPaths $board_repo
puts "BOARD_REPO=$board_repo"
puts "PYNQ_BOARD_PARTS=[get_board_parts -quiet *pynq*]"
puts "TUL_BOARD_PARTS=[get_board_parts -quiet tul.com.tw:*]"
exit
