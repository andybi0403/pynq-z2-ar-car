@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
cl /nologo /W4 /wd4819 /WX /TC /LD /O2 "C:\Users\39909\Desktop\FPGA\pynq_fpga\host\c_build\safe_control_prod.c" "C:\Users\39909\Desktop\FPGA\pynq_fpga\host\c_build\hybrid_protocol_prod.c" /Fe"C:\Users\39909\Desktop\FPGA\pynq_fpga\host\c_build\safe_control.dll" /FoC:\Users\39909\Desktop\FPGA\pynq_fpga\host\c_build\obj\ /link /EXPORT:safe_init /EXPORT:safe_tick /EXPORT:safe_fault /EXPORT:safe_source_handover /EXPORT:safe_frame /EXPORT:safe_pframe /EXPORT:safe_outputs /EXPORT:hybrid_receive /EXPORT:hybrid_report /EXPORT:hybrid_crc16 /EXPORT:safe_local_sample
if errorlevel 1 exit /b 1

