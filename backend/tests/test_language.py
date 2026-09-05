"""Script detection."""
import pytest

from app.services.language import Script, bengali_ratio, detect_script, uses_bengali


@pytest.mark.parametrize(
    "text,expected",
    [
        ("How hard should I exercise?", Script.LATIN),
        ("আমি কি হাঁটতে পারব?", Script.BENGALI),
        ("বুকে ব্যথা হচ্ছে", Script.BENGALI),
        ("", Script.UNKNOWN),
        ("123 456", Script.UNKNOWN),
    ],
)
def test_detect_script(text, expected):
    assert detect_script(text) == expected


def test_code_switched_text_is_mixed():
    """Bangla-English code switching is the norm, not an edge case."""
    assert detect_script("আমার chest pain হচ্ছে") == Script.MIXED
    assert uses_bengali("আমার chest pain হচ্ছে")


def test_english_with_one_stray_character_is_still_english():
    assert detect_script("Can I exercise today ব") == Script.LATIN


def test_bengali_ratio_is_computed_over_letters_only():
    assert bengali_ratio("বুকে ব্যথা 120/80") == pytest.approx(1.0)
    assert bengali_ratio("chest pain 120/80") == 0.0


def test_uses_bengali_covers_both_bengali_and_mixed():
    assert uses_bengali("বুকে ব্যথা")
    assert not uses_bengali("chest pain")
