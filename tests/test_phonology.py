import pytest

from ducklang.phonology import (
    ALL_SYLLABLES,
    feature_distance,
    parse_text,
    parse_word,
    validate_text,
)


def test_twelve_syllables():
    texts = {s.text for s in ALL_SYLLABLES}
    assert len(texts) == 12
    assert texts == {
        "ka", "ki", "ko", "kaa", "kii", "koo", "wa", "wi", "wo", "waa", "wii", "woo",
    }


def test_parse_compound_word_is_unambiguous():
    syllables = parse_word("kiiwa")
    assert [s.text for s in syllables] == ["kii", "wa"]
    assert syllables[0].features == ("k", "i", True)
    assert syllables[1].description == "暗降短"


def test_parse_text_ignores_punctuation():
    assert [s.text for s in parse_text("wa wi ki?")] == ["wa", "wi", "ki"]


@pytest.mark.parametrize("bad", ["ma", "kaaa", "kwa", "ʔo", "kak", "k"])
def test_invalid_words_raise(bad):
    with pytest.raises(ValueError):
        parse_word(bad)


def test_feature_distance():
    assert feature_distance("ka", "ka") == 0
    assert feature_distance("ka", "wa") == 1
    assert feature_distance("ka", "wii") == 3
    assert feature_distance("ka", "kawa") == 99


def test_known_sentences_are_valid():
    for text in ("ka wakaa kii。", "wa waka koo ki?", "kaakaa!", "kowa kowa kika kowi ki?"):
        validate_text(text)
