param([switch]$Vivado,[switch]$Synthesis,[switch]$Implementation,[switch]$RequireAEBlocked)
$ErrorActionPreference='Stop'
$PreDir=$PSScriptRoot
$Root=[IO.Path]::GetFullPath((Join-Path $PreDir '..'))
$Workspace=Split-Path $Root -Parent
$Python=Join-Path $env:LOCALAPPDATA 'Programs/Python/Python314/python.exe'
if(-not (Test-Path $Python)){$Python='python'}
$VivadoExe='C:/AMDDesignTools/2026.1/Vivado/bin/vivado.bat'
$Stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$LogDir=Join-Path $Root ('fpga/build/task7_8_tests/'+$Stamp)
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

& $Python -m unittest discover -s (Join-Path $PreDir 'tests') -p 'test_*.py'
if($LASTEXITCODE -ne 0){throw 'Preintegration Python tests failed'}

foreach($case in @(
 @{Top='tb_axis32_to_rgb24';Rtl='axis32_to_rgb24.v';Tb='tb_axis32_to_rgb24.sv'},
 @{Top='tb_axi_control_slot_stub';Rtl='axi_control_slot_stub.v';Tb='tb_axi_control_slot_stub.sv'}
)){
 $SimDir=Join-Path $LogDir $case.Top
 New-Item -ItemType Directory -Force -Path $SimDir | Out-Null
 Push-Location $SimDir
 try{
  & 'C:/AMDDesignTools/2026.1/Vivado/bin/xvlog.bat' -sv (Join-Path $PreDir ('rtl/'+$case.Rtl)) (Join-Path $PreDir ('tb/'+$case.Tb))
  if($LASTEXITCODE -ne 0){throw ($case.Top+' compile failed')}
  & 'C:/AMDDesignTools/2026.1/Vivado/bin/xelab.bat' $case.Top -s ($case.Top+'_sim')
  if($LASTEXITCODE -ne 0){throw ($case.Top+' elaboration failed')}
  & 'C:/AMDDesignTools/2026.1/Vivado/bin/xsim.bat' ($case.Top+'_sim') -runall --log xsim_console.log
  if($LASTEXITCODE -ne 0){throw ($case.Top+' simulation failed')}
  $Console=Get-Content -LiteralPath 'xsim_console.log' -Raw
  if($Console -notmatch 'TEST PASSED' -or $Console -match 'TEST FAILED|\[FAIL\]'){throw ($case.Top+' self-check failed')}
 }finally{Pop-Location}
}

& $Python (Join-Path $PreDir 'host/check_ae_gate.py') (Join-Path $Root 'nightly')
$GateOpen=($LASTEXITCODE -eq 0)
if($RequireAEBlocked -and $GateOpen){throw 'A-E release gate unexpectedly open while hardware evidence is incomplete'}
if($GateOpen){Write-Output 'AE_GATE_STATE=PASS_READY_FOR_RELEASE_REVIEW'}else{Write-Output 'AE_GATE_STATE=BLOCKED'}

if($Vivado){
 Push-Location $LogDir
 try{
  & $VivadoExe -mode batch -source (Join-Path $PreDir 'vivado/create_framework.tcl') -log (Join-Path $LogDir 'create.log') -journal (Join-Path $LogDir 'create.jou')
  if($LASTEXITCODE -ne 0){throw 'Vivado framework creation failed'}
  & $VivadoExe -mode batch -source (Join-Path $PreDir 'vivado/check_framework.tcl') -log (Join-Path $LogDir 'check.log') -journal (Join-Path $LogDir 'check.jou')
  if($LASTEXITCODE -ne 0){throw 'Vivado framework check failed'}
  $Hwh=Join-Path $Root 'fpga/build/task7_8_preintegration/task7_8_preintegration.gen/sources_1/bd/preintegration_bd/hw_handoff/preintegration_bd.hwh'
  & $Python (Join-Path $PreDir 'host/hwh_contract.py') --hwh $Hwh
  if($LASTEXITCODE -ne 0){throw 'Generated HWH contract audit failed'}
 }finally{Pop-Location}
}
if($Synthesis){
 if(-not $Vivado){throw '-Synthesis requires -Vivado'}
 Push-Location $LogDir
 try{
  & $VivadoExe -mode batch -source (Join-Path $PreDir 'vivado/synth_framework.tcl') -log (Join-Path $LogDir 'synth.log') -journal (Join-Path $LogDir 'synth.jou')
  if($LASTEXITCODE -ne 0){throw 'Vivado framework synthesis failed'}
  $BadClock=Select-String -LiteralPath (Join-Path $LogDir 'synth.log') -Pattern 'Timing 38-249|Designutils 20-1307|Common 17-55' -Quiet
  if($BadClock){throw 'Vivado synthesis contains the known disconnected/unsupported clock constraint'}
 }finally{Pop-Location}
}
if($Implementation){
 if(-not $Synthesis){throw '-Implementation requires -Synthesis and -Vivado'}
 Push-Location $LogDir
 try{
  & $VivadoExe -mode batch -source (Join-Path $PreDir 'vivado/impl_framework.tcl') -log (Join-Path $LogDir 'impl.log') -journal (Join-Path $LogDir 'impl.jou')
  if($LASTEXITCODE -ne 0){throw 'Vivado framework implementation failed'}
  $BadClock=Select-String -LiteralPath (Join-Path $LogDir 'impl.log') -Pattern 'Timing 38-249|Designutils 20-1307|Common 17-55' -Quiet
  if($BadClock){throw 'Vivado implementation contains the known disconnected/unsupported clock constraint'}
 }finally{Pop-Location}
}
Write-Output "TASK7_8_PREINTEGRATION_PASS (production integration is separate; release and physical board/HDMI remain gated)"
Write-Output "LOG_DIR=$LogDir"
