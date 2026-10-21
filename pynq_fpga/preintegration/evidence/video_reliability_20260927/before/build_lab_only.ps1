param(
    [switch]$SkipRegression,
    [switch]$ReuseBitstream
)
$ErrorActionPreference = 'Stop'
$PreDir = $PSScriptRoot
$Root = (Resolve-Path (Join-Path $PreDir '..')).Path
$RepoRoot = (Resolve-Path (Join-Path $Root '..')).Path
$OutDir = Join-Path $Root 'lab\task7_8_lab_only_20260919'
$ZipPath = Join-Path $Root 'lab\task7_8_lab_only_20260919.zip'
$Python = 'python'
$Vivado = 'C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat'
$LinkCandidates = @(Get-ChildItem -LiteralPath $RepoRoot -Recurse -File -Filter 'pynq_link.py' |
    Where-Object { $_.FullName -match '[\\/]pc[\\/]pynq_link\.py$' })
if ($LinkCandidates.Count -ne 1) {
    throw "Expected exactly one authoritative pc/pynq_link.py, found $($LinkCandidates.Count)"
}
$PynqLinkSource = $LinkCandidates[0].FullName

if (-not (Test-Path -LiteralPath $Vivado)) { throw "Vivado not found: $Vivado" }

& $Python (Join-Path $Root 'fpga\scripts\validate_board_manifest.py')
if ($LASTEXITCODE -ne 0) { throw 'Board manifest structural validation failed' }

# A lab artifact must never silently become a release artifact.
& $Python (Join-Path $Root 'fpga\scripts\validate_board_manifest.py') --release
if ($LASTEXITCODE -eq 0) { throw 'Release gate is open; LAB_ONLY packaging refuses to continue' }
Write-Output 'LAB_ONLY_RELEASE_GATE_CONFIRMED_BLOCKED'

if (-not $SkipRegression) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'fpga\scripts\run_sim.ps1') -Top tb_car_board_video_wrapper -TbFile tb_car_board_video_wrapper.sv
    if ($LASTEXITCODE -ne 0) { throw 'Production board/video wrapper regression failed' }
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$ResolvedLabRoot = (Resolve-Path (Join-Path $Root 'lab')).Path
$ResolvedOutDir = (Resolve-Path $OutDir).Path
if (-not $ResolvedOutDir.StartsWith($ResolvedLabRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unexpected LAB_ONLY output path: $ResolvedOutDir"
}
# Keep the transfer folder deterministic when this script is rerun.
Get-ChildItem -LiteralPath $OutDir -File |
    Where-Object { $_.Name -match '^write_bitstream.*\.(log|jou)$|^vivado_bitgen\.log$' } |
    Remove-Item -Force
$BuildLogDir = Join-Path $Root 'fpga\build\task7_8_integrated'
$Log = Join-Path $BuildLogDir 'lab_bitstream.log'
$Journal = Join-Path $BuildLogDir 'lab_bitstream.jou'
$Bit = Join-Path $OutDir 'task7_8_LAB_ONLY.bit'
$Hwh = Join-Path $OutDir 'task7_8_LAB_ONLY.hwh'
if (-not $ReuseBitstream) {
    & $Vivado -mode batch -source (Join-Path $PreDir 'vivado\write_lab_only_bitstream.tcl') -log $Log -journal $Journal
    if ($LASTEXITCODE -ne 0) { throw 'Vivado LAB_ONLY bitstream generation failed' }
    Copy-Item -LiteralPath $Log -Destination (Join-Path $OutDir 'vivado_bitgen.log') -Force
} else {
    Write-Output 'LAB_ONLY_REUSING_EXISTING_BITSTREAM'
    if (Test-Path -LiteralPath $Log) {
        Copy-Item -LiteralPath $Log -Destination (Join-Path $OutDir 'vivado_bitgen.log') -Force
    }
}
foreach ($Path in @($Bit,$Hwh)) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Missing LAB_ONLY artifact: $Path" }
    if ((Get-Item -LiteralPath $Path).Length -le 0) { throw "Empty LAB_ONLY artifact: $Path" }
}
& $Python (Join-Path $PreDir 'host\hwh_contract.py') --hwh $Hwh --integrated
if ($LASTEXITCODE -ne 0) { throw 'LAB_ONLY HWH production contract failed' }

