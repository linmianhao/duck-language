import pytest

from ducklang.phonology import validate_text
from ducklang.translator import UnknownWordError, loanwordize, translate

GOLDEN = {
    "你好吗？": "na wi ha?",
    "我饿了": "ma mam ʔi。",
    "我喜欢你": "ma na wi。",
    "你吃了吗？": "na num ko ha?",
    "我们去水边": "mama wa ki ba。",
    "危险！": "kak!",
    "明天要下雨": "ʔo-wa ba。",
    "这里很危险": "ti kak。",
    "你是谁？": "na ʔa-kwa ha?",
    "我不冷": "ma ʔu pim。",
    "我没有食物": "ma mam ʔu。",
    "回家": "nu ki ba。",
    "这是什么？": "ti ʔa ha?",
    "你去哪里？": "na ʔa-ki ba ha?",
    "我想喝水": "ma wa num ba。",
    "你会游泳吗？": "na ʔwa kan ha?",
    "别去": "ʔu ba。",
    "水里有鸭": "wa ki kwa。",
    "两只鸭": "ʔok-ʔok kwa。",
    "大鸭": "po kwa。",
    "我的朋友是鸭": "ma mik kwa。",
    "我不在水里": "ma wa ki ʔu。",
    "我有一只鸭": "ma ʔok kwa ki。",
    "今天天气好": "ti-ʔo wi。",
    "我饿了，想吃饭": "ma mam ʔi, mam num ba。",
    "因为下雨，我们不去": "ʔo-wa, mama ʔu ba。",
    "我没有吃": "ma ʔu num ko。",
    "我没有吃饭": "ma mam ʔu num ko。",
    "他没来": "ta ʔu ba ko。",
    "我不能吃": "ma ʔu num kan。",
    "我不吃": "ma ʔu num。",
    "我饿了。你好吗？": "ma mam ʔi。 na wi ha?",
    "我饿了。我喜欢你。": "ma mam ʔi。 ma na wi。",
    "我喜欢吃鱼": "ma nam num wi。",
    "我喜欢睡觉": "ma ʔum wi。",
    "我喜欢去水里": "ma wa ki ba wi。",
}


@pytest.mark.parametrize(("text", "expected"), GOLDEN.items())
def test_golden_translations(text, expected):
    result = translate(text)
    assert result.duck == expected
    validate_text(result.duck)


def test_gloss_is_not_empty():
    result = translate("你吃了吗？")
    assert result.gloss == "你 吃 了 吗"


def test_unknown_word_is_loanwordized():
    result = translate("我喝咖啡")
    assert "kwaʔ" in result.duck
    assert result.warnings
    validate_text(result.duck)


def test_strict_mode_rejects_unknown_word():
    with pytest.raises(UnknownWordError):
        translate("我喝咖啡", strict=True)


def test_loanwordize_uses_valid_syllables():
    duck = loanwordize("咖啡")
    assert duck.startswith("kwaʔ-")
    validate_text(duck)


def test_empty_input_rejected():
    with pytest.raises(ValueError):
        translate("   ")
