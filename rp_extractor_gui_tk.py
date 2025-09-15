#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, subprocess, threading, tkinter as tk
from tkinter import ttk, filedialog, messagebox
APP_TITLE = "Russian Post PDF Extractor — Minimal GUI"
def is_frozen(): return getattr(sys, "frozen", False)
def find_extractor_cmd():
    here = os.path.dirname(os.path.abspath(__file__))
    if is_frozen():
        exe = os.path.join(here, "rp_extractor.exe")
        if os.path.exists(exe): return [exe]
    rp_py = os.path.join(here, "rp_extractor.py")
    if os.path.exists(rp_py): return [sys.executable, rp_py]
    return ["rp_extractor"]
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self._set_dark_theme()
        self.title(APP_TITLE); self.geometry("900x620")
        self.in_path=tk.StringVar(); self.out_path=tk.StringVar()
        self.csv=tk.BooleanVar(value=True); self.no_ocr=tk.BooleanVar(value=False); self.force_ocr=tk.BooleanVar(value=False)
        self.max_pages=tk.IntVar(value=5); self.min_chars=tk.IntVar(value=200); self.workers=tk.IntVar(value=1)
        self.dpi=tk.IntVar(value=400); self.lang=tk.StringVar(value="rus+eng")
        self.dump_dir=tk.StringVar(value=""); self.log_path=tk.StringVar(value="")
        self.total=0; self.done=0; self.cancel_file=None; self._build_ui()
    def _set_dark_theme(self):
        bg="#2e2e2e"; fg="#ffffff"; accent="#5b9bd5"
        s=ttk.Style(self); s.theme_use("clam")
        s.configure(".", background=bg, foreground=fg)
        s.configure("TEntry", fieldbackground="#3c3f41", foreground=fg)
        s.configure("TCheckbutton", background=bg, foreground=fg)
        s.configure("TButton", background="#444", foreground=fg)
        s.configure("TProgressbar", background=accent)
        self.configure(bg=bg)
    def _build_ui(self):
        pad={"padx":8,"pady":6}; frm=ttk.Frame(self); frm.pack(fill="both",expand=True)
        ttk.Label(frm,text="Вход (файл PDF или папка):").grid(row=0,column=0,sticky="w",**pad)
        ttk.Entry(frm,textvariable=self.in_path,width=70).grid(row=0,column=1,sticky="we",**pad)
        ttk.Button(frm,text="Файл",command=self.browse_in_file).grid(row=0,column=2,**pad)
        ttk.Button(frm,text="Папка",command=self.browse_in_dir).grid(row=0,column=3,**pad)
        ttk.Label(frm,text="Выходной файл:").grid(row=1,column=0,sticky="w",**pad)
        ttk.Entry(frm,textvariable=self.out_path,width=70).grid(row=1,column=1,sticky="we",**pad)
        ttk.Button(frm,text="Обзор",command=self.browse_out_file).grid(row=1,column=2,**pad)
        ttk.Checkbutton(frm,text="CSV",variable=self.csv).grid(row=2,column=0,sticky="w",**pad)
        ttk.Checkbutton(frm,text="Отключить OCR",variable=self.no_ocr).grid(row=2,column=1,sticky="w",**pad)
        ttk.Checkbutton(frm,text="Forced OCR",variable=self.force_ocr).grid(row=2,column=2,sticky="w",**pad)
        row=3
        ttk.Label(frm,text="Последние страниц:").grid(row=row,column=0,sticky="w",**pad)
        ttk.Spinbox(frm,from_=0,to=50,textvariable=self.max_pages,width=6).grid(row=row,column=1,sticky="w",**pad)
        ttk.Label(frm,text="Мин. символов для OCR:").grid(row=row,column=2,sticky="e",**pad)
        ttk.Spinbox(frm,values=(50,100,150,200,250,300,400,500,750,1000),textvariable=self.min_chars,width=8).grid(row=row,column=3,sticky="w",**pad)
        row+=1
        ttk.Label(frm,text="Воркеров:").grid(row=row,column=0,sticky="w",**pad)
        ttk.Spinbox(frm,from_=1,to=16,textvariable=self.workers,width=6).grid(row=row,column=1,sticky="w",**pad)
        ttk.Label(frm,text="OCR DPI:").grid(row=row,column=2,sticky="e",**pad)
        ttk.Spinbox(frm,values=(150,200,250,300,350,400,450,500,600),textvariable=self.dpi,width=8).grid(row=row,column=3,sticky="w",**pad)
        row+=1
        ttk.Label(frm,text="Tesseract lang:").grid(row=row,column=0,sticky="w",**pad)
        ttk.Entry(frm,textvariable=self.lang,width=16).grid(row=row,column=1,sticky="w",**pad)
        ttk.Label(frm,text="Dump dir:").grid(row=row,column=2,sticky="e",**pad)
        ttk.Entry(frm,textvariable=self.dump_dir,width=36).grid(row=row,column=3,sticky="w",**pad)
        row+=1
        ttk.Label(frm,text="Лог (опц.):").grid(row=row,column=0,sticky="w",**pad)
        ttk.Entry(frm,textvariable=self.log_path,width=70).grid(row=row,column=1,sticky="we",**pad)
        ttk.Button(frm,text="Обзор лог",command=self.browse_log).grid(row=row,column=2,**pad)
        row+=1
        self.pb=ttk.Progressbar(frm,orient="horizontal",mode="determinate",maximum=100); self.pb.grid(row=row,column=0,columnspan=3,sticky="we",**pad)
        self.pb_txt=ttk.Label(frm,text="0/0"); self.pb_txt.grid(row=row,column=3,sticky="e",**pad)
        row+=1
        self.btn_start=ttk.Button(frm,text="Старт",command=self.start_run); self.btn_start.grid(row=row,column=0,**pad)
        self.btn_stop=ttk.Button(frm,text="Стоп",command=self.stop_run,state="disabled"); self.btn_stop.grid(row=row,column=1,**pad)
        row+=1
        self.txt=tk.Text(frm,height=18,bg="#3c3f41",fg="#ffffff"); self.txt.grid(row=row,column=0,columnspan=4,sticky="nsew",**pad)
        frm.rowconfigure(row,weight=1); frm.columnconfigure(1,weight=1); frm.columnconfigure(3,weight=1)
    def browse_in_file(self):
        p=filedialog.askopenfilename(filetypes=[("PDF","*.pdf")]); 
        if p: self.in_path.set(p)
    def browse_in_dir(self):
        p=filedialog.askdirectory(); 
        if p: self.in_path.set(p)
    def browse_out_file(self):
        p=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv"),("TXT","*.txt")]); 
        if p: self.out_path.set(p)
    def browse_log(self):
        p=filedialog.asksaveasfilename(defaultextension=".log",filetypes=[("Log","*.log"),("All","*.*")]); 
        if p: self.log_path.set(p)
    def build_cmd(self,cancel_file):
        cmd=find_extractor_cmd()
        cmd+=["--input",self.in_path.get(),"--output",self.out_path.get(),
              "--max-pages-back",str(self.max_pages.get()),"--min-chars-for-ocr",str(self.min_chars.get()),
              "--progress-stdout","--cancel-file",cancel_file]
        if self.csv.get() or self.out_path.get().lower().endswith(".csv"): cmd.append("--csv")
        if self.no_ocr.get(): cmd.append("--no-ocr")
        if self.force_ocr.get(): cmd.append("--force-ocr")
        if self.dpi.get(): cmd+=["--dpi",str(self.dpi.get())]
        if self.lang.get().strip(): cmd+=["--lang",self.lang.get().strip()]
        if self.dump_dir.get().strip(): cmd+=["--debug-dump-text",self.dump_dir.get().strip()]
        if self.workers.get() is not None: cmd+=["--workers",str(self.workers.get())]
        if self.log_path.get().strip(): cmd+=["--log",self.log_path.get().strip()]
        return cmd
    def start_run(self):
        if not self.in_path.get() or not self.out_path.get():
            messagebox.showerror("Ошибка","Укажите вход и выходной файл."); return
        here=os.path.dirname(os.path.abspath(__file__))
        self.cancel_file=os.path.join(here,".cancel.flag")
        try:
            if os.path.exists(self.cancel_file): os.remove(self.cancel_file)
        except Exception: pass
        cmd=self.build_cmd(self.cancel_file)
        self._append(">> "+" ".join(cmd))
        self.btn_start.configure(state="disabled"); self.btn_stop.configure(state="normal")
        self.pb.configure(value=0); self.pb_txt.configure(text="0/0"); self.total=0; self.done=0
        threading.Thread(target=self._run_proc,args=(cmd,),daemon=True).start()
    def stop_run(self):
        try:
            if self.cancel_file:
                with open(self.cancel_file,"w") as f: f.write("1")
                self._append("[CANCEL] Запрошена остановка...")
        except Exception as e:
            self._append(f"[CANCEL ERROR] {e}")
    def _run_proc(self,cmd):
        try:
            si=None
            if os.name=='nt':
                try:
                    si=subprocess.STARTUPINFO(); si.dwFlags|=subprocess.STARTF_USESHOWWINDOW
                except Exception: si=None
            with subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=1,text=True,startupinfo=si) as p:
                for raw in p.stdout: self._handle_line(raw.rstrip("\n"))
                rc=p.wait(); self._append(f"[EXIT] Return code: {rc}")
        except Exception as e:
            self._append(f"[ERROR] {e}")
        finally:
            self.btn_start.configure(state="normal"); self.btn_stop.configure(state="disabled")
    def _append(self,msg): self.txt.insert("end",msg+"\n"); self.txt.see("end")
    def _handle_line(self,line:str):
        try:
            evt=json.loads(line)
            if isinstance(evt,dict) and evt.get("event")=="start":
                self.total=int(evt.get("total") or 0); self.pb.configure(value=0); self.pb_txt.configure(text=f"{self.done}/{self.total}"); return
            if isinstance(evt,dict) and evt.get("event")=="progress":
                self.done+=1
                if self.total: self.pb.configure(value=int(self.done*100/self.total)); self.pb_txt.configure(text=f"{self.done}/{self.total}")
                fn=evt.get("file",""); self._append(f"[OK] {fn} -> {evt.get('track','')} {evt.get('code','')} ({evt.get('method','')})"); return
            if isinstance(evt,dict) and evt.get("event")=="done":
                self._append(f"[DONE] Wrote {evt.get('count')} records to {evt.get('output')}"); return
        except Exception: pass
        self._append(line)
if __name__=="__main__":
    app=App(); app.mainloop()
