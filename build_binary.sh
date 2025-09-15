#!/usr/bin/env bash
set -euo pipefail
wine "C:\\Python311\\python.exe" -m PyInstaller --clean --onefile --name rp_extractor rp_extractor.py
wine "C:\\Python311\\python.exe" -m PyInstaller --clean --onefile --noconsole --name rp_extractor_gui rp_extractor_gui_tk.py
echo Built EXEs in ./dist
