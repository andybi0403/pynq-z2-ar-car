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
export PYNQ_VIDEO_PROFILE="$("$python" -c 'import json;print(json.load(open("lab_manifest.json"))["video_profile"])')"
video_fps=10
video_quality=65
codec_flags=
if [ "$PYNQ_VIDEO_PROFILE" = wireless360 ]; then
 video_fps=25
 codec_flags="--jpeg-profile balanced_fast --reuse-decoder"
fi
if [ "$PYNQ_VIDEO_PROFILE" = wireless720_jpeg ]; then
 video_fps=25
 video_quality=85
 codec_flags="--jpeg-profile hardware_422"
fi
"$python" prepare_console.py --enable-risk-evaluation
exec "$python" wireless_runtime.py --full-console "$motor_flag" --diagnostic-startup \
 --duration "${SENSOR_CONSOLE_DURATION:-0}" --video-mode manual --fps "$video_fps" --quality "$video_quality" $codec_flags \
 --evidence-dir "evidence/console_$(date -u +%Y%m%dT%H%M%SZ)" "$@"
