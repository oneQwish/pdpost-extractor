@echo off
setlocal
set "BASEDIR=%~dp0"
set "TESSERACT_PATH=%BASEDIR%Tesseract-OCR\tesseract.exe"
set "POPPLER_PATH=%BASEDIR%poppler\bin"
start "" "%BASEDIR%rp_extractor_gui.exe"
