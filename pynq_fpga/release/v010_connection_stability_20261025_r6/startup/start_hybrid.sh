#!/bin/sh
set -eu
cd /home/xilinx/edge_console_v010_uart_role_fix_20261014_r3
export XILINX_XRT=/usr
export PYTHONDONTWRITEBYTECODE=1
/usr/local/share/pynq-venv/bin/python3 /home/xilinx/stm32_sensors_platform_20261013/prepare_hybrid.py --enable-risk-evaluation
exec /usr/local/share/pynq-venv/bin/python3 ./wireless_runtime.py "$@"
