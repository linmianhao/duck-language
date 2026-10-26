from ducklang.lexicon import Lexicon, Phrasebook
from ducklang.reverse import reverse


def test_lexicon_is_valid():
    assert Lexicon.load().validate() == []


def test_phrasebook_is_valid():
    lexicon = Lexicon.load()
    assert Phrasebook.load().validate(lexicon) == []


def test_lexicon_is_small_and_bidirectional():
    lexicon = Lexicon.load()
    assert 50 <= len(lexicon.words) <= 90
    for word in lexicon.words:
        assert lexicon.lookup_duck(word.duck) is word
        for gloss in word.glosses:
            assert lexicon.lookup(gloss) is word


def test_placeholders_exist():
    lexicon = Lexicon.load()
    assert lexicon.placeholder_noun is not None
    assert lexicon.placeholder_verb is not None


def test_every_phrase_reverses_to_its_own_entry():
    lexicon, phrasebook = Lexicon.load(), Phrasebook.load()
    for phrase in phrasebook.phrases:
        zh = reverse(phrase.duck, lexicon=lexicon, phrasebook=phrasebook).zh
        assert zh.rstrip("。！？，") == phrase.zh[0]


def test_nearest_word_correction():
    lexicon = Lexicon.load()
    assert lexicon.nearest("kaakaa").zh == "危险"
    assert lexicon.nearest("kokikoki") is None
