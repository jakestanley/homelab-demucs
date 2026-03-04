#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

cd "$REPO_ROOT"

PYTHON_EXE=${DEMUCS_PYTHON_EXE:-}
if [ -z "$PYTHON_EXE" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_EXE=$(command -v python3)
    elif command -v python >/dev/null 2>&1; then
        PYTHON_EXE=$(command -v python)
    else
        echo "Python interpreter not found. Set DEMUCS_PYTHON_EXE or install python3." >&2
        exit 1
    fi
fi

if ! command -v "$PYTHON_EXE" >/dev/null 2>&1 && [ ! -x "$PYTHON_EXE" ]; then
    echo "Configured DEMUCS_PYTHON_EXE is not executable: $PYTHON_EXE" >&2
    exit 1
fi

exec "$PYTHON_EXE" -m demucs_service.server
