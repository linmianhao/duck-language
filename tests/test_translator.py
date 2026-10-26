import pytest

from ducklang.phonology import validate_text
from ducklang.translator import UnknownWordError, translate

GOLDEN = {
    # 短语库
    "你好吗？": "wa wi ki?",
    "我饿了": "ka wakaa kii。",
    "我喜欢你": "ka wa wiwa。",
    "危险！": "kaakaa!",
    # 规则引擎
    "你吃了吗？": "wa waka koo ki?",
    "明天要下雨": "kiwoo waako kiko。",
    "这里很危险": "wo kaakaa!",
    "我们去水边吧": "kaka waa woko wiiko。",
    "我要吃鱼": "ka waawi kii waka。",
    "我想喝水": "ka waa kii waki。",
    "你会游泳吗？": "wa wakoo kiko ki?",
    "我看见一只大鱼": "ka waawi koowa kiwi。",
    "谁在家？": "kika woowa woko ki?",
    "你去哪里？": "wa kiwo wiiko ki?",
    "你什么时候来？": "wa kikoo wiki ki?",
    "我是鸭子": "ka kaa kowi。",
    "这是什么？": "wo kiwa kowi ki?",
    "你给我食物": "wa ka wakaa wika。",
    "我和你去玩": "ka wa kowo wiiko woka。",
    "别去": "ko wiiko!",
    "快跑！": "kiika wiiko!",
    "我很冷": "ka kooki。",
    "我不饿": "ka ko wakaa kii。",
    "你渴吗？": "wa waa kii ki?",
    "下雨了": "waako koo。",
    "两只鸭": "kaa koowo。",
    "鸭子们": "kaa koowo。",
    "我不在家": "ka ko woowa woko。",
    "鱼在水里": "waawi waa woko。",
    "我没吃饭": "ka wakaa ko waka koo。",
    "他没来": "kowa ko wiki koo。",
    "我没有食物": "ka wakaa ko kawa。",
    "他们是谁？": "kowa kowa kika kowi ki?",
    "我们明天去河边玩": "kiwoo kaka waa woko wiiko woka。",
    "小鸭子很开心": "kiiwa wiwaa。",
    "我饿了，我们去吃饭吧": "ka wakaa kii, kaka wakaa wiiko waka。",
    "因为下雨，我们不去": "waako, kaka ko wiiko。",
    "我饿了。你好吗？": "ka wakaa kii。 wa wi ki?",
}


@pytest.mark.parametrize(("text", "expected"), GOLDEN.items())
def test_golden_translations(text, expected):
    result = translate(text)
    assert result.duck == expected
    assert not result.warnings
    validate_text(result.duck)


def test_gloss():
    assert translate("你吃了吗？").gloss == "你 吃 了 吗"


def test_unknown_noun_becomes_placeholder():
    result = translate("我喝咖啡")
    assert result.duck == "ka waawo waki。"
    assert any("咖啡" in w for w in result.warnings)


def test_unknown_subject_becomes_person():
    result = translate("张三来了")
    assert result.duck == "wowa wiki koo。"
    assert result.warnings


def test_numbers_inside_names_are_not_numbers():
    assert "koowo" not in translate("张三来了").duck


def test_strict_mode_rejects_unknown_word():
    with pytest.raises(UnknownWordError):
        translate("我喝咖啡", strict=True)


def test_empty_input_rejected():
    with pytest.raises(ValueError):
        translate("   ")
