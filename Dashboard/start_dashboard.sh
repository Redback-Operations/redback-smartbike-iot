#!/usr/bin/env bash
# Start Redback SmartBike IoT Dashboard on Linux / Raspberry Pi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

if [ -f "../.env" ]; then
    export $(grep -v '^#' ../.env | xargs)
elif [ -f "$HOME/.env" ]; then
    export $(grep -v '^#' $HOME/.env | xargs)
fi

python3 run.py "$@"
