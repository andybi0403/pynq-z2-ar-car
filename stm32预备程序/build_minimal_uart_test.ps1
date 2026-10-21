# 构建最小串口诊断固件；不修改原 safe_car 的构建产物。
param([string]$CompilerBin = "")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not $CompilerBin) {
    $gcc = Get-ChildItem -Path 'C:\ST\STM32CubeIDE_*\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32*\tools\bin\arm-none-eabi-gcc.exe' |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $gcc) { throw "CubeIDE ARM GCC not found. Set -CompilerBin." }
    $CompilerBin = Split-Path -Parent $gcc.FullName
}
$out = 'build_minimal_uart_test'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$common = @('-mcpu=cortex-m3','-mthumb','-Os','-g3','-std=gnu11',
    '-ffunction-sections','-fdata-sections','-DSTM32F10X_MD',
    '-DHSE_VALUE=8000000','-ISource/CMSIS','-ISource/FWlib/inc')
$sources = @('minimal_uart_test.c','safe_startup.c','Source/CMSIS/system_stm32f10x.c')
$objects = @()
foreach ($source in $sources) {
    $obj = $out + '/' + [IO.Path]::GetFileNameWithoutExtension($source) + '.o'
    $extra = @('-Wall','-Wextra')
    if ($source -eq 'minimal_uart_test.c') { $extra += '-Werror' }
    & "$CompilerBin/arm-none-eabi-gcc.exe" @common @extra '-c' $source '-o' $obj
    if ($LASTEXITCODE -ne 0) { throw "Compile failed: $source" }
    $objects += $obj
}
& "$CompilerBin/arm-none-eabi-gcc.exe" -mcpu=cortex-m3 -mthumb -nostartfiles --specs=nano.specs --specs=nosys.specs -T safe_stm32f103c8.ld "-Wl,--gc-sections,-Map=$out/minimal_uart_test.map" @objects -o "$out/minimal_uart_test.elf"
if ($LASTEXITCODE -ne 0) { throw 'Link failed' }
& "$CompilerBin/arm-none-eabi-objcopy.exe" -O ihex "$out/minimal_uart_test.elf" "$out/minimal_uart_test.hex"
if ($LASTEXITCODE -ne 0) { throw 'HEX conversion failed' }
& "$CompilerBin/arm-none-eabi-objcopy.exe" -O binary "$out/minimal_uart_test.elf" "$out/minimal_uart_test.bin"
if ($LASTEXITCODE -ne 0) { throw 'BIN conversion failed' }
& "$CompilerBin/arm-none-eabi-size.exe" "$out/minimal_uart_test.elf"
if ($LASTEXITCODE -ne 0) { throw 'size failed' }
Get-FileHash -Algorithm SHA256 "$out/minimal_uart_test.hex","$out/minimal_uart_test.bin"
