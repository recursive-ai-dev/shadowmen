#!/bin/bash
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Building standalone desktop binary for Shadow Men..."
pyinstaller shadowmen.spec

echo "Build complete! Binary located at dist/shadowmen"
