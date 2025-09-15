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
from typing import Callable, Optional, Dict, List, Tuple, Union

logger = logging.getLogger("rp_extractor")

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


def _configure_logging(log_path: str) -> None:
    if not log_path:
        return
    try:
        path = Path(log_path)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
    except Exception:
        logger.exception("Failed to configure logging to %s", log_path)

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


def _coerce_cancel_callback(cancel_cb: Optional[Union[Callable[[], bool], str, os.PathLike]]) -> Optional[Callable[[], bool]]:
    if cancel_cb is None:
        return None
    if callable(cancel_cb):
        return cancel_cb
    path = Path(cancel_cb)

    def _check() -> bool:
        try:
            return path.exists()
        except Exception:
            return False

    return _check


def _dump_debug_text(pdf_path: Path, page_idx: int, kind: str, text: str) -> None:
    if not DEBUG_DUMP_DIR or not text:
        return
    try:
        base = Path(DEBUG_DUMP_DIR)
        base.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", pdf_path.stem)
        out = base / f"{safe_name}_p{page_idx + 1}_{kind}_{os.getpid()}.txt"
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
    except Exception:
        logger.debug("Failed to dump debug text for %s page %s", pdf_path, page_idx + 1, exc_info=True)


def _should_cancel(cancel_file: Optional[Union[str, os.PathLike]]) -> bool:
    if not cancel_file:
        return False
    try:
        return Path(cancel_file).exists()
    except Exception:
        return False


def process_pdf_files(pdfs: List[Path],
                      workers: int,
                      process_kwargs: Dict[str, object],
                      cancel_file: Optional[Union[str, os.PathLike]] = None,
                      progress_cb: Optional[Callable[[Dict[str, Optional[str]]], None]] = None
                      ) -> List[Dict[str, Optional[str]]]:
    if not pdfs:
        return []
    if _should_cancel(cancel_file):
        return []
    results: Dict[int, Dict[str, Optional[str]]] = {}
    max_workers = workers if isinstance(workers, int) else 1
    if max_workers <= 0:
        cpu = os.cpu_count() or 1
        max_workers = max(1, cpu)
    max_workers = min(max_workers, len(pdfs))

    def _handle_result(idx: int, record: Dict[str, Optional[str]]):
        results[idx] = record
        if progress_cb:
            try:
                progress_cb(record)
            except Exception:
                logger.debug("Progress callback failed for %s", record.get("source"), exc_info=True)

    if max_workers == 1:
        for idx, pdf in enumerate(pdfs):
            if _should_cancel(cancel_file):
                break
            try:
                rec = process_pdf(pdf, **process_kwargs)
            except Exception:
                logger.exception("Failed to process %s", pdf)
                rec = {"source": pdf.name, "track": None, "code": None, "method": "error"}
            _handle_result(idx, rec)
            if rec.get("method") == "canceled":
                break
    else:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        futures: Dict[concurrent.futures.Future, int] = {}
        try:
            for idx, pdf in enumerate(pdfs):
                if _should_cancel(cancel_file):
                    break
                future = executor.submit(process_pdf, pdf, **process_kwargs)
                futures[future] = idx
            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                try:
                    rec = future.result()
                except Exception:
                    logger.exception("Failed to process %s", pdfs[idx])
                    rec = {"source": pdfs[idx].name, "track": None, "code": None, "method": "error"}
                _handle_result(idx, rec)
                if rec.get("method") == "canceled" or _should_cancel(cancel_file):
                    break
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    ordered = [results[idx] for idx in sorted(results)]
    return ordered


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
    cancel_fn = _coerce_cancel_callback(cancel_cb)
    ocr_threshold = max(0, int(min_chars_for_ocr or 0))
    total_pages = max(1, get_page_count(pdf_path))
    pages = list(range(total_pages-1, -1, -1))
    if max_pages_back > 0: pages = pages[:max_pages_back]

    for pidx in pages:
        if cancel_fn and cancel_fn():
            res["method"] = "canceled"
            return res
        tr = cd = None
        txt = ""
        method = ""
        if not force_ocr:
            txt = extract_page_text_pdfminer(pdf_path, pidx)
            if txt:
                _dump_debug_text(pdf_path, pidx, "text", txt)
            tr, cd = sniff_track_code_with_labels(txt)
            if tr and cd:
                method = "text"
        need_ocr = False
        if enable_ocr:
            if force_ocr:
                need_ocr = True
            elif (not tr or not cd) and len(txt) < ocr_threshold:
                need_ocr = True
        if need_ocr:
            ocr_txt = extract_page_text_ocr(pdf_path, pidx, dpi=ocr_dpi, lang=ocr_lang)
            if ocr_txt:
                _dump_debug_text(pdf_path, pidx, "ocr", ocr_txt)
                tr2, cd2 = sniff_track_code_with_labels(ocr_txt)
                if tr2 and cd2:
                    tr, cd = tr2, cd2
                    method = "ocr"
        if tr and cd:
            res.update(track=tr, code=cd, method=method)
            return res
    return res


def walk_pdfs(path: Path):
    if path.is_file() and path.suffix.lower()==".pdf": return [path]
    return sorted(p for p in path.rglob("*.pdf") if p.is_file())


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

    if args.log:
        _configure_logging(args.log)

    global DEBUG_DUMP_DIR
    DEBUG_DUMP_DIR = str(Path(args.debug_dump_text).expanduser()) if args.debug_dump_text else None

    pdfs = walk_pdfs(Path(args.input))
    total = len(pdfs)
    cancel_file = args.cancel_file or None
    if args.progress_stdout:
        print(json.dumps({"event": "start", "total": total}), flush=True)

    enable_ocr = (not args.no_ocr) or args.force_ocr
    process_kwargs = {
        "max_pages_back": args.max_pages_back,
        "min_chars_for_ocr": args.min_chars_for_ocr,
        "enable_ocr": enable_ocr,
        "cancel_cb": cancel_file,
        "force_ocr": args.force_ocr,
        "ocr_dpi": args.dpi,
        "ocr_lang": args.lang,
    }

    progress_cb = None
    if args.progress_stdout:
        def progress_cb(rec: Dict[str, Optional[str]]):
            evt = {
                "event": "progress",
                "file": rec.get("source"),
                "track": rec.get("track"),
                "code": rec.get("code"),
                "method": rec.get("method"),
            }
            print(json.dumps(evt, ensure_ascii=False), flush=True)

    results = process_pdf_files(
        pdfs,
        workers=args.workers,
        process_kwargs=process_kwargs,
        cancel_file=cancel_file,
        progress_cb=progress_cb,
    )

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

