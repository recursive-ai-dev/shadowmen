#!/bin/bash
set -e

echo "Building standalone desktop binary for Shadow Men..."
pyinstaller --name shadowmen \
            --onefile \
            --windowed \
            --hidden-import gi.repository.Gtk \
            --hidden-import gi.repository.Gdk \
            --hidden-import gi.repository.GLib \
            --hidden-import gi.repository.cairo \
            --hidden-import cairo \
            shadowmen/__main__.py

echo "Build complete! Binary located at dist/shadowmen"
