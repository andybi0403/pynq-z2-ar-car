$ErrorActionPreference='Stop'
$Root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Cmake='C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
if (-not (Test-Path -LiteralPath $Cmake)) { $Cmake=(Get-Command cmake -ErrorAction Stop).Source }
$Build=Join-Path $Root 'fpga\build\wireless_native_host_v2'
$Archive=Join-Path $Root 'fpga\build\native_dependencies\libjpeg-turbo-3.1.2.tar.gz'
$ArgsList=@('-S',(Join-Path $PSScriptRoot 'native'),'-B',$Build,'-A','x64')
if (Test-Path -LiteralPath $Archive) { $ArgsList+=('-DWV_TURBO_ARCHIVE='+$Archive.Replace('\','/')) }
& $Cmake @ArgsList
if($LASTEXITCODE -ne 0){throw 'Native codec configure failed'}
& $Cmake --build $Build --config Release --target car_video --parallel 4
if($LASTEXITCODE -ne 0){throw 'Native codec build failed'}
Write-Output 'WIRELESS_HOST_CODEC_BUILD_PASS (not ARM/V4L2 performance evidence)'
