#!/bin/bash
set -e
echo "Building Shadow Men for macOS..."
pip install -e .
pip install pyinstaller pyobjc-framework-Quartz
pyinstaller --onefile --windowed --name shadowmen     --add-data "shadowmen:shadowmen"     shadowmen.py
echo "Build complete: dist/shadowmen.app"
