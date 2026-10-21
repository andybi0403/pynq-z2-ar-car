# build_car_c_dll.ps1 -- build the real STM32 safe_control.c into a host DLL.
# Production source is copied byte-identical (SHA256 verified and logged) to an
# ASCII path because cmd.exe mangles CJK paths in compiler arguments.
# Exports mirror production safe_control.h exactly (7 functions).
# Exit code: 0=OK, non-zero=FAIL.
$ErrorActionPreference = "Stop"
$OutDir = $PSScriptRoot

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
# Night A mainline is the PYNQ-integrated firmware. Do not select the first
# recursive match: the demo and integrated variants deliberately parse
# different $P frame layouts.
$FirmwareRoots = @(Get-ChildItem -LiteralPath $Root -Directory |
    Where-Object { $_.Name -like "stm32_pynq*" })
if ($FirmwareRoots.Count -ne 1) {
    Write-Output "ERROR: expected exactly one stm32_pynq* production directory, found $($FirmwareRoots.Count)"
    exit 2
}
$SrcPath = Join-Path $FirmwareRoots[0].FullName "Source\APP\safe_control.c"
$HeaderPath = Join-Path $FirmwareRoots[0].FullName "Source\APP\safe_control.h"
if (-not (Test-Path -LiteralPath $SrcPath)) {
    Write-Output "ERROR: integrated production safe_control.c not found: $SrcPath"
    exit 2
}
if (-not (Test-Path -LiteralPath $HeaderPath)) {
    Write-Output "ERROR: integrated production safe_control.h not found: $HeaderPath"
    exit 2
}
$SrcFile = Get-Item -LiteralPath $SrcPath

$VCVarseq = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path $VCVarseq)) {
    Write-Output "ERROR: MSVC vcvars64.bat not found"
    exit 2
}

# Byte-identical copy with SHA256 proof
$SrcCopy = Join-Path $OutDir "safe_control_prod.c"
Copy-Item $SrcFile.FullName $SrcCopy -Force
$SrcSha = (Get-FileHash $SrcFile.FullName -Algorithm SHA256).Hash
$CopySha = (Get-FileHash $SrcCopy -Algorithm SHA256).Hash
if ($SrcSha -ne $CopySha) {
    Write-Output "ERROR: source copy SHA mismatch"
    exit 3
}
Copy-Item -LiteralPath $HeaderPath -Destination (Join-Path $OutDir "safe_control.h") -Force
Write-Output "Source path: $($SrcFile.FullName)"
Write-Output "Source SHA256: $SrcSha"

$HybridCopy = Join-Path $OutDir 'hybrid_protocol_prod.c'
$HybridSource = Join-Path $FirmwareRoots[0].FullName 'Source\APP\hybrid_protocol.c'
Copy-Item -LiteralPath $HybridSource -Destination $HybridCopy -Force
Copy-Item -LiteralPath (Join-Path $FirmwareRoots[0].FullName 'Source\APP\hybrid_protocol.h') -Destination (Join-Path $OutDir 'hybrid_protocol.h') -Force
# Export list includes both authoritative safety/protocol headers
$Exports = "safe_init safe_tick safe_fault safe_source_handover safe_frame safe_pframe safe_outputs hybrid_receive hybrid_report hybrid_crc16 safe_local_sample"
$ExpArgs = ($Exports.Split(" ") | ForEach-Object { "/EXPORT:$_" }) -join " "

# Build via a bat file (single cl line, no continuation characters)
$DllPath = Join-Path $OutDir "safe_control.dll"
$ObjDir = Join-Path $OutDir "obj"
New-Item -ItemType Directory -Force -Path $ObjDir | Out-Null
$clLine = "cl /nologo /W4 /wd4819 /WX /TC /LD /O2 `"$SrcCopy`" `"$HybridCopy`" /Fe`"$DllPath`" /Fo$ObjDir\ /link $ExpArgs"
$CmdFile = Join-Path $OutDir "build_cmd.bat"
Set-Content -Path $CmdFile -Value "@echo off`r`ncall `"$VCVarseq`" >nul`r`n$clLine`r`nif errorlevel 1 exit /b 1`r`n" -Encoding ASCII

cmd /c $CmdFile *> (Join-Path $OutDir "build.log")
$code = $LASTEXITCODE
Get-Content (Join-Path $OutDir "build.log") | ForEach-Object { Write-Output $_ }
if ($code -ne 0 -or -not (Test-Path $DllPath)) {
    Write-Output "FAIL: safe_control.dll build (exit $code)"
    exit $code
}
Write-Output "OK: safe_control.dll built"
$Identity = [ordered]@{
    schema='car-production-c-build/v1'
    source=$SrcFile.FullName
    source_sha256=$SrcSha.ToLowerInvariant()
    header=$HeaderPath
    header_sha256=(Get-FileHash -Algorithm SHA256 $HeaderPath).Hash.ToLowerInvariant()
    dll_sha256=(Get-FileHash -Algorithm SHA256 $DllPath).Hash.ToLowerInvariant()
    compiler_command=$clLine
}
[IO.File]::WriteAllText((Join-Path $OutDir 'build_identity.json'), ($Identity | ConvertTo-Json -Depth 4), (New-Object System.Text.UTF8Encoding($false)))
exit 0
