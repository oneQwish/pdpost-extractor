#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Russian Post PDF Extractor — CLI (GUI-compatible)
- Track: exactly 14 digits starting with '8'
- Code: exactly 8 digits
- Совместим с GUI: поддерживает --progress-stdout, --cancel-file, --debug-dump-text, --log
"""

import argparse, os, re, sys, csv, json, logging, concurrent.futures
import importlib.util


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:  # pragma: no cover - depends on environment
        return False

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List, Tuple

DEBUG_DUMP_DIR: Optional[str] = None
TRACK14 = r"8\d{13}"

LOGO_RE = re.compile(r"почта\s+россии", re.I)

TRACK_LABEL_RE = re.compile(
    r"(трек\s*[-№]*\s*номер|почтов[а-я\s]*идентификатор|идентификатор\s+отправления|шпи|штрих\s*код)",
    re.I,
)
CODE_LABEL_RE = re.compile(
    r"(код\s*(?:доступа|для\s+получения|получения|письма)|доступ\s*код)",
    re.I,
)
TRACK_CONTEXT_RE = re.compile(r"(трек|идентификатор|почтов|шпи|штрих)", re.I)
CODE_CONTEXT_RE = re.compile(r"(\bкод\b|\bдоступ|\bполуч|\bписьм)", re.I)

TRACK_SEQ_RE = re.compile(r"8(?:[\s\u00a0-]*\d){13}")
CODE_SEQ_RE = re.compile(r"\d(?:[\s\u00a0-]*\d){7}")


@dataclass
class _NumberCandidate:
    value: str
    start: int
    end: int
    score: int


_pdfminer_available = _has_module("pdfminer.high_level")
if _pdfminer_available:
    from pdfminer.high_level import extract_text
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdfdocument import PDFDocument
else:  # pragma: no cover - exercised via fallback branches
    extract_text = None  # type: ignore
    PDFPage = PDFParser = PDFDocument = None  # type: ignore

_pdf2image_available = _has_module("pdf2image")
_pytesseract_available = _has_module("pytesseract")
if _pdf2image_available:
    from pdf2image import convert_from_path
else:  # pragma: no cover - exercised via fallback branches
    convert_from_path = None  # type: ignore

if _pytesseract_available:
    import pytesseract
else:  # pragma: no cover - exercised via fallback branches
    pytesseract = None  # type: ignore

OCR_AVAILABLE = _pdf2image_available and _pytesseract_available

if os.name == "nt" and pytesseract is not None:
    tp = os.environ.get("TESSERACT_PATH")
    if not tp or not os.path.exists(tp):
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        cand = base / "tesseract" / "Tesseract-OCR" / "tesseract.exe"
        if not cand.exists():
            cand = base / "Tesseract-OCR" / "tesseract.exe"
        if cand.exists():
            tp = str(cand)
    if tp and os.path.exists(tp):
        pytesseract.pytesseract.tesseract_cmd = tp


def extract_page_text_pdfminer(pdf_path: Path, pidx: int) -> str:
    if not _pdfminer_available or extract_text is None:
        return ""
    try:
        return extract_text(str(pdf_path), page_numbers=[pidx]) or ""
    except Exception:
        return ""


def extract_page_text_ocr(pdf_path: Path, pidx: int, dpi: int = 300, lang: str = "rus+eng") -> str:
    if not OCR_AVAILABLE or convert_from_path is None or pytesseract is None:
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
    if _pdfminer_available and PDFParser and PDFDocument and PDFPage:
        try:
            with open(pdf_path, "rb") as f:
                parser = PDFParser(f)
                doc = PDFDocument(parser)
                return sum(1 for _ in PDFPage.create_pages(doc))
        except Exception:
            pass
    if convert_from_path is not None:
        try:
            convert_from_path(str(pdf_path), first_page=1, last_page=1)
            return 2
        except Exception:
            pass
    return 1


def _extract_line_context(text: str, start: int, end: int) -> Tuple[str, str, str]:
    """Return the line containing the span together with its neighbours."""
    line_start = text.rfind("\n", 0, start)
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    line_text = text[line_start:line_end]

    prev_line = ""
    if line_start > 0:
        prev_end = line_start - 1
        prev_start = text.rfind("\n", 0, prev_end)
        if prev_start == -1:
            prev_start = 0
        else:
            prev_start += 1
        prev_line = text[prev_start:prev_end]

    next_line = ""
    if line_end < len(text):
        next_start = line_end + 1
        next_end = text.find("\n", next_start)
        if next_end == -1:
            next_end = len(text)
        next_line = text[next_start:next_end]

    return line_text, prev_line, next_line


def _match_after_label(segment: str, start_idx: int, seq_re: re.Pattern, expected_len: int, base_score: int) -> Optional[_NumberCandidate]:
    window = segment[start_idx:start_idx + 500]
    m = seq_re.search(window)
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group())
    if len(digits) != expected_len:
        return None
    if expected_len == 14 and not re.fullmatch(TRACK14, digits):
        return None
    return _NumberCandidate(digits, start_idx + m.start(), start_idx + m.end(), base_score)


def _dedup_candidates(candidates: List[_NumberCandidate]) -> List[_NumberCandidate]:
    ordered = sorted(candidates, key=lambda c: (-c.score, c.start, c.end, c.value))
    seen = set()
    result: List[_NumberCandidate] = []
    for cand in ordered:
        key = (cand.value, cand.start, cand.end)
        if key in seen:
            continue
        seen.add(key)
        result.append(cand)
    return result


def _choose_best_pair(tracks: List[_NumberCandidate], codes: List[_NumberCandidate]):
    best_pair = None
    best_key = (-1, -1, -1)
    for t in tracks:
        for c in codes:
            if c.start < t.end and c.end > t.start:
                continue
            if c.start >= t.end:
                gap = c.start - t.end
            else:
                gap = t.start - c.end
            if gap > 350:
                continue
            order_bonus = 1 if t.start <= c.start else 0
            score_key = (t.score + c.score, order_bonus, -gap)
            if score_key > best_key:
                best_key = score_key
                best_pair = (t.value, c.value)
    return best_pair


def sniff_track_code_with_labels(text: str):
    t = text.replace("\xa0", " ").replace("\u202f", " ")

    segments = []
    logo_matches = list(LOGO_RE.finditer(t))
    if logo_matches:
        tail = t[logo_matches[-1].end():]
        if tail.strip():
            segments.append(tail)
    segments.append(t)

    best_track = None
    best_code = None
    best_track_score = -1
    best_code_score = -1

    for segment in segments:
        if not segment.strip():
            continue
        track_candidates: List[_NumberCandidate] = []
        code_candidates: List[_NumberCandidate] = []
        track_spans: List[Tuple[int, int]] = []

        for match in TRACK_LABEL_RE.finditer(segment):
            cand = _match_after_label(segment, match.end(), TRACK_SEQ_RE, 14, 4)
            if cand:
                track_candidates.append(cand)
                track_spans.append((cand.start, cand.end))

        for match in CODE_LABEL_RE.finditer(segment):
            cand = _match_after_label(segment, match.end(), CODE_SEQ_RE, 8, 4)
            if cand:
                code_candidates.append(cand)

        for match in TRACK_SEQ_RE.finditer(segment):
            digits = re.sub(r"\D", "", match.group())
            if not re.fullmatch(TRACK14, digits):
                continue
            start, end = match.start(), match.end()
            context = segment[max(0, start - 80):min(len(segment), end + 80)]
            score = 1
            if TRACK_LABEL_RE.search(context):
                score = 4
            elif TRACK_CONTEXT_RE.search(context):
                score = 2
            track_candidates.append(_NumberCandidate(digits, start, end, score))
            track_spans.append((start, end))

        for match in CODE_SEQ_RE.finditer(segment):
            digits = re.sub(r"\D", "", match.group())
            if len(digits) != 8:
                continue
            start, end = match.start(), match.end()
            if any(start >= ts and end <= te for ts, te in track_spans):
                continue
            context = segment[max(0, start - 80):min(len(segment), end + 80)]
            if not CODE_CONTEXT_RE.search(context):
                continue
            line_text, prev_line, next_line = _extract_line_context(segment, start, end)
            line_has_code_kw = bool(CODE_CONTEXT_RE.search(line_text))
            nearby_code_kw = line_has_code_kw or bool(CODE_CONTEXT_RE.search(prev_line)) or bool(CODE_CONTEXT_RE.search(next_line))
            if not nearby_code_kw:
                continue
            if TRACK_CONTEXT_RE.search(line_text) and not line_has_code_kw:
                continue
            score = 2
            if CODE_LABEL_RE.search(line_text) or CODE_LABEL_RE.search(prev_line):
                score = 5
            elif CODE_LABEL_RE.search(next_line):
                score = max(score, 5)
            elif line_has_code_kw:
                score = 4
            elif CODE_CONTEXT_RE.search(prev_line) or CODE_CONTEXT_RE.search(next_line):
                score = 3
            code_candidates.append(_NumberCandidate(digits, start, end, score))

        track_candidates = _dedup_candidates(track_candidates)
        code_candidates = _dedup_candidates(code_candidates)

        pair = _choose_best_pair(track_candidates, code_candidates)
        if pair:
            return pair

        if track_candidates and track_candidates[0].score > best_track_score:
            best_track = track_candidates[0].value
            best_track_score = track_candidates[0].score
        if code_candidates and code_candidates[0].score > best_code_score:
            best_code = code_candidates[0].value
            best_code_score = code_candidates[0].score

    return best_track, best_code


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

