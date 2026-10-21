@echo off
setlocal
cd /d "%~dp0"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not exist out mkdir out
rem Disable MSVC warning 4819 caused by UTF-8 learning comments.
cl /nologo /W4 /wd4819 /WX /TC test_safe_control.c ..\Source\APP\safe_control.c /Foout\ /Feout\test_safe_control.exe
if errorlevel 1 exit /b 1
out\test_safe_control.exe
exit /b %errorlevel%
