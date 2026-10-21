param([string]$Name='')
# Compatibility entry: all new builds use the complete fresh-directory pipeline.
$ErrorActionPreference='Stop'
& (Join-Path $PSScriptRoot 'build_complete.ps1') -Name $Name
