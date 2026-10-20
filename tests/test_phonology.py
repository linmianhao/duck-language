from ducklang.phonology import parse_text, parse_word, validate_text


def test_parse_simple_word():
    syllables = parse_word("mama")
    assert [s.text for s in syllables] == ["ma", "ma"]


def test_parse_compound_and_glottal_stop():
    syllables = parse_word("kwaʔ-ʔo-wa")
    assert [s.text for s in syllables] == ["kwaʔ", "ʔo", "wa"]


def test_parse_question_punctuation_is_ignored():
    syllables = parse_text("na wi ha?")
    assert [s.text for s in syllables] == ["na", "wi", "ha"]


def test_invalid_syllable_raises():
    try:
        parse_word("sak")
    except ValueError:
        return
    raise AssertionError("sak should be invalid")


def test_known_sentences_are_valid():
    for text in (
        "ma mam ʔi。",
        "na num ko ha?",
        "ʔo-wa ba。",
        "ti kak!",
        "mama wa ki ba。",
        "ʔok-ʔok kwa。",
        "kwaʔ-ka-pe",
        "ti-ʔo wi。",
    ):
        validate_text(text)
