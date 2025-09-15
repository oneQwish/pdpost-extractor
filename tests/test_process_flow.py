import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rp_extractor


def _make_pdf(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.4\n")
    return path


def test_process_pdf_uses_ocr_when_text_short(tmp_path, monkeypatch):
    pdf = _make_pdf(tmp_path, "short.pdf")

    monkeypatch.setattr(rp_extractor, "get_page_count", lambda _: 1)
    monkeypatch.setattr(rp_extractor, "extract_page_text_pdfminer", lambda *_: "too short")

    def fake_sniff(text: str):
        if text.startswith("ocr"):
            return "80065036285004", "12345678"
        return None, None

    ocr_calls = []

    def fake_ocr(*_args, **_kwargs):
        ocr_calls.append(_args[1])
        return "ocr text"

    monkeypatch.setattr(rp_extractor, "sniff_track_code_with_labels", fake_sniff)
    monkeypatch.setattr(rp_extractor, "extract_page_text_ocr", fake_ocr)

    res = rp_extractor.process_pdf(
        pdf,
        max_pages_back=5,
        min_chars_for_ocr=200,
        enable_ocr=True,
        force_ocr=False,
        cancel_cb=None,
        ocr_dpi=300,
        ocr_lang="rus+eng",
    )

    assert res["track"] == "80065036285004"
    assert res["code"] == "12345678"
    assert res["method"] == "ocr"
    assert ocr_calls  # OCR was invoked


def test_process_pdf_skips_ocr_when_text_sufficient(tmp_path, monkeypatch):
    pdf = _make_pdf(tmp_path, "long.pdf")

    monkeypatch.setattr(rp_extractor, "get_page_count", lambda _: 1)
    monkeypatch.setattr(rp_extractor, "extract_page_text_pdfminer", lambda *_: "x" * 500)
    monkeypatch.setattr(rp_extractor, "sniff_track_code_with_labels", lambda *_: (None, None))

    def fake_ocr(*_args, **_kwargs):
        raise AssertionError("OCR should not be triggered when text is sufficient")

    monkeypatch.setattr(rp_extractor, "extract_page_text_ocr", fake_ocr)

    res = rp_extractor.process_pdf(
        pdf,
        max_pages_back=5,
        min_chars_for_ocr=200,
        enable_ocr=True,
        force_ocr=False,
        cancel_cb=None,
        ocr_dpi=300,
        ocr_lang="rus+eng",
    )

    assert res["track"] is None
    assert res["code"] is None
    assert res["method"] == ""


def test_process_pdf_files_parallel_order_preserved(tmp_path, monkeypatch):
    pdfs = [_make_pdf(tmp_path, name) for name in ("a.pdf", "b.pdf", "c.pdf")]

    def fake_process(pdf_path: Path, **_kwargs):
        if pdf_path.name == "a.pdf":
            time.sleep(0.05)
        elif pdf_path.name == "c.pdf":
            time.sleep(0.01)
        return {
            "source": pdf_path.name,
            "track": pdf_path.stem.upper(),
            "code": "CODE",
            "method": "text",
        }

    monkeypatch.setattr(rp_extractor, "process_pdf", fake_process)

    progress = []
    results = rp_extractor.process_pdf_files(
        pdfs,
        workers=3,
        process_kwargs={"cancel_cb": None},
        cancel_file=None,
        progress_cb=lambda rec: progress.append(rec["source"]),
    )

    assert [rec["source"] for rec in results] == [p.name for p in pdfs]
    assert set(progress) == {p.name for p in pdfs}


def test_process_pdf_files_respects_cancel_file(tmp_path, monkeypatch):
    pdfs = [_make_pdf(tmp_path, name) for name in ("one.pdf", "two.pdf")]
    cancel_path = tmp_path / "stop.flag"
    cancel_path.write_text("stop")

    called = []

    def fake_process(*_args, **_kwargs):
        called.append(True)
        return {"source": "x", "track": None, "code": None, "method": "text"}

    monkeypatch.setattr(rp_extractor, "process_pdf", fake_process)

    results = rp_extractor.process_pdf_files(
        pdfs,
        workers=2,
        process_kwargs={"cancel_cb": str(cancel_path)},
        cancel_file=str(cancel_path),
    )

    assert results == []
    assert called == []
