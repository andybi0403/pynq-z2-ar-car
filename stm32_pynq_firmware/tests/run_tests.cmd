@echo off
setlocal
cd /d "%~dp0"
if not exist out mkdir out
rem Compile ARM before vcvars changes the PowerShell module environment.
call powershell -NoProfile -ExecutionPolicy Bypass -File ..\build_safe.ps1 >out\arm_build.log 2>&1
if errorlevel 1 (
  type out\arm_build.log
  exit /b 1
)
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not exist out mkdir out
rem Disable MSVC warning 4819 caused by UTF-8 learning comments.
cl /nologo /W4 /wd4819 /WX /TC test_safe_control.c ..\Source\APP\safe_control.c /Foout\ /Feout\test_safe_control.exe
if errorlevel 1 exit /b 1
out\test_safe_control.exe
if errorlevel 1 exit /b 1
cl /nologo /W4 /wd4819 /WX /TC test_hybrid_protocol.c ..\Source\APP\safe_control.c ..\Source\APP\hybrid_protocol.c /Foout\ /Feout\test_hybrid_protocol.exe
if errorlevel 1 exit /b 1
out\test_hybrid_protocol.exe
if errorlevel 1 exit /b 1
python test_uart_roles_arm.py
exit /b %errorlevel%
