# Russian Post PDF Extractor

Инструмент для извлечения трек-номеров (14 цифр) и почтовых кодов (8 цифр) из PDF квитанций Почты России. В комплекте есть CLI, графический интерфейс на Tk, а также утилиты для сборки Windows-пакета.

## Возможности

- Обработка одиночных PDF-файлов и целых папок (рекурсивно).
- Гибридный алгоритм: сначала текст из pdfminer, при необходимости автоматически подключается OCR через Tesseract + Poppler.
- Параллельная обработка с помощью флага `--workers` (значение `0` включает «авто» — по числу CPU).
- JSON-уведомления о ходе выполнения (`--progress-stdout`) и файл-флаг отмены (`--cancel-file`) для интеграции с GUI.
- Запись логов в файл (`--log`) и дампы текста/OCR для диагностики (`--debug-dump-text`).
- Минимальный GUI с темной темой, автоподстановкой путей, просмотром результатов и возможностью отмены.

## Структура репозитория

| Путь | Назначение |
| --- | --- |
| `rp_extractor.py` | CLI-утилита. |
| `rp_extractor_gui_tk.py` | Графический интерфейс Tkinter, совместим с PyInstaller. |
| `tests/` | Pytest-тесты для ключевых сценариев обработки. |
| `build_binary.sh` / `build_binary.bat` | Быстрая сборка `.exe` через PyInstaller (Wine/Windows). |
| `build_portable_wine.sh` | Сборка «портативного» набора (GUI+CLI+зависимости) из-под Linux с Wine. |
| `portable/` | Шаблон портативного пакета (run-скрипты, Poppler, Tesseract, placeholder-EXE). |
| `dist/` | Целевая папка PyInstaller (создаётся автоматически). |

## Быстрый старт (CLI на Linux/macOS)

1. Установите Python ≥ 3.10 и необходимые пакеты:

   ```bash
   python3 -m pip install -U pip
   python3 -m pip install pdfminer.six pdf2image pillow pytesseract
   ```

   Для OCR дополнительно нужны системные зависимости:

   - Poppler (`sudo apt install poppler-utils` или `brew install poppler`).
   - Tesseract (`sudo apt install tesseract-ocr` или `brew install tesseract`).

2. Запуск CLI:

   ```bash
   python3 rp_extractor.py \
     --input /path/to/invoice.pdf \
     --output results.csv \
     --csv --workers 0 --force-ocr --lang rus+eng
   ```

3. Для пакетной обработки каталога достаточно передать путь к папке:

   ```bash
   python3 rp_extractor.py --input ./pdfs --output results.csv --csv --workers 4
   ```

## Ключевые опции CLI

| Флаг | Что делает |
| --- | --- |
| `--max-pages-back` | Сколько последних страниц анализировать (по умолчанию 5). |
| `--min-chars-for-ocr` | Минимальное число символов в pdfminer-тексте, ниже которого запускается OCR. |
| `--no-ocr` / `--force-ocr` | Полностью выключить OCR или принудительно включить его для всех страниц. |
| `--dpi` / `--lang` | DPI и языки для Tesseract. |
| `--workers` | Количество потоков (0 = автоматически). |
| `--debug-dump-text DIR` | Сохраняет распознанный текст/ocr в указанную папку. |
| `--log FILE` | Пишет лог работы в файл (UTF-8). |
| `--progress-stdout` | Включает JSON-события `start/progress/done` в stdout. |
| `--cancel-file PATH` | Если файл появляется во время работы, обработка прерывается. |

### Пример простого JSON-ивента

```json
{"event": "progress", "file": "invoice.pdf", "track": "800...", "code": "12345678", "method": "ocr"}
```

GUI использует эти события для отображения прогресса и отмены.

## GUI (Tkinter)

Запуск из исходников:

```bash
python3 rp_extractor_gui_tk.py
```

Основные функции GUI:

- Автоподстановка выходного файла (`invoice.pdf` → `invoice.csv`, для папок — `results.csv`).
- Возможность выбрать каталог для дампов текста, файл лога и открыть их после завершения.
- Кнопка «Открыть» для готового CSV/логов, обновление статуса и прогресс-бара на основе JSON-событий.
- Поддержка отмены обработки (создаётся `.cancel.flag` рядом с exe/скриптом).
- Значение «0» в поле «Воркеров» включает автоматический подбор количества потоков.

