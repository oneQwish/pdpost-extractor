#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Russian Post PDF Extractor — CLI (GUI-compatible)
- Track: exactly 14 digits starting with '8'
- Code: exactly 8 digits
- Совместим с GUI: поддерживает --progress-stdout, --cancel-file, --debug-dump-text, --log
"""

import argparse, os, re, sys, csv, json, logging, concurrent.futures
from pathlib import Path
from typing import Optional, Dict, List

DEBUG_DUMP_DIR: Optional[str] = None
TRACK14 = r"8\d{13}"

from pdfminer.high_level import extract_text
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument

try:
    from pdf2image import convert_from_path
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

if os.name == "nt":
    tp = os.environ.get("TESSERACT_PATH")
    if not tp or not os.path.exists(tp):
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        cand = base / "tesseract" / "Tesseract-OCR" / "tesseract.exe"
        if not cand.exists():
            cand = base / "Tesseract-OCR" / "tesseract.exe"
        if cand.exists():
            tp = str(cand)
    if tp and os.path.exists(tp):
        try:
            import pytesseract  # type: ignore
            pytesseract.pytesseract.tesseract_cmd = tp
        except Exception:
            pass


def extract_page_text_pdfminer(pdf_path: Path, pidx: int) -> str:
    try:
        return extract_text(str(pdf_path), page_numbers=[pidx]) or ""
    except Exception:
        return ""


def extract_page_text_ocr(pdf_path: Path, pidx: int, dpi: int = 300, lang: str = "rus+eng") -> str:
    if not OCR_AVAILABLE:
        return ""
    poppler_path = os.environ.get("POPPLER_PATH")
    if not poppler_path:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        cand = base / "poppler" / "bin"
        if cand.is_dir():
            poppler_path = str(cand)
    kwargs = {"dpi": dpi, "first_page": pidx + 1, "last_page": pidx + 1}
    if poppler_path and os.path.isdir(poppler_path):
        kwargs["poppler_path"] = poppler_path
    try:
        imgs = convert_from_path(str(pdf_path), **kwargs)
        if not imgs:
            return ""
        return pytesseract.image_to_string(imgs[0], lang=lang) or ""
    except Exception:
        return ""


def get_page_count(pdf_path: Path) -> int:
    try:
        with open(pdf_path, "rb") as f:
            parser = PDFParser(f); doc = PDFDocument(parser)
            return sum(1 for _ in PDFPage.create_pages(doc))
    except Exception:
        try:
            convert_from_path(str(pdf_path), first_page=1, last_page=1)
            return 2
        except Exception:
            return 1


def sniff_track_code_with_labels(text: str):
    t = text.replace("\xa0", " ")
    track_label_re = re.compile(r"(трек.*номер|трек\s*№|почтовый\s+идентификатор|идентификатор\s+отправления)", re.I)
    code_label_re  = re.compile(r"код\s*доступа", re.I)

    def _after(m_end: int, kind: str):
        window = re.sub(r"[^0-9\s]", " ", t[m_end:m_end+500])
        window = re.sub(r"\s+", " ", window)
        if kind == "track":
            m = re.search(r"8(?:\s*\d){13}", window)
            if m:
                raw = re.sub(r"\s+", "", m.group(0))
                if re.fullmatch(TRACK14, raw): return raw
        if kind == "code":
            m = re.search(r"(?:\d\s*){8}", window)
            if m:
                raw = re.sub(r"\s+", "", m.group(0))
                if len(raw) == 8 and raw.isdigit(): return raw
        return None

    track = code = None
    m1 = track_label_re.search(t)
    if m1: track = _after(m1.end(), "track")
    m2 = code_label_re.search(t)
    if m2: code = _after(m2.end(), "code")
    if track and code: return track, code

    pg = re.sub(r"[^0-9\s]", " ", t)
    pg = re.sub(r"\s+", " ", pg)
    m = re.search(r"8(?:\s*\d){13}", pg)
    if m:
        raw = re.sub(r"\s+", "", m.group(0))
        if re.fullmatch(TRACK14, raw):
            track = raw
            pg = pg.replace(m.group(0), " ")
    m = re.search(r"(?:\d\s*){8}", pg)
    if m:
        raw = re.sub(r"\s+", "", m.group(0))
        if len(raw) == 8 and raw.isdigit():
            code = raw
    return track, code


def process_pdf(pdf_path: Path,
                max_pages_back=5,
                min_chars_for_ocr=200,
                enable_ocr=True,
                cancel_cb=None,
                force_ocr=False,
                ocr_dpi=300,
                ocr_lang="rus+eng") -> Dict[str, Optional[str]]:
    res = {"source": pdf_path.name, "track": None, "code": None, "method": ""}
    total_pages = max(1, get_page_count(pdf_path))
    pages = list(range(total_pages-1, -1, -1))
    if max_pages_back > 0: pages = pages[:max_pages_back]

    for pidx in pages:
        if cancel_cb and cancel_cb(): res["method"]="canceled"; return res
        tr=cd=None; txt=""; method=""
        if not force_ocr:
            txt = extract_page_text_pdfminer(pdf_path, pidx)
            tr,cd = sniff_track_code_with_labels(txt); method="text"
        if (force_ocr or (not tr or not cd)) and enable_ocr:
            ocr_txt = extract_page_text_ocr(pdf_path, pidx, dpi=ocr_dpi, lang=ocr_lang)
            if ocr_txt:
                tr2,cd2 = sniff_track_code_with_labels(ocr_txt)
                if tr2 and cd2: tr,cd=tr2,cd2; method="ocr"
        if tr and cd:
            res.update(track=tr, code=cd, method=method); return res
    return res


def walk_pdfs(path: Path):
    if path.is_file() and path.suffix.lower()==".pdf": return [path]
    return sorted(p for p in path.rglob("*.pdf") if p.is_file())


def _process_pdf_wrapper(args): return process_pdf(Path(args[0]), *args[1:])


def run_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input"); ap.add_argument("--output")
    ap.add_argument("--csv", action="store_true")
    ap.add_argument("--max-pages-back", type=int, default=5)
    ap.add_argument("--min-chars-for-ocr", type=int, default=200)
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--force-ocr", action="store_true", dest="force_ocr", default=False)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--lang", default="rus+eng")
    # GUI flags (ignored internally but accepted)
    ap.add_argument("--progress-stdout", action="store_true")
    ap.add_argument("--cancel-file", default="")
    ap.add_argument("--debug-dump-text", default="")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    pdfs = walk_pdfs(Path(args.input))
    total = len(pdfs)
    cancel_cb = None
    if args.cancel_file:
        def cancel_cb():
            try:
                return os.path.exists(args.cancel_file)
            except Exception:
                return False
    if args.progress_stdout:
        print(json.dumps({"event": "start", "total": total}), flush=True)

    results = []
    for pdf in pdfs:
        if cancel_cb and cancel_cb():
            break
        rec = process_pdf(pdf, args.max_pages_back, args.min_chars_for_ocr, not args.no_ocr,
                          cancel_cb=cancel_cb, force_ocr=args.force_ocr,
                          ocr_dpi=args.dpi, ocr_lang=args.lang)
        results.append(rec)
        if args.progress_stdout:
            evt = {"event": "progress", "file": rec["source"],
                   "track": rec.get("track"), "code": rec.get("code"),
                   "method": rec.get("method")}
            print(json.dumps(evt, ensure_ascii=False), flush=True)

    out_enc = "utf-8-sig" if os.name == "nt" else "utf-8"
    if args.csv or args.output.lower().endswith(".csv"):
        with open(args.output, "w", newline="", encoding=out_enc) as f:
            w = csv.writer(f)
            w.writerow(["filename", "track", "code"])
            for r in results:
                w.writerow([r["source"], r["track"] or "", r["code"] or ""])
    else:
        with open(args.output, "w", encoding=out_enc) as f:
            for r in results:
                f.write(f"{r['source']} - {r['track'] or ''} - {r['code'] or ''}\n")

    if args.progress_stdout:
        print(json.dumps({"event": "done", "count": len(results),
                          "output": args.output}, ensure_ascii=False), flush=True)


if __name__=="__main__":
    import multiprocessing as mp; mp.freeze_support(); run_cli()

