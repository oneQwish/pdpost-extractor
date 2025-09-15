from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rp_extractor import sniff_track_code_with_labels

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_sniff_with_clear_labels():
    text = (
        "Железнодорожный городской суд Московской области\n"
        "ПОЧТА РОССИИ\n"
        "Почтовый идентификатор: 8006 5036 2850 04\n"
        "Код доступа: 1234 5678\n"
    )
    track, code = sniff_track_code_with_labels(text)
    assert track == "80065036285004"
    assert code == "12345678"


def test_sniff_prefers_last_logo_region():
    text = (
        "ИНН 7712345678\n"
        "Код доступа: 1111 2222\n"
        "ПОЧТА РОССИИ\n"
        "Почтовый идентификатор: 8006 5036 2850 04\n"
        "Код доступа: 8765 4321\n"
    )
    track, code = sniff_track_code_with_labels(text)
    assert track == "80065036285004"
    assert code == "87654321"


def test_sniff_without_logo_still_detects():
    text = (
        "Судебное отправление\n"
        "Почтовый идентификатор 8006 5036 2850 04\n"
        "Код доступа 1478 5236\n"
    )
    track, code = sniff_track_code_with_labels(text)
    assert track == "80065036285004"
    assert code == "14785236"


def test_sniff_returns_partial_when_code_missing():
    text = (
        "ПОЧТА РОССИИ\n"
        "Почтовый идентификатор: 8006 5036 2850 04\n"
        "Адрес: Московская обл., Балашиха, ул. Зеленая, д. 10\n"
    )
    track, code = sniff_track_code_with_labels(text)
    assert track == "80065036285004"
    assert code is None


def test_sniff_handles_track_without_label():
    text = (
        "ПОЧТА РОССИИ\n"
        "8006 5036 2850 04\n"
        "Код доступа: 2345 6789\n"
    )
    track, code = sniff_track_code_with_labels(text)
    assert track == "80065036285004"
    assert code == "23456789"


def test_sniff_with_real_ocr_text_from_attachment():
    text = (FIXTURES / "letter_image2_ocr.txt").read_text(encoding="utf-8")
    track, code = sniff_track_code_with_labels(text)
    assert track == "80099008576514"
    assert code == "54769201"


def test_sniff_with_blank_attachment_text():
    text = (FIXTURES / "blank_page_ocr.txt").read_text(encoding="utf-8")
    track, code = sniff_track_code_with_labels(text)
    assert track is None
    assert code is None


def test_sniff_handles_shpi_and_pickup_phrase():
    text = (
        "Балашихинский городской суд Московской области\n"
        "ПОЧТА РОССИИ\n"
        "ШПИ 8009 9008 5765 14\n"
        "Код для получения:\n"
        "5476 9201\n"
        "Получайте и отправляйте письма онлайн.\n"
    )
    track, code = sniff_track_code_with_labels(text)
    assert track == "80099008576514"
    assert code == "54769201"


def test_sniff_detects_code_with_label_on_previous_line():
    text = (
        "ПОЧТА РОССИИ\n"
        "Трек-номер\n"
        "8000 1234 5678 90\n"
        "Код письма\n"
        "1122 3344\n"
    )
    track, code = sniff_track_code_with_labels(text)
    assert track == "80001234567890"
    assert code == "11223344"
