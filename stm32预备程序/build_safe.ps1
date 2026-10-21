# 这是一个可重复执行的命令行构建脚本：不依赖 CubeIDE 当前打开的界面。
# 它使用 ARM GCC 编译 STM32F103 的 C 源文件，再链接成 ELF，并转换为
# 可烧录的 HEX/BIN 文件。修改源码后重新运行本脚本即可检查是否能构建。
param([string]$CompilerBin = "")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not $CompilerBin) {
    $gcc = Get-ChildItem -Path 'C:\ST\STM32CubeIDE_*\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32*\tools\bin\arm-none-eabi-gcc.exe' |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $gcc) { throw "CubeIDE ARM GCC not found. Set -CompilerBin." }
    $CompilerBin = Split-Path -Parent $gcc.FullName
}
New-Item -ItemType Directory -Force -Path 'build_safe' | Out-Null
$common = @('-mcpu=cortex-m3','-mthumb','-Os','-g3','-std=gnu11',
    '-ffunction-sections','-fdata-sections','-DSTM32F10X_MD',
    '-DUSE_STDPERIPH_DRIVER','-DHSE_VALUE=8000000',
    '-ISource/CMSIS','-ISource/FWlib/inc','-ISource/APP','-ISource/BSP')
$sources = @('Source/APP/main.c','Source/APP/safe_car.c','Source/APP/safe_control.c',
    'safe_startup.c','Source/CMSIS/system_stm32f10x.c',
    'Source/FWlib/src/stm32f10x_gpio.c','Source/FWlib/src/stm32f10x_rcc.c',
    'Source/FWlib/src/stm32f10x_tim.c','Source/FWlib/src/stm32f10x_usart.c',
    'Source/FWlib/src/stm32f10x_exti.c','Source/FWlib/src/misc.c')
$objects = @()
foreach ($source in $sources) {
    $obj = 'build_safe/' + [IO.Path]::GetFileNameWithoutExtension($source) + '.o'
    $extra = @()
    if ($source -match 'safe_car|safe_control|main.c') { $extra=@('-Wall','-Wextra','-Werror') }
    & "$CompilerBin/arm-none-eabi-gcc.exe" @common @extra -c $source -o $obj
    if ($LASTEXITCODE -ne 0) { throw "Compile failed: $source" }
    $objects += $obj
}
& "$CompilerBin/arm-none-eabi-gcc.exe" -mcpu=cortex-m3 -mthumb -nostartfiles --specs=nano.specs --specs=nosys.specs -T safe_stm32f103c8.ld "-Wl,--gc-sections,-Map=build_safe/safe_car.map" @objects -o build_safe/safe_car.elf
if ($LASTEXITCODE -ne 0) { throw 'Link failed' }
foreach ($fmt in @(@('ihex','hex'),@('binary','bin'))) {
    & "$CompilerBin/arm-none-eabi-objcopy.exe" -O $fmt[0] build_safe/safe_car.elf ("build_safe/safe_car."+$fmt[1])
    if ($LASTEXITCODE -ne 0) { throw 'objcopy failed' }
}
& "$CompilerBin/arm-none-eabi-size.exe" build_safe/safe_car.elf
if ($LASTEXITCODE -ne 0) { throw 'size failed' }
Get-FileHash -Algorithm SHA256 build_safe/safe_car.hex,build_safe/safe_car.bin
