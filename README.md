# Russian Post PDF Extractor — Full Package

## Состав
- `rp_extractor.py` — CLI.
- `rp_extractor_gui_tk.py` — минимальный Tk GUI (в сборке вызывает `rp_extractor.exe`).
- `build_binary.sh` / `build_binary.bat` — сборка .exe через PyInstaller.
- Инструкции по сборке на Linux→Windows (Wine) и упаковке Portable.

## Сборка .exe на Linux через Wine
```bash
# Fedora / Ubuntu: поставьте wine
# Fedora:
sudo dnf install wine winetricks
# Ubuntu:
# sudo apt-get install wine winetricks

export WINEARCH=win64
export WINEPREFIX=$HOME/.wine-py311
wineboot -i

# Установите Windows-Python 3.11.x (скачайте офиц. установщик)
wine ~/Downloads/python-3.11.X-amd64.exe /quiet TargetDir=C:\Python311 InstallAllUsers=1 PrependPath=1 Include_test=0

wine "C:\Python311\python.exe" -m pip install -U pip
wine "C:\Python311\python.exe" -m pip install pyinstaller pdfminer.six pdf2image pillow pytesseract

# Сборка
cd /path/to/this/folder
wine "C:\Python311\python.exe" -m PyInstaller --clean --onefile --name rp_extractor rp_extractor.py
wine "C:\Python311\python.exe" -m PyInstaller --clean --onefile --noconsole --name rp_extractor_gui rp_extractor_gui_tk.py
# Готовые exe: dist\rp_extractor.exe, dist\rp_extractor_gui.exe
```

> Предупреждения вида `InvokeShellLinker failed to extract icon` — безвредны.

## Упаковка Portable-пакета
Сделайте структуру:
```
portable\
  rp_extractor.exe
  rp_extractor_gui.exe
  tesseract\
    Tesseract-OCR\
      tesseract.exe
      tessdata\
        rus.traineddata
        eng.traineddata
  poppler\
    bin\
      pdftoppm.exe
      pdfinfo.exe
  run_gui.bat
  run_cli.bat
```

`run_gui.bat`:
```bat
@echo off
setlocal
set "BASEDIR=%~dp0"
set "TESSERACT_PATH=%BASEDIR%tesseract\Tesseract-OCR\tesseract.exe"
set "POPPLER_PATH=%BASEDIR%poppler\bin"
start "" "%BASEDIR%rp_extractor_gui.exe"
```

`run_cli.bat`:
```bat
@echo off
setlocal
set "BASEDIR=%~dp0"
set "TESSERACT_PATH=%BASEDIR%tesseract\Tesseract-OCR\tesseract.exe"
set "POPPLER_PATH=%BASEDIR%poppler\bin"
"%BASEDIR%rp_extractor.exe" ^
  --input "%USERPROFILE%\Documents\PDFs" ^
  --output "%USERPROFILE%\Documents\results.csv" ^
  --csv --max-pages-back 5 --workers 0 --force-ocr --dpi 400 --lang rus+eng
```

Где взять зависимости:
- Tesseract (Windows, x64): установщик от UB Mannheim (ссылка в оф. доках Tesseract). После установки скопируйте папку `Tesseract-OCR`.
- Poppler for Windows: возьмите архив с бинарниками из GitHub Releases `oschwartz10612/poppler-windows`, из него нужна `bin\`.
```

