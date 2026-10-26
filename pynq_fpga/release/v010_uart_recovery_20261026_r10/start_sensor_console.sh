#!/bin/sh
set -eu

cd "$(dirname "$0")"
export XILINX_XRT="${XILINX_XRT:-/usr}"
export PYTHONDONTWRITEBYTECODE=1
python="${SENSOR_CONSOLE_PYTHON:-/usr/local/share/pynq-venv/bin/python3}"
if [ ! -x "$python" ]; then python=python3; fi
if [ "$(id -u)" -ne 0 ]; then
  echo 'PYNQ hardware requires root; run: sudo ./start_sensor_console.sh' >&2
  exit 1
fi
duration="${SENSOR_CONSOLE_DURATION:-1800}"
evidence="${SENSOR_CONSOLE_EVIDENCE:-evidence/sensor_console_$(date -u +%Y%m%dT%H%M%SZ)}"
mode="${SENSOR_CONSOLE_VIDEO_MODE:-auto}"
case "${SENSOR_CONSOLE_MOTOR_MODE:-disconnected}" in
  disconnected) motor_flag=--motor-disconnected ;;
  connected-zero-output) motor_flag=--motor-connected-zero-output ;;
  *) echo 'Invalid SENSOR_CONSOLE_MOTOR_MODE' >&2; exit 1 ;;
esac

"$python" prepare_console.py --enable-risk-evaluation
exec "$python" wireless_runtime.py \
  "$motor_flag" \
  --diagnostic-startup \
  --duration "$duration" \
  --video-mode "$mode" \
  --evidence-dir "$evidence" \
  "$@"
