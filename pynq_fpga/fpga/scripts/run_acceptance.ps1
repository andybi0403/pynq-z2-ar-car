# Tasks 1-4 plus Night A regression; synthesis is an explicit -Synthesis option.
param([switch]$Synthesis)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$workspace=Split-Path $project -Parent
$out=Join-Path $project ('nightly/acceptance_20260918/run_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $out -Force | Out-Null
Start-Transcript -Path (Join-Path $out 'regression.log') | Out-Null
try {
    $firmwares=@(Get-ChildItem -LiteralPath $workspace -Directory | Where-Object {
        Test-Path (Join-Path $_.FullName 'tests/run_tests.cmd')
    })
    if($firmwares.Count -ne 2){throw 'Expected exactly two existing STM32 test projects'}
    foreach($firmware in $firmwares){
        & (Join-Path $firmware.FullName 'tests/run_tests.cmd')
        if($LASTEXITCODE -ne 0){throw "C test failed: $($firmware.Name)"}
    }
    $pc=@(Get-ChildItem -LiteralPath $workspace -Directory | Where-Object {
        Test-Path (Join-Path $_.FullName 'pc/test_pynq_link.py')
    })
    if($pc.Count -ne 1){throw 'Expected one canonical pynq_link test directory'}
    $python=Join-Path $env:LOCALAPPDATA 'Programs/Python/Python314/python.exe'
    Push-Location (Join-Path $pc[0].FullName 'pc')
    try{
        & $python -m unittest test_pynq_link test_console test_hybrid_link
        if($LASTEXITCODE -ne 0){throw 'Python tests failed'}
    }finally{Pop-Location}
    $reggen=Join-Path $project 'fpga/registers/generate_register_map.py'
    & $python $reggen --check
    if($LASTEXITCODE -ne 0){throw 'Register map generated files are stale or invalid'}
    $cBuild=Join-Path $project 'host/c_build/build_car_c_dll.ps1'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $cBuild
    if($LASTEXITCODE -ne 0){throw 'Integrated production safe_control DLL build failed'}
    & $python -m unittest discover -s (Join-Path $project 'host/tests') -p 'test_*.py'
    if($LASTEXITCODE -ne 0){throw 'Integrated host contract tests failed'}
    & $python (Join-Path $project 'preintegration/run_supervisor_fault_matrix.py') --output (Join-Path $out 'supervisor_fault_matrix')
    if($LASTEXITCODE -ne 0){throw 'Production C supervisor fault matrix failed'}
    & $python -m unittest discover -s (Join-Path $project 'preintegration/tests') -p 'test_*.py'
    if($LASTEXITCODE -ne 0){throw 'Integrated runtime/video/evidence tests failed'}
    & 'C:\Program Files\nodejs\node.exe' (Join-Path $project 'preintegration/tests/test_wireless_player.js')
    if($LASTEXITCODE -ne 0){throw 'MJPEG browser parser/player tests failed'}
    & $python (Join-Path $project 'preintegration/run_joint_software_evidence.py') --output (Join-Path $out 'joint_software')
    if($LASTEXITCODE -ne 0){throw 'Concurrent joint software evidence or hardware rejection gate failed'}
    & $python (Join-Path $project 'fpga/scripts/validate_board_manifest.py')
    if($LASTEXITCODE -ne 0){throw 'Board manifest schema validation failed'}
    foreach($top in @('tb_car_axil_regs','tb_car_sensors','tb_car_qei','tb_car_velocity','tb_car_qei_odometry','tb_car_qei_diagnostics','tb_car_review_regressions','tb_car_ir_batch','tb_car_risk_core','tb_car_perception_arch','tb_car_external_sensors','tb_car_axis_osd','tb_car_risk_lamps','tb_car_front_overlay','tb_car_front_numeric','tb_car_status_osd','tb_car_frame_metadata','tb_car_osd_text','tb_car_osd_fullframe','tb_car_board_video_wrapper')){
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'run_sim.ps1') -Top $top -TbFile ($top+'.sv')
        if($LASTEXITCODE -ne 0){throw "RTL failed: $top"}
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'run_sim.ps1') -Top tb_wireless_capture -TbFile tb_wireless_capture.sv
    if($LASTEXITCODE -ne 0){throw '720p wireless capture RTL failed'}
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'run_sim.ps1') -Top tb_risk_physics_sweep -TbFile tb_risk_physics_sweep.sv
    if($LASTEXITCODE -ne 0){throw 'Independent conservative physical stopping-distance sweep failed'}
    $frontRun=Get-ChildItem -LiteralPath (Join-Path $project 'fpga/build/sim_tb_car_front_overlay') -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName 'front_f5.rgb') } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if(-not $frontRun){throw 'Missing forward overlay RTL output'}
    & $python (Join-Path $project 'host/tests/compare_front_overlay.py') --rtl-dir $frontRun.FullName
    if($LASTEXITCODE -ne 0){throw 'Forward overlay independent pixel comparison failed'}
    $osdRunRoot=Join-Path $project 'fpga/build/sim_tb_car_osd_text'
    $chainRun=Get-ChildItem -LiteralPath (Join-Path $project 'fpga/build/sim_tb_car_board_video_wrapper') -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName 'display_chain_f3.rgb') } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if(-not $chainRun){throw 'Missing production historical-frame display pixel output'}
    & $python (Join-Path $project 'host/tests/compare_frame_display_chain.py') --rtl-dir $chainRun.FullName
    if($LASTEXITCODE -ne 0){throw 'Production frame metadata/OSD pixel comparison failed'}
    $statusRun=Get-ChildItem -LiteralPath (Join-Path $project 'fpga/build/sim_tb_car_status_osd') -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName 'status_f1.rgb') } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if(-not $statusRun){throw 'Missing status OSD pixel output'}
    & $python (Join-Path $project 'host/tests/compare_status_osd.py') --rtl-dir $statusRun.FullName
    if($LASTEXITCODE -ne 0){throw 'Status OSD pixel comparison failed'}
    $osdRun=Get-ChildItem -LiteralPath $osdRunRoot -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName 'osd_rtl_f1.rgb') } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if(-not $osdRun){throw 'Missing timestamped RTL OSD pixel dump'}
    $osdEvidence=Join-Path $out 'osd_compare'
    & $python (Join-Path $project 'host/tests/compare_osd.py') --rtl-dir $osdRun.FullName --out-dir $osdEvidence
    if($LASTEXITCODE -ne 0){throw 'OSD pixel comparison failed'}
    $fullRunRoot=Join-Path $project 'fpga/build/sim_tb_car_osd_fullframe'
    $fullRun=Get-ChildItem -LiteralPath $fullRunRoot -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName 'osd_rtl_640x480.rgb') } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if(-not $fullRun){throw 'Missing full-size RTL OSD pixel dump'}
    & $python (Join-Path $project 'host/tests/compare_osd_fullframe.py') `
        --rtl (Join-Path $fullRun.FullName 'osd_rtl_640x480.rgb') --out-dir $osdEvidence
    if($LASTEXITCODE -ne 0){throw 'Full-size OSD pixel comparison failed'}
    if($Synthesis){
        # Keep incidental Vivado files (for example retry_open_fs.log) inside
        # this timestamped evidence directory instead of polluting the repo root.
        Push-Location $out
        try{
            # A fresh process per top avoids cross-design synthesis state.
            # Reports belong to this run; a prior report can never satisfy it.
            $priorOocOutput=$env:PYNQ_OOC_OUT_DIR
            $synthesisIndex=Join-Path $out 'synthesis.log'
            try{
            foreach($module in @('car_axil_regs','car_sensors_top','car_qei_top','car_risk_core','car_perception_top','car_axis_osd','car_axis_front_overlay','car_axis_status_osd','car_axis_frame_metadata','car_board_video_wrapper')){
                $moduleOut=Join-Path $out ('synthesis/'+$module)
                New-Item -ItemType Directory -Path $moduleOut | Out-Null
                $env:PYNQ_OOC_OUT_DIR=$moduleOut
                $moduleLog=Join-Path $moduleOut 'synthesis.log'
                & 'C:/AMDDesignTools/2026.1/Vivado/bin/vivado.bat' -mode batch -source (Join-Path $PSScriptRoot 'synth_modules.tcl') -log $moduleLog -journal (Join-Path $moduleOut 'synthesis.jou') -tclargs $module
                if($LASTEXITCODE -ne 0){throw "Synthesis failed: $module"}
                if(-not (Select-String -Path $moduleLog -Pattern 'MODULE_SYNTHESIS_COMPLETED' -Quiet)){throw "Missing synthesis completion: $module"}
                Get-Content -LiteralPath $moduleLog | Add-Content -LiteralPath $synthesisIndex
                $report=Get-Content -LiteralPath (Join-Path $moduleOut ($module+'_timing.rpt')) -Raw
                $setup=[regex]::Match($report,'Setup\s*:[^\r\n]*Worst Slack\s+(-?[0-9.]+)ns')
                if(-not $setup.Success){throw "Missing setup timing for $module"}
                $slack=[double]::Parse($setup.Groups[1].Value,[Globalization.CultureInfo]::InvariantCulture)
                if($slack -lt 0){throw "Negative OOC setup slack: $module $slack ns"}
            }
            }finally{$env:PYNQ_OOC_OUT_DIR=$priorOocOutput}
        }finally{Pop-Location}
    }
    Write-Output 'ARCHITECTURE_SOFTWARE_RTL_PASS (not hardware acceptance)'
}finally{Stop-Transcript | Out-Null}
