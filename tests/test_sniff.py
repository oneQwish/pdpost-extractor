from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rp_extractor import sniff_track_code_with_labels


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
