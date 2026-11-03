@echo off
setlocal
cd /d "%~dp0"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not exist out mkdir out
cl /nologo /W4 /wd4819 /WX /TC /LD ..\Source\APP\safe_control.c /Foout\ /Feout\safe_control.dll /link /EXPORT:safe_init /EXPORT:safe_tick /EXPORT:safe_fault /EXPORT:safe_source_handover /EXPORT:safe_frame /EXPORT:safe_pframe /EXPORT:safe_outputs
exit /b %errorlevel%