> **Примечание.** На Windows при запуске PyInstaller-сборки важно выставить переменные окружения `TESSERACT_PATH` и `POPPLER_PATH` (см. `run_gui.bat`/`run_cli.bat`). Если они не заданы, приложение попытается использовать вложенные копии из портативного пакета.

## Диагностика и логирование

- `--log some.log` включит запись хода работы и ошибок (в UTF-8). GUI позволяет выбрать путь и открыть лог после завершения.
- `--debug-dump-text dumps/` сохранит `.txt` файлы с текстом и OCR-выводом для каждой страницы (помогает при отладке извлечения).
- Для досрочного завершения можно создать файл, переданный через `--cancel-file` (GUI делает это автоматически при нажатии «Стоп»).

## Тесты

```bash
pytest
```

Юнит-тесты моделируют ключевые сценарии: выбор OCR при коротком тексте, параллельную обработку и отмену по флагу.

## Сборка Windows-версии через Wine

1. Установите Wine и winetricks (пример для Ubuntu):

   ```bash
   sudo apt install wine winetricks
   ```

2. Создайте отдельный wine-префикс и установите Windows Python 3.11:

   ```bash
   export WINEARCH=win64
   export WINEPREFIX=$HOME/.wine-py311
   wineboot -i

   # Скачайте официальный установщик python-3.11.x-amd64.exe и выполните:
   wine ~/Downloads/python-3.11.x-amd64.exe /quiet TargetDir=C:\\Python311 InstallAllUsers=1 PrependPath=1 Include_test=0
   ```

3. Установите зависимости в Windows-окружении:

   ```bash
   wine "C:\\Python311\\python.exe" -m pip install -U pip
   wine "C:\\Python311\\python.exe" -m pip install pyinstaller pdfminer.six pdf2image pillow pytesseract
   ```

4. Соберите `.exe` (CLI и GUI):

   ```bash
   ./build_binary.sh
   ```

   Исполняемые файлы появятся в `dist/rp_extractor.exe` и `dist/rp_extractor_gui.exe`.

## Портативная сборка (Wine)

Сценарий `build_portable_wine.sh` автоматизирует полный цикл: сборка PyInstaller + подготовка структуры с зависимостями и архива.

```bash
# Опционально переопределите путь к wine/python:
export WINE=/usr/bin/wine
export WINE_PYTHON='C:\\Python311\\python.exe'

./build_portable_wine.sh
```

Скрипт:

1. Проверяет наличие PyInstaller в Windows-окружении.
2. Собирает `rp_extractor.exe` и `rp_extractor_gui.exe`.
3. Копирует шаблон из `portable/` (там должны лежать актуальные `Tesseract-OCR/`, `poppler/`, `run_gui.bat`, `run_cli.bat`).
4. Подменяет exe свежесобранными версиями.
5. Создаёт папку `dist/portable/rp_extractor_portable_<дата>` и, при наличии `zip`, архив `dist/portable/rp_extractor_portable_<дата>.zip`.

Получившийся набор содержит готовые батники:

- `run_gui.bat` — запускает GUI, передавая переменные `TESSERACT_PATH` и `POPPLER_PATH`.
- `run_cli.bat` — пример пакетной обработки каталога пользователя (можете отредактировать под свои нужды).

> Если нужно обновить Poppler или Tesseract, замените содержимое в `portable/` и повторно запустите `build_portable_wine.sh`.

## Полезные советы

- `--workers 0` выбирает количество потоков автоматически. Для OCR-нагруженных задач удобно задавать число по ядрам.
- Минимальный набор OCR-данных — `rus.traineddata` и `eng.traineddata` (копируются в `portable/Tesseract-OCR/tessdata`).
- Локальные дампы OCR помогают подобрать `--min-chars-for-ocr` и `--dpi` под конкретный скан.

Готово! Пользуйтесь CLI или GUI, а при необходимости собирайте полноценный Windows-пакет одним скриптом.
