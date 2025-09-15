@echo off
setlocal
set "BASEDIR=%~dp0"
set "TESSERACT_PATH=%BASEDIR%tesseract\Tesseract-OCR\tesseract.exe"
set "POPPLER_PATH=%BASEDIR%poppler\bin"
"%BASEDIR%rp_extractor.exe" ^
  --input "%USERPROFILE%\Documents\PDFs" ^
  --output "%USERPROFILE%\Documents\results.csv" ^
  --csv --max-pages-back 5 --workers 0 --force-ocr --dpi 400 --lang rus+eng
