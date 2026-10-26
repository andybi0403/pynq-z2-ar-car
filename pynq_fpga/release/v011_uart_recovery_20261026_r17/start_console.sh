#!/bin/sh
set -eu
cd "$(dirname "$0")"
export XILINX_XRT="${XILINX_XRT:-/usr}"
export PYTHONDONTWRITEBYTECODE=1
python="${SENSOR_CONSOLE_PYTHON:-/usr/local/share/pynq-venv/bin/python3}"
case "${SENSOR_CONSOLE_MOTOR_MODE:-connected}" in
 connected) motor_flag=--motor-connected ;;
 disconnected) motor_flag=--motor-disconnected ;;
 *) echo 'Motor physical state must be connected or disconnected' >&2; exit 1 ;;
esac
"$python" prepare_console.py --enable-risk-evaluation
exec "$python" wireless_runtime.py --full-console "$motor_flag" --diagnostic-startup \
 --duration "${SENSOR_CONSOLE_DURATION:-1800}" --video-mode auto \
 --evidence-dir "evidence/console_$(date -u +%Y%m%dT%H%M%SZ)" "$@"
