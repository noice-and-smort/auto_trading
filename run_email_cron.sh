#!/usr/bin/env bash
set -e

# Change directory to project root
cd "$(dirname "$0")"

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    . venv/bin/activate
fi

# Run script with email notification enabled
python3 src/script.py --email
