#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# -- Input directory --
echo "Input directory (press Enter for default 'inputs/'):"
read -r INPUT_DIR
INPUT_DIR="${INPUT_DIR:-inputs}"

if [ ! -d "$INPUT_DIR" ]; then
    echo "ERROR: directory not found: $INPUT_DIR"
    exit 1
fi

# -- Setup venv if missing --
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

# -- Install deps --
pip install -r requirements.txt -q

# -- Run --
python main.py --input-dir "$INPUT_DIR"
