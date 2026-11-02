param([string]$Name = 'plain_motor_20261027_r1', [ValidateSet('wireless720','wireless360','wireless720_jpeg')][string]$VideoProfile = 'wireless720', [string]$BuildBase = '')
$ErrorActionPreference='Stop'
$Variant=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if($Name -notmatch '^[A-Za-z0-9_-]+$'){throw 'Invalid build name'}
if(-not $BuildBase){$BuildBase=Join-Path $Variant 'build'}
$BuildBase=[IO.Path]::GetFullPath($BuildBase)
$Build=Join-Path $BuildBase $Name
$Output=Join-Path $BuildBase ($Name+'_artifacts')
if((Test-Path -LiteralPath $Build) -or (Test-Path -LiteralPath $Output)){throw 'Use a new immutable build name'}
New-Item -ItemType Directory -Path $Build | Out-Null
$Vivado='C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat'
if(-not(Test-Path -LiteralPath $Vivado)){throw 'Vivado 2026.1 required'}
$PriorBuild=$env:PYNQ_INTEGRATED_BUILD_DIR
$PriorOutput=$env:PYNQ_LAB_OUT_DIR
$PriorVideo=$env:PYNQ_VIDEO_PROFILE
try{
 $env:PYNQ_INTEGRATED_BUILD_DIR=$Build
 $env:PYNQ_LAB_OUT_DIR=$Output
 $env:PYNQ_VIDEO_PROFILE=$VideoProfile
 & python (Join-Path $Variant 'pynq_fpga\fpga\registers\generate_register_map.py') --check
 if($LASTEXITCODE -ne 0){throw 'Generated contract stale'}
 & $Vivado -mode batch -source (Join-Path $PSScriptRoot 'build_fpga.tcl') -log (Join-Path $Build 'vivado.log') -journal (Join-Path $Build 'vivado.jou') *> (Join-Path $Build 'build_console.log')
 if($LASTEXITCODE -ne 0){throw "FPGA build failed; inspect $Build\build_console.log"}
 Write-Output "PLAIN_MOTOR_FPGA_PASS artifacts=$Output"
}finally{
 $env:PYNQ_INTEGRATED_BUILD_DIR=$PriorBuild
 $env:PYNQ_LAB_OUT_DIR=$PriorOutput
 $env:PYNQ_VIDEO_PROFILE=$PriorVideo
}
