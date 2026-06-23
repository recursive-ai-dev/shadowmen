@echo off
echo Building Shadow Men for Windows...
pip install -e .
pip install pyinstaller pygetwindow
pyinstaller --onefile --windowed --name shadowmen ^
    --add-data "shadowmen;shadowmen" ^
    shadowmen.py
echo Build complete: dist/shadowmen.exe
