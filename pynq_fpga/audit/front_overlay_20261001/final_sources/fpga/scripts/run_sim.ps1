# run_sim.ps1 -- XSim simulation entry (task2/task3 shared)
# Usage: powershell -ExecutionPolicy Bypass -File run_sim.ps1 -Top tb_car_axil_regs -TbFile tb_car_axil_regs.sv
#        powershell -ExecutionPolicy Bypass -File run_sim.ps1 -Top tb_car_sensors -TbFile tb_car_sensors.sv
# Exit code: 0=PASS, non-zero=FAIL (compile/elaborate/run/assert)
param(
    [string]$WorkDir = "",
    [string]$Top = "tb_car_axil_regs",
    [string]$TbFile = "tb_car_axil_regs.sv"
)
if ($WorkDir -eq "") { $WorkDir = "$PSScriptRoot\..\build\sim_$Top" }

$ErrorActionPreference = "Stop"

# Locate Vivado XSim tools
$VivadoBin = "C:\AMDDesignTools\2026.1\Vivado\bin"
if (-not (Test-Path "$VivadoBin\xvlog.bat")) {
    Write-Output "ERROR: xvlog.bat not found under $VivadoBin"
    exit 2
}

$Root = Resolve-Path "$PSScriptRoot\..\.."        # pynq_fpga project root
$RtlDir = Join-Path $Root "fpga\rtl"
$TbDir  = Join-Path $Root "fpga\tb"
$ThirdAxil = Join-Path $Root "third_party\verilog-axi\rtl"

$SrcRtl = @(
    (Join-Path $ThirdAxil "axil_reg_if.v"),
    (Join-Path $ThirdAxil "axil_reg_if_rd.v"),
    (Join-Path $ThirdAxil "axil_reg_if_wr.v"),
    (Join-Path $RtlDir "car_time_counter.v"),
    (Join-Path $RtlDir "car_snapshot.v"),
    (Join-Path $RtlDir "car_axil_regs.v"),
    (Join-Path $RtlDir "car_ultrasonic.v"),
    (Join-Path $RtlDir "car_ir.v"),
    (Join-Path $RtlDir "car_sensors_core.v"),
    (Join-Path $RtlDir "car_sensors_top.v"),
    (Join-Path $RtlDir "car_qei.v"),
    (Join-Path $RtlDir "car_qei_velocity.v"),
    (Join-Path $RtlDir "car_qei_odometry.v"),
    (Join-Path $RtlDir "car_qei_core.v"),
    (Join-Path $RtlDir "car_qei_top.v"),
    (Join-Path $RtlDir "car_risk_core.v"),
    (Join-Path $RtlDir "car_perception_top.v"),
    (Join-Path $RtlDir "car_axis_osd.v"),
    (Join-Path $RtlDir "car_axis_front_overlay.v"),
    (Join-Path $RtlDir "car_axis_status_osd.v"),
    (Join-Path $RtlDir "car_axis_frame_metadata.v"),
    (Join-Path $RtlDir "car_board_video_wrapper.v")
)
$SrcTb = Join-Path $TbDir $TbFile

foreach ($f in ($SrcRtl + @($SrcTb))) {
    if (-not (Test-Path $f)) {
        Write-Output "ERROR: missing source $f"
        exit 2
    }
}

$BuildRoot = [IO.Path]::GetFullPath((Join-Path $Root 'fpga\build'))
$WorkDir = [IO.Path]::GetFullPath($WorkDir)
if (-not $WorkDir.StartsWith($BuildRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Simulation output must be a child of pynq_fpga/fpga/build'
}
$WorkDir = Join-Path $WorkDir (Get-Date -Format 'yyyyMMdd_HHmmss_fff')
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
Copy-Item -LiteralPath (Join-Path $RtlDir 'font_8x8_minimal.mem') -Destination $WorkDir -Force
Copy-Item -LiteralPath (Join-Path $RtlDir 'font_8x8_status.mem') -Destination $WorkDir -Force
Set-Location $WorkDir

$LogFile = Join-Path $WorkDir "sim_run.log"

function Run-Step($exe, $exeArgs, $stepName) {
    # Redirect to a step-unique file: xvlog/xelab/xsim each open their own
    # default <tool>.log in the working directory, so sharing that name with
    # the PowerShell redirection handle makes the tool fail to open its log.
    $StepLog = Join-Path $WorkDir (($stepName -replace '\s+', '_') + ".psout")
    & "$VivadoBin\$exe" @exeArgs *> $StepLog
    $code = $LASTEXITCODE
    Get-Content $StepLog | Add-Content $LogFile
    if ($code -ne 0) {
        Write-Output "FAIL: $stepName (exit $code), log: $StepLog"
        exit $code
    }
}

# 1. Compile RTL + TB
Run-Step "xvlog.bat" (@("-sv", "-i", $RtlDir) + $SrcRtl + @($SrcTb)) "xvlog compile"

# 2. Elaborate
Run-Step "xelab.bat" @($Top, "-debug", "typical", "-s", ($Top + "_sim")) "xelab elaborate"

# 3. Run simulation
Run-Step "xsim.bat" @(($Top + "_sim"), "-runall", "--log", "xsim_console.log") "xsim run"

Get-Content (Join-Path $WorkDir "xsim_console.log") | Add-Content $LogFile

# 4. Verdict from assertions (not waveform screenshots)
$console = Get-Content (Join-Path $WorkDir "xsim_console.log") -Raw
if ($console -match 'TEST FAILED|\[FAIL\]|Fatal:|FATAL|ERROR:') {
    Write-Output "FAIL: diagnostic found; LOG: $LogFile"
    exit 1
} elseif ($console -match "TEST PASSED") {
    $passed = ([regex]::Match($console, "TEST PASSED \((\d+) checks\)")).Groups[1].Value
    Write-Output "PASS: $Top simulation ($passed checks)"
    Write-Output "LOG: $LogFile"
    exit 0
} elseif ($console -match "TEST FAILED") {
    Write-Output "FAIL: assertion failures"
    Write-Output "LOG: $LogFile"
    exit 1
} else {
    Write-Output "FAIL: no verdict line in console (watchdog/hang?)"
    Write-Output "LOG: $LogFile"
    exit 3
}
