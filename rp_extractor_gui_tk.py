#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Минимальный Tkinter-GUI для запуска CLI-утилиты извлечения PDF."""

import os
import sys
import json
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox


APP_TITLE = "Russian Post PDF Extractor — Minimal GUI"


def is_frozen():
    """Возвращает True, если приложение запущено из упакованного бинарника."""

    return getattr(sys, "frozen", False)


def find_extractor_cmd():
    """Находит исполняемый файл CLI для запуска из GUI."""

    here = os.path.dirname(os.path.abspath(__file__))
    if is_frozen():
        exe = os.path.join(here, "rp_extractor.exe")
        if os.path.exists(exe):
            return [exe]
    rp_py = os.path.join(here, "rp_extractor.py")
    if os.path.exists(rp_py):
        return [sys.executable, rp_py]
    return ["rp_extractor"]


class App(tk.Tk):
    """Главное окно приложения: управляет состоянием и взаимодействует с CLI."""

    def __init__(self):
        """Настраивает окно, переменные состояния и интерфейс."""
        super().__init__()
        self._set_dark_theme()
        self.title(APP_TITLE)
        self.geometry("960x660")
        # Tkinter-переменные позволяют автоматически обновлять привязанные
        # элементы управления и следить за изменениями значений.
        self.in_path = tk.StringVar()
        self.out_path = tk.StringVar()
        self.csv = tk.BooleanVar(value=True)
        self.no_ocr = tk.BooleanVar(value=False)
        self.force_ocr = tk.BooleanVar(value=False)
        self.max_pages = tk.IntVar(value=5)
        self.min_chars = tk.IntVar(value=200)
        self.workers = tk.IntVar(value=0)
        self.dpi = tk.IntVar(value=400)
        self.lang = tk.StringVar(value="rus+eng")
        self.dump_dir = tk.StringVar(value="")
        self.log_path = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Готов к запуску")
        self.total = 0
        self.done = 0
        self.cancel_file = None
        self._last_output = ""
        self._cancel_requested = False
        self._saw_done_event = False
        # Триггеры обновляют связанные поля при изменении настроек пользователем.
        self.csv.trace_add("write", lambda *_: self._ensure_output_extension())
        self.out_path.trace_add("write", lambda *_: self._update_open_buttons())
        self.log_path.trace_add("write", lambda *_: self._update_open_buttons())
        self._build_ui()
    def _set_dark_theme(self):
        """Применяет тёмную цветовую схему ко всем элементам управления."""

        bg = "#2e2e2e"
        fg = "#ffffff"
        accent = "#5b9bd5"
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=bg, foreground=fg)
        style.configure("TEntry", fieldbackground="#3c3f41", foreground=fg)
        style.configure("TSpinbox", fieldbackground="#3c3f41", foreground=fg)
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.configure("TButton", background="#444", foreground=fg)
        style.configure("TProgressbar", background=accent)
        self.configure(bg=bg)

    def _build_ui(self):
        """Создаёт и размещает виджеты интерфейса."""

        pad = {"padx": 8, "pady": 6}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=12, pady=12)
        frm.columnconfigure(1, weight=2)
        frm.columnconfigure(2, weight=1)
        frm.columnconfigure(3, weight=0)

        ttk.Label(frm, text="Вход (PDF или папка):").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.in_path, width=80).grid(row=0, column=1, columnspan=2, sticky="we", **pad)
        in_btns = ttk.Frame(frm)
        in_btns.grid(row=0, column=3, sticky="nsew", **pad)
        ttk.Button(in_btns, text="Файл", command=self.browse_in_file).pack(fill="x", pady=(0, 2))
        ttk.Button(in_btns, text="Папка", command=self.browse_in_dir).pack(fill="x")

        ttk.Label(frm, text="Выходной файл:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.out_path, width=80).grid(row=1, column=1, columnspan=2, sticky="we", **pad)
        out_btns = ttk.Frame(frm)
        out_btns.grid(row=1, column=3, sticky="nsew", **pad)
        ttk.Button(out_btns, text="Обзор", command=self.browse_out_file).pack(fill="x", pady=(0, 2))
        self.btn_open_output = ttk.Button(out_btns, text="Открыть", command=self.open_output, state="disabled")
        self.btn_open_output.pack(fill="x")

        ttk.Checkbutton(frm, text="CSV", variable=self.csv).grid(row=2, column=0, sticky="w", **pad)
        ttk.Checkbutton(frm, text="Отключить OCR", variable=self.no_ocr).grid(row=2, column=1, sticky="w", **pad)
        ttk.Checkbutton(frm, text="Принудительный OCR", variable=self.force_ocr).grid(row=2, column=2, sticky="w", **pad)

        row = 3
        ttk.Label(frm, text="Последние страниц:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Spinbox(frm, from_=0, to=50, textvariable=self.max_pages, width=8).grid(row=row, column=1, sticky="w", **pad)
        ttk.Label(frm, text="Мин. символов для OCR:").grid(row=row, column=2, sticky="e", **pad)
        ttk.Spinbox(
            frm,
            values=(50, 100, 150, 200, 250, 300, 400, 500, 750, 1000),
            textvariable=self.min_chars,
            width=10,
        ).grid(row=row, column=3, sticky="w", **pad)

        row += 1
        ttk.Label(frm, text="Воркеров:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Spinbox(frm, from_=0, to=32, textvariable=self.workers, width=8).grid(row=row, column=1, sticky="w", **pad)
        ttk.Label(frm, text="OCR DPI:").grid(row=row, column=2, sticky="e", **pad)
        ttk.Spinbox(frm, values=(150, 200, 250, 300, 350, 400, 450, 500, 600), textvariable=self.dpi, width=10).grid(
            row=row, column=3, sticky="w", **pad
        )

        row += 1
        ttk.Label(frm, text="0 = авто потоков").grid(row=row, column=1, sticky="w", **pad)

        row += 1
        ttk.Label(frm, text="Языки OCR (lang):").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.lang).grid(row=row, column=1, columnspan=3, sticky="we", **pad)

        row += 1
        ttk.Label(frm, text="Папка для дампов текста:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.dump_dir).grid(row=row, column=1, columnspan=2, sticky="we", **pad)
        ttk.Button(frm, text="Обзор", command=self.browse_dump_dir).grid(row=row, column=3, sticky="we", **pad)

        row += 1
        ttk.Label(frm, text="Файл лога (опц.):").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.log_path).grid(row=row, column=1, columnspan=2, sticky="we", **pad)
        log_btns = ttk.Frame(frm)
        log_btns.grid(row=row, column=3, sticky="nsew", **pad)
        ttk.Button(log_btns, text="Обзор", command=self.browse_log).pack(fill="x", pady=(0, 2))
        self.btn_open_log = ttk.Button(log_btns, text="Открыть", command=self.open_log, state="disabled")
        self.btn_open_log.pack(fill="x")

        row += 1
        self.pb = ttk.Progressbar(frm, orient="horizontal", mode="determinate", maximum=1, value=0)
        self.pb.grid(row=row, column=0, columnspan=3, sticky="we", **pad)
        self.pb_txt = ttk.Label(frm, text="0/0")
        self.pb_txt.grid(row=row, column=3, sticky="e", **pad)

        row += 1
        self.status_lbl = ttk.Label(frm, textvariable=self.status_var)
        self.status_lbl.grid(row=row, column=0, columnspan=4, sticky="w", **pad)

        row += 1
        btns = ttk.Frame(frm)
        btns.grid(row=row, column=0, columnspan=4, sticky="w", **pad)
        self.btn_start = ttk.Button(btns, text="Старт", command=self.start_run)
        self.btn_start.pack(side="left", padx=(0, 8))
        self.btn_stop = ttk.Button(btns, text="Стоп", command=self.stop_run, state="disabled")
        self.btn_stop.pack(side="left")

        row += 1
        self.txt = tk.Text(frm, height=18, bg="#3c3f41", fg="#ffffff")
        self.txt.grid(row=row, column=0, columnspan=4, sticky="nsew", **pad)
        frm.rowconfigure(row, weight=1)

        self._update_open_buttons()

    def _update_open_buttons(self):
        """Активирует или блокирует кнопки открытия файлов в зависимости от их наличия."""

        out = Path(self.out_path.get().strip())
        log = Path(self.log_path.get().strip())
        out_exists = out.is_file()
        log_exists = log.is_file()
        self.btn_open_output.configure(state="normal" if out_exists else "disabled")
        self.btn_open_log.configure(state="normal" if log_exists else "disabled")

    def _open_path(self, path: Path):
        """Открывает файл или каталог средствами ОС."""

        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:  # pragma: no cover - platform dependent
            messagebox.showerror("Ошибка", f"Не удалось открыть {path}: {exc}")

    def open_output(self):
        """Открывает файл с результатами, если он существует."""

        path = Path(self.out_path.get().strip())
        if not path.exists():
            messagebox.showwarning("Нет файла", "Файл ещё не создан.")
            return
        self._open_path(path)

    def open_log(self):
        """Открывает файл журнала, если он создан."""

        path = Path(self.log_path.get().strip())
        if not path.exists():
            messagebox.showwarning("Нет файла", "Лог ещё не создан.")
            return
        self._open_path(path)

    def _ensure_output_extension(self, *_args):
        """Следит за тем, чтобы расширение выходного файла соответствовало режиму."""

        out_raw = self.out_path.get().strip()
        if not out_raw:
            return
        out_path = Path(out_raw)
        if self.csv.get() and out_path.suffix.lower() != ".csv":
            self.out_path.set(str(out_path.with_suffix(".csv")))
        elif not self.csv.get() and out_path.suffix.lower() == ".csv":
            self.out_path.set(str(out_path.with_suffix(".txt")))
        self._update_open_buttons()

    def _auto_fill_output(self, selected: Path):
        """Предлагает имя файла вывода на основе выбранного пути."""

        if self.out_path.get().strip():
            return
        suffix = ".csv" if self.csv.get() else ".txt"
        if selected.is_dir():
            target = selected / f"results{suffix}"
        else:
            target = selected.with_suffix(suffix)
        self.out_path.set(str(target))
        self._update_open_buttons()

    def _set_running(self, running: bool):
        """Переключает состояние кнопок при запуске/остановке обработки."""

        if running:
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            self.btn_open_output.configure(state="disabled")
            self.btn_open_log.configure(state="disabled")
        else:
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self._update_open_buttons()

    def _reset_progress(self):
        """Сбрасывает индикатор выполнения и связанные счётчики."""

        self.total = 0
        self.done = 0
        self._saw_done_event = False
        self._last_output = ""
        self.pb.configure(mode="determinate", maximum=1, value=0)
        self.pb_txt.configure(text="0/0")

    def _on_run_finished(self, return_code):
        """Обрабатывает завершение процесса CLI и обновляет интерфейс."""

        self._set_running(False)
        if self.cancel_file:
            cf = Path(self.cancel_file)
            try:
                cf.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
        self.cancel_file = None
        if not self._saw_done_event:
            if self._cancel_requested:
                self.status_var.set("Операция отменена пользователем.")
            elif return_code is None:
                self.status_var.set("Ошибка запуска (см. лог).")
            elif return_code != 0:
                self.status_var.set(f"Завершено с ошибкой (код {return_code}).")
            else:
                self.status_var.set("Завершено.")
        self._update_open_buttons()
        self._cancel_requested = False
    def browse_in_file(self):
        """Открывает диалог выбора PDF-файла для обработки."""

        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if path:
            self.in_path.set(path)
            self._auto_fill_output(Path(path))

    def browse_in_dir(self):
        """Выбирает папку, содержащую PDF-файлы."""

        path = filedialog.askdirectory()
        if path:
            self.in_path.set(path)
            self._auto_fill_output(Path(path))

    def browse_out_file(self):
        """Позволяет выбрать или создать файл для сохранения результатов."""

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("TXT", "*.txt"), ("Все", "*.*")],
        )
        if path:
            self.out_path.set(path)
            self._ensure_output_extension()

    def browse_dump_dir(self):
        """Выбирает каталог, куда сохранять текстовые дампы для отладки."""

        path = filedialog.askdirectory()
        if path:
            self.dump_dir.set(path)

    def browse_log(self):
        """Выбирает путь для файла журнала CLI."""

        path = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log", "*.log"), ("All", "*.*")],
        )
        if path:
            self.log_path.set(path)
            self._update_open_buttons()
    def build_cmd(self, cancel_file: str):
        """Формирует список аргументов для запуска CLI с текущими настройками."""

        input_path = str(Path(self.in_path.get().strip()).expanduser())
        output_path = str(Path(self.out_path.get().strip()).expanduser())
        cmd = find_extractor_cmd()
        cmd += [
            "--input",
            input_path,
            "--output",
            output_path,
            "--max-pages-back",
            str(self.max_pages.get()),
            "--min-chars-for-ocr",
            str(self.min_chars.get()),
            "--progress-stdout",
            "--cancel-file",
            cancel_file,
        ]
        if self.csv.get() or output_path.lower().endswith(".csv"):
            cmd.append("--csv")
        if self.no_ocr.get():
            cmd.append("--no-ocr")
        if self.force_ocr.get():
            cmd.append("--force-ocr")
        if self.dpi.get():
            cmd += ["--dpi", str(self.dpi.get())]
        lang = self.lang.get().strip()
        if lang:
            cmd += ["--lang", lang]
        dump_dir = self.dump_dir.get().strip()
        if dump_dir:
            cmd += ["--debug-dump-text", str(Path(dump_dir).expanduser())]
        workers = self.workers.get()
        if workers is not None:
            cmd += ["--workers", str(workers)]
        log_path = self.log_path.get().strip()
        if log_path:
            cmd += ["--log", str(Path(log_path).expanduser())]
        return cmd
    def start_run(self):
        """Валидирует ввод пользователя и запускает обработку в фоне."""

        in_raw = self.in_path.get().strip()
        out_raw = self.out_path.get().strip()
        if not in_raw or not out_raw:
            messagebox.showerror("Ошибка", "Укажите вход и выходной файл.")
            return
        in_path = Path(in_raw)
        if not in_path.exists():
            messagebox.showerror("Ошибка", f"Путь {in_path} не найден.")
            return
        self._ensure_output_extension()
        out_path = Path(self.out_path.get().strip())
        parent = out_path.parent
        if parent and not parent.exists():
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                messagebox.showerror("Ошибка", f"Не удалось создать каталог вывода: {exc}")
                return
        here = Path(__file__).resolve().parent
        cancel_path = here / ".cancel.flag"
        self.cancel_file = cancel_path
        try:
            cancel_path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except TypeError:  # Python <3.8 fallback
            if cancel_path.exists():
                try:
                    cancel_path.unlink()
                except OSError:
                    pass
        cmd = self.build_cmd(str(cancel_path))
        self._append(">> " + " ".join(cmd))
        self._reset_progress()
        self._set_running(True)
        self.status_var.set("Запуск...")
        self._cancel_requested = False
        threading.Thread(target=self._run_proc, args=(cmd,), daemon=True).start()
    def stop_run(self):
        """Создаёт файл-флаг отмены, чтобы остановить текущий запуск."""

        if not self.cancel_file:
            return
        try:
            with open(self.cancel_file, "w", encoding="utf-8") as fh:
                fh.write("1")
            self._cancel_requested = True
            self._append("[CANCEL] Запрошена остановка...")
            self.status_var.set("Отмена запрошена...")
        except Exception as exc:
            self._append(f"[CANCEL ERROR] {exc}")
    def _run_proc(self, cmd):
        """Запускает CLI в отдельном потоке и транслирует события в GUI."""

        rc = None
        try:
            si = None
            if os.name == "nt":
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                except Exception:
                    si = None
            with subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                text=True,
                startupinfo=si,
            ) as proc:
                assert proc.stdout is not None
                for raw in proc.stdout:
                    line = raw.rstrip("\n")
                    self.after(0, self._handle_line, line)
                rc = proc.wait()
                self.after(0, self._append, f"[EXIT] Return code: {rc}")
        except Exception as exc:
            self.after(0, self._append, f"[ERROR] {exc}")
        finally:
            self.after(0, self._on_run_finished, rc)
    def _append(self, msg):
        """Добавляет строку в текстовый журнал внизу окна."""

        self.txt.insert("end", msg + "\n")
        self.txt.see("end")

    def _handle_line(self, line: str):
        """Обрабатывает строку вывода CLI, распознавая JSON-события."""

        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            self._append(line)
            return
        if not isinstance(evt, dict):
            self._append(line)
            return

        event = evt.get("event")
        if event == "start":
            self.total = int(evt.get("total") or 0)
            self.done = 0
            maximum = max(1, self.total)
            self.pb.configure(mode="determinate", maximum=maximum, value=0)
            self.pb_txt.configure(text=f"0/{self.total}")
            if self.total:
                self.status_var.set(f"Файлов к обработке: {self.total}")
            else:
                self.status_var.set("Нет PDF для обработки.")
            return

        if event == "progress":
            self.done += 1
            maximum = max(1, self.total)
            self.pb.configure(maximum=maximum, value=min(self.done, maximum))
            if self.total:
                processed = min(self.done, self.total)
                self.pb_txt.configure(text=f"{processed}/{self.total}")
            else:
                self.pb_txt.configure(text=str(self.done))
            file_name = evt.get("file", "")
            track = evt.get("track", "") or ""
            code = evt.get("code", "") or ""
            method = evt.get("method", "") or ""
            if self.total:
                self.status_var.set(f"Обработано {processed}/{self.total}: {file_name}")
            else:
                self.status_var.set(f"Обработано {self.done}: {file_name}")
            details = " ".join(part for part in (track, code) if part)
            if method:
                details = f"{details} ({method})" if details else f"({method})"
            self._append(f"[OK] {file_name} -> {details}" if details else f"[OK] {file_name}")
            return

        if event == "done":
            self._saw_done_event = True
            self._cancel_requested = False
            count = evt.get("count")
            count_display = count if count is not None else "?"
            output = evt.get("output") or ""
            self._last_output = output
            if output:
                self.status_var.set(f"Готово: {count_display} записей -> {output}")
            else:
                self.status_var.set(f"Готово: {count_display} записей")
            self._append(f"[DONE] Wrote {count_display} records to {output}")
            self._update_open_buttons()
            return

        self._append(line)
if __name__=="__main__":
    app=App(); app.mainloop()
