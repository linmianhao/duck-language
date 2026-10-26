import pytest

from ducklang.reverse import reverse
from ducklang.translator import translate

GOLDEN = {
    "wa waka koo ki?": "你吃了吗？",
    "kiwoo waako kiko": "明天会下雨。",
    "kaka waa woko wiiko": "我们去水边。",
    "ka waawi kii waka": "我要吃鱼。",
    "kika woowa woko ki": "谁在家？",
    "wa kiwo wiiko ki": "你去哪里？",
    "wa kikoo wiki ki": "你什么时候来？",
    "wa ka wakaa wika": "你给我食物。",
    "ka wa kowo wiiko woka": "我和你去玩。",
    "ka wakaa ko waka koo": "我没吃食物。",
    "ka wakaa ko kawa": "我没有食物。",
    "ka ko kooki": "我不冷。",
    "wa waa kii ki": "你渴吗？",
    "ka waawi koowa kiwi": "我看大鱼。",
    "kaa koowo": "很多鸭。",
    "kowa kowa kika kowi ki": "他们是谁？",
    "kaakaa!": "危险！",
    "ka wakaa kii": "我饿了。",
    "ka wakaa kii, wa wi ki?": "我饿了，你好。",
}


@pytest.mark.parametrize(("duck", "expected"), GOLDEN.items())
def test_golden_reverse(duck, expected):
    assert reverse(duck).zh == expected


def test_unknown_and_invalid_words_warn_but_do_not_crash():
    result = reverse("ka kokikoki waka ma")
    assert any("kokikoki" in w for w in result.warnings)
    assert any("ma" in w and "非法" in w for w in result.warnings)
    assert result.zh


def test_tail_word_is_ignored():
    assert reverse("wa waka koo ki kakaka").zh == "你吃了吗？"


def test_empty_rejected():
    with pytest.raises(ValueError):
        reverse("  ")


ROUNDTRIP = [
    "我饿了", "你吃了吗？", "明天要下雨", "我们去水边吧", "我想喝水", "你会游泳吗？",
    "我看见一只大鱼", "谁在家？", "你去哪里？", "我是鸭子", "你给我食物", "我和你去玩",
    "不要走", "快跑！", "我很冷", "我不饿", "下雨了", "两只鸭", "我不在家", "鱼在水里",
    "这是什么？", "我没吃饭", "他没来", "我没有食物", "我饿了，我们去吃饭吧",
    "我们明天去河边玩", "小鸭子很开心", "你好", "天气很好", "我怕虫子", "你们在哪里？",
    "他们是谁？", "你渴吗？", "我快跑", "谁想吃虫子？", "你什么时候来？", "鸭子会游泳",
    "我在水里玩",
]


@pytest.mark.parametrize("text", ROUNDTRIP)
def test_roundtrip_is_stable(text):
    """中文 -> 鸭语 -> 中文 -> 鸭语，两次鸭语必须一致。"""
    duck = translate(text).duck
    assert translate(reverse(duck).zh).duck == duck
