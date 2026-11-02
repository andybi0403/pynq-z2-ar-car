#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec sh ./start_console.sh "$@"
