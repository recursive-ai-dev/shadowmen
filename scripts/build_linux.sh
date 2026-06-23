#!/bin/bash
set -e
echo "Building Shadow Men for Linux..."
pip install -e .
pip install pyinstaller
pyinstaller --onefile --name shadowmen     --add-data "shadowmen:shadowmen"     shadowmen.py
echo "Build complete: dist/shadowmen"
