param([string]$Name = '', [switch]$Wireless)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Spec = Get-Content -LiteralPath (Join-Path $Root 'fpga\registers\register_map.json') -Raw | ConvertFrom-Json
if (-not $Name) { $Name = 'v0' + $Spec.contract_version + '_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff') }
if ($Name -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$') { throw 'Name must contain only letters, digits, underscores or hyphens' }
$Build = Join-Path $Root ('fpga\build\task7_8_' + $Name)
$Output = Join-Path $Root ('lab\task7_8_lab_only_' + $Name)
$Evidence = Join-Path $PSScriptRoot ('evidence\complete_' + $Name)
foreach ($Path in @($Build,$Output,$Evidence,($Output+'.zip'))) {
    if (Test-Path -LiteralPath $Path) { throw "Fresh build refuses to overwrite existing output: $Path" }
}
$Vivado = 'C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat'
if (-not (Test-Path -LiteralPath $Vivado)) { throw 'Vivado 2026.1 is missing' }
Get-Command python -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Path $Evidence | Out-Null
$PriorBuild = $env:PYNQ_INTEGRATED_BUILD_DIR
$PriorOutput = $env:PYNQ_LAB_OUT_DIR
$PriorProfile = $env:PYNQ_VIDEO_PROFILE
$Record = [ordered]@{schema='car-complete-build/v1'; name=$Name; contract_id=$Spec.integrated_id;
    started_utc=[DateTime]::UtcNow.ToString('o'); status='RUNNING'; hardware='PENDING';
    build_dir=$Build; package_dir=$Output; evidence_dir=$Evidence; stages=@()}
function Save-Record {
    [IO.File]::WriteAllText((Join-Path $Evidence 'pipeline.json'), ($Record | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
}
function Invoke-Stage([string]$Label,[scriptblock]$Action) {
    $Stage = [ordered]@{name=$Label;started_utc=[DateTime]::UtcNow.ToString('o');status='RUNNING'}
    $Record.stages += $Stage; Save-Record
    $StageLog = Join-Path $Evidence ($Label+'.log')
    Write-Output "COMPLETE_BUILD_STAGE $Label log=$StageLog"
    # Windows PowerShell represents native stderr as ErrorRecords when
    # redirected. unittest writes successful progress to stderr; gate on the
    # child process exit code, not the existence of diagnostic text.
    $PriorErrorAction=$ErrorActionPreference
    try {
        $ErrorActionPreference='Continue'
        & $Action *> $StageLog
        $StageExit=$LASTEXITCODE
    } finally { $ErrorActionPreference=$PriorErrorAction }
    if ($StageExit -ne 0) { throw "Stage $Label failed (exit $StageExit); inspect $StageLog" }
    $Stage.status='PASS';$Stage.ended_utc=[DateTime]::UtcNow.ToString('o')
    $Stage.log_sha256=(Get-FileHash -LiteralPath $StageLog -Algorithm SHA256).Hash.ToLowerInvariant()
    Save-Record
}
try {
    $env:PYNQ_VIDEO_PROFILE = 'hdmi640'
    if ($Wireless) { $env:PYNQ_VIDEO_PROFILE = 'wireless720' }
    $Record.video_profile = $env:PYNQ_VIDEO_PROFILE
    $env:PYNQ_INTEGRATED_BUILD_DIR=$Build
    $env:PYNQ_LAB_OUT_DIR=$Output
    if ($Wireless) {
        Invoke-Stage 'wireless_native' { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'build_wireless_native.ps1') }
    }
    $FirmwareRoots = @(Get-ChildItem -LiteralPath (Split-Path $Root -Parent) -Directory | Where-Object { $_.Name -like 'stm32_pynq*' })
    if ($FirmwareRoots.Count -ne 1) { throw 'Expected one authoritative STM32 hybrid firmware' }
    Invoke-Stage 'stm32_firmware' { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $FirmwareRoots[0].FullName 'build_safe.ps1') }
    Invoke-Stage 'source_start' { & python (Join-Path $PSScriptRoot 'source_provenance.py') --capture (Join-Path $Evidence 'source_start.json') }
    Invoke-Stage 'regression' { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'fpga\scripts\run_acceptance.ps1') -Synthesis }
    Invoke-Stage 'source_after_regression' { & python (Join-Path $PSScriptRoot 'source_provenance.py') --check (Join-Path $Evidence 'source_start.json') }
    Invoke-Stage 'build' { & $Vivado -mode batch -source (Join-Path $PSScriptRoot 'vivado\rebuild_video_reliability.tcl') -log (Join-Path $Evidence 'vivado.log') -journal (Join-Path $Evidence 'vivado.jou') }
    Invoke-Stage 'package' { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'build_lab_only.ps1') -SkipRegression }
    Invoke-Stage 'source_final' { & python (Join-Path $PSScriptRoot 'source_provenance.py') --check (Join-Path $Evidence 'source_start.json') }
    $Zip=$Output+'.zip'
    $Record.zip_path=$Zip
    $Record.zip_sha256=(Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
    $Record.status='LAB_ONLY_CANDIDATE';$Record.ended_utc=[DateTime]::UtcNow.ToString('o');Save-Record
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'latest_candidate.json'),($Record|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
    Write-Output "COMPLETE_BUILD_PASS package=$Output zip=$Zip hardware=PENDING"
} catch {
    $Record.status='FAILED';$Record.error=$_.Exception.Message
    if ($Record.stages.Count -and $Record.stages[-1].status -eq 'RUNNING') {
        $Record.stages[-1].status='FAILED'
        $Record.stages[-1].ended_utc=[DateTime]::UtcNow.ToString('o')
        $Record.stages[-1].error=$Record.error
    }
    $Record.ended_utc=[DateTime]::UtcNow.ToString('o');Save-Record
    [Console]::Error.WriteLine($Record.error)
    exit 1
} finally {
    $env:PYNQ_INTEGRATED_BUILD_DIR=$PriorBuild
    $env:PYNQ_LAB_OUT_DIR=$PriorOutput
    $env:PYNQ_VIDEO_PROFILE=$PriorProfile
}
