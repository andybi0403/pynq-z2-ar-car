#!/bin/sh
set -eu

cd "$(dirname "$0")"
duration="${SENSOR_CONSOLE_DURATION:-1800}"
evidence="${SENSOR_CONSOLE_EVIDENCE:-evidence/sensor_console_$(date -u +%Y%m%dT%H%M%SZ)}"
mode="${SENSOR_CONSOLE_VIDEO_MODE:-auto}"

exec python3 wireless_runtime.py \
  --motor-disconnected \
  --diagnostic-startup \
  --duration "$duration" \
  --video-mode "$mode" \
  --evidence-dir "$evidence" \
  "$@"