$Support = @(
    @{ Source=(Join-Path $PreDir 'host\lab_acceptance.py'); Name='lab_acceptance.py' },
    @{ Source=(Join-Path $PreDir 'host\board_runtime.py'); Name='board_runtime.py' },
    @{ Source=(Join-Path $PreDir 'host\frame_pipeline.py'); Name='frame_pipeline.py' },
    @{ Source=(Join-Path $PreDir 'host\hwh_contract.py'); Name='hwh_contract.py' },
    @{ Source=(Join-Path $Root 'host\perception_client.py'); Name='perception_client.py' },
    @{ Source=(Join-Path $Root 'host\qei_calibration.py'); Name='qei_calibration.py' },
    @{ Source=(Join-Path $Root 'host\perception_replay.py'); Name='perception_replay.py' },
    @{ Source=(Join-Path $Root 'host\car_regs.py'); Name='car_regs.py' },
    @{ Source=$PynqLinkSource; Name='pynq_link.py' },
    @{ Source=(Join-Path $PreDir 'LAB_ONLY_README.md'); Name='README.md' }
)
foreach ($Item in $Support) {
    if (-not (Test-Path -LiteralPath $Item.Source)) { throw "Missing LAB_ONLY support source: $($Item.Source)" }
    Copy-Item -LiteralPath $Item.Source -Destination (Join-Path $OutDir $Item.Name) -Force
}

$Timing = Get-Content -LiteralPath (Join-Path $OutDir 'timing_LAB_ONLY.rpt') -Raw
$Match = [regex]::Match($Timing, '(?m)^\s*([0-9.-]+)\s+([0-9.-]+)\s+\d+\s+\d+\s+([0-9.-]+)\s+([0-9.-]+)')
if (-not $Match.Success) { throw 'Could not parse LAB_ONLY timing report' }
$Wns = [double]$Match.Groups[1].Value
$Tns = [double]$Match.Groups[2].Value
$Whs = [double]$Match.Groups[3].Value
$Ths = [double]$Match.Groups[4].Value
if ($Wns -lt 0 -or $Whs -lt 0) { throw "LAB_ONLY timing failed WNS=$Wns WHS=$Whs" }

$Manifest = [ordered]@{
    schema = 'car-lab-artifact/v1'
    name = 'task7_8_LAB_ONLY'
    generated_at = (Get-Date).ToString('o')
    classification = 'LAB_ONLY_NO_MOTOR_NON_RELEASE'
    board = 'PYNQ-Z2'
    part = 'xc7z020clg400-1'
    integrated_id = '0xC4251006'
    source_project = 'pynq_fpga/fpga/build/task7_8_integrated/task7_8_integrated.xpr'
    artifacts = [ordered]@{
        bit = [ordered]@{ file='task7_8_LAB_ONLY.bit'; bytes=(Get-Item $Bit).Length; sha256=(Get-FileHash -Algorithm SHA256 $Bit).Hash.ToLowerInvariant() }
        hwh = [ordered]@{ file='task7_8_LAB_ONLY.hwh'; bytes=(Get-Item $Hwh).Length; sha256=(Get-FileHash -Algorithm SHA256 $Hwh).Hash.ToLowerInvariant() }
    }
    contracts = [ordered]@{
        hwh = 'PASS_PRODUCTION_NO_PLACEHOLDER'
        release_gate = 'BLOCKED_EXPECTED'
        motor_output_allowed = $false
        serial_motion_allowed = $false
    }
    timing = [ordered]@{ wns_ns=$Wns; tns_ns=$Tns; whs_ns=$Whs; ths_ns=$Ths }
    physical_validation = [ordered]@{
        pynq_overlay_loaded = $false
        mmio = $false
        sensors = $false
        uart_stop = $false
        c270 = $false
        hdmi = $false
    }
}
$ManifestJson = $Manifest | ConvertTo-Json -Depth 8
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $OutDir 'lab_manifest.json'), $ManifestJson + [Environment]::NewLine, $Utf8NoBom)
& $Python (Join-Path $OutDir 'lab_acceptance.py') contract
if ($LASTEXITCODE -ne 0) { throw 'Packaged LAB_ONLY contract self-test failed' }
$CacheDir = Join-Path $OutDir '__pycache__'
if (Test-Path -LiteralPath $CacheDir) {
    $ResolvedOut = (Resolve-Path -LiteralPath $OutDir).Path.TrimEnd([IO.Path]::DirectorySeparatorChar)
    $ResolvedCache = (Resolve-Path -LiteralPath $CacheDir).Path
    if (-not $ResolvedCache.StartsWith($ResolvedOut + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove cache outside LAB_ONLY directory: $ResolvedCache"
    }
    Remove-Item -LiteralPath $ResolvedCache -Recurse -Force
}
Compress-Archive -Path (Join-Path $OutDir '*') -DestinationPath $ZipPath -CompressionLevel Optimal -Force
$ZipHash = (Get-FileHash -Algorithm SHA256 $ZipPath).Hash.ToLowerInvariant()
"$ZipHash  $(Split-Path -Leaf $ZipPath)" | Set-Content -LiteralPath ($ZipPath + '.sha256.txt') -Encoding ascii
Write-Output "TASK7_8_LAB_ONLY_PACKAGE_PASS $OutDir"
Write-Output "TASK7_8_LAB_ONLY_ZIP=$ZipPath"
Write-Output "TASK7_8_LAB_ONLY_ZIP_SHA256=$ZipHash"
