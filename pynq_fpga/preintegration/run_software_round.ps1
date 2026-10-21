param([int]$Round)
$ErrorActionPreference='Stop'
if($Round -lt 1 -or $Round -gt 5){throw 'Round must be 1..5'}
$Project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Workspace=Split-Path $Project -Parent
$Evidence=Join-Path $Project ('audit\wireless_five_rounds_20261004\round'+$Round+'_evidence')
New-Item -ItemType Directory -Path $Evidence -Force | Out-Null
Start-Transcript -Path (Join-Path $Evidence 'software.log') | Out-Null
try {
    $Firmwares=@(Get-ChildItem -LiteralPath $Workspace -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'tests\run_tests.cmd') })
    if($Firmwares.Count -ne 2){throw 'Expected exactly two canonical firmware projects'}
    foreach($Folder in $Firmwares) {
        & (Join-Path $Folder.FullName 'tests\run_tests.cmd')
        if($LASTEXITCODE -ne 0){throw 'STM32 C regression failed'}
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Project 'host\c_build\build_car_c_dll.ps1')
    if($LASTEXITCODE -ne 0){throw 'Production C DLL build failed'}
    $Pc=@($Firmwares | Where-Object { Test-Path (Join-Path $_.FullName 'pc\test_pynq_link.py') })
    if($Pc.Count -ne 1){throw 'Expected one canonical PC link test directory'}
    Push-Location (Join-Path $Pc[0].FullName 'pc')
    try { & python -m unittest test_pynq_link test_console; if($LASTEXITCODE -ne 0){throw 'CarLink tests failed'} }
    finally { Pop-Location }
    foreach($Folder in @('host\tests','preintegration\tests')) {
        & python -m unittest discover -s (Join-Path $Project $Folder) -p 'test_*.py'
        if($LASTEXITCODE -ne 0){throw 'Python round regression failed'}
    }
    & python (Join-Path $PSScriptRoot 'run_supervisor_fault_matrix.py') --output (Join-Path $Evidence 'supervisor_fault_matrix')
    if($LASTEXITCODE -ne 0){throw 'Production C fault matrix failed'}
    & 'C:\Program Files\nodejs\node.exe' (Join-Path $PSScriptRoot 'tests\test_wireless_player.js')
    if($LASTEXITCODE -ne 0){throw 'Browser player regressions failed'}
    Write-Output ('ROUND_'+$Round+'_SOFTWARE_PASS; hardware=PENDING')
} finally { Stop-Transcript | Out-Null }
