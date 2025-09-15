#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$ROOT_DIR/dist"
PORTABLE_TEMPLATE="$ROOT_DIR/portable"
PORTABLE_OUT_ROOT="$DIST_DIR/portable"

WINE_BIN="${WINE:-wine}"
WIN_PYTHON="${WINE_PYTHON:-C:\\Python311\\python.exe}"

if ! command -v "$WINE_BIN" >/dev/null 2>&1; then
  echo "[ERROR] wine не найден. Укажите путь через переменную WINE." >&2
  exit 1
fi

echo "Используем wine: $WINE_BIN"
echo "Используем Windows Python: $WIN_PYTHON"

if [ ! -d "$PORTABLE_TEMPLATE" ]; then
  echo "[ERROR] Не найдена директория с заготовкой portable: $PORTABLE_TEMPLATE" >&2
  exit 1
fi

# Проверяем, установлен ли PyInstaller
if ! "$WINE_BIN" "$WIN_PYTHON" -m pip show pyinstaller >/dev/null 2>&1; then
  echo "[ERROR] PyInstaller не установлен в Windows-окружении." >&2
  echo "        Установите: wine \"$WIN_PYTHON\" -m pip install pyinstaller" >&2
  exit 1
fi

echo "Собираем исполняемые файлы..."
"$WINE_BIN" "$WIN_PYTHON" -m PyInstaller --clean --noconfirm --onefile --name rp_extractor "$ROOT_DIR/rp_extractor.py"
"$WINE_BIN" "$WIN_PYTHON" -m PyInstaller --clean --noconfirm --onefile --noconsole --name rp_extractor_gui "$ROOT_DIR/rp_extractor_gui_tk.py"

if [ ! -f "$DIST_DIR/rp_extractor.exe" ] || [ ! -f "$DIST_DIR/rp_extractor_gui.exe" ]; then
  echo "[ERROR] PyInstaller не создал rp_extractor.exe/rp_extractor_gui.exe" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET_NAME="rp_extractor_portable_$STAMP"
TARGET_DIR="$PORTABLE_OUT_ROOT/$TARGET_NAME"
mkdir -p "$PORTABLE_OUT_ROOT"

python3 - "$PORTABLE_TEMPLATE" "$TARGET_DIR" <<'PY'
import shutil
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst)
PY

cp "$DIST_DIR/rp_extractor.exe" "$TARGET_DIR/"
cp "$DIST_DIR/rp_extractor_gui.exe" "$TARGET_DIR/"

echo "Создаём ZIP архив..."
if command -v zip >/dev/null 2>&1; then
  (cd "$PORTABLE_OUT_ROOT" && zip -r "$TARGET_NAME.zip" "$TARGET_NAME" >/dev/null)
  echo "Готовый архив: $PORTABLE_OUT_ROOT/$TARGET_NAME.zip"
else
  echo "[WARN] Утилита zip не найдена, архив не создан." >&2
fi

echo "Портативная сборка: $TARGET_DIR"
