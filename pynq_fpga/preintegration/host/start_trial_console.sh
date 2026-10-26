#!/bin/sh
set -eu
cd "$(dirname "$0")"
export XILINX_XRT="${XILINX_XRT:-/usr}"
export PYTHONDONTWRITEBYTECODE=1
python="${SENSOR_CONSOLE_PYTHON:-/usr/local/share/pynq-venv/bin/python3}"
# Preparation resets both scales to zero. No guessed scale is applied here.
"$python" prepare_console.py --enable-risk-evaluation
exec "$python" trial_runtime.py --ground-trial --duration "${SENSOR_CONSOLE_DURATION:-1800}" "$@"
