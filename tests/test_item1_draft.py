"""ITEM-1：抽取的输入是原文文本本身，模型调用可注入；草稿字段分离、名称唯一、篇幅门槛。

这些用例全部用假的模型调用函数，不访问网络，也不调用任何付费模型。
"""

import json
from pathlib import Path

import pytest

from storyweave import (
    人物可出页,
    人物身份字段,
    抽取草稿,
    抽取短篇草稿,
    整篇可出页,
    未跳过的未支持,
    构建抽取提示,
    名称重复,
    模型输出不可解析,
    计字,
    解析模型输出,
    草稿非法,
    校验篇幅,
    篇幅不符,
)

原文 = "阿明推开院门，屋里只剩一盏灯。他穿着一件旧棉袄。"


def _模型输出():
    """一份完整的模型输出。

    哨兵字符串互不包含，用来检查字段没有串写。
    人物里故意混入旧字段「脸」、外来字段「变身后样貌」和一个「另一身份」块：
    新契约只认六项身份字段，这些外来内容必须被丢掉。
    """
    return {
        "人物": [
            {
                "名称": "名称哨兵阿明",
                "身份": {
                    "脸型": "脸型哨兵鹅卵",
                    "发型与发色": "发型哨兵短黑",
                    "眼": "眼哨兵细长",
                    "显著特征": "特征哨兵左眉疤",
                    "年龄": "年龄哨兵十七",
                    "体态": "体态哨兵清瘦",
                    "脸": "旧版脸哨兵",
                },
                "原文起": 0,
                "原文止": 8,
                "服装": [
                    {
                        "名称": "服装名哨兵",
                        "描述": "服装描述哨兵深蓝",
                        "原文起": 9,
                        "原文止": 14,
                        "确认状态": "已确认",
                        "参考图": "参考图哨兵不该出现",
                    }
                ],
                "未支持": [],
                "变身后样貌": {"脸型": "变后脸哨兵兽"},
                "另一身份": {"脸型": "另一脸型哨兵兽", "年龄": "另一年龄哨兵兽"},
                "故事节拍": [{"摘要": "节拍摘要哨兵推门"}],
            }
        ],
        "场景": [
            {
                "名称": "场景名哨兵",
                "建筑外观": "场景外观哨兵砖",
                "原文起": 15,
                "原文止": 24,
                "确认状态": "已确认",
                "故事节拍": [{"摘要": "节拍摘要哨兵推门"}],
            }
        ],
        "风格ID": "风格哨兵水墨",
        "风格确认状态": "已确认",
        "故事节拍": [
            {"顺序": 1, "摘要": "节拍摘要哨兵推门", "原文起": 0, "原文止": 8},
            {"顺序": 2, "摘要": "节拍摘要哨兵离校", "原文起": 9, "原文止": 24},
        ],
        "无主线索": [],
    }


def _模型(输出=None, 记录=None, 原样文本=None):
    """造一个可注入的假模型：返回结构化 JSON 文本，并把收到的提示记下来。"""

    def 调用模型(提示):
        if 记录 is not None:
            记录.append(提示)
        if 原样文本 is not None:
            return 原样文本
        return json.dumps(_模型输出() if 输出 is None else 输出, ensure_ascii=False)

    return 调用模型


def _键集合(值):
    找到 = set()
    if isinstance(值, dict):
        找到.update(值)
        for 子 in 值.values():
            找到 |= _键集合(子)
    elif isinstance(值, list):
        for 子 in 值:
            找到 |= _键集合(子)
    return 找到


def test_抽取草稿的输入是原文本身而不是外部给定的结构化结果():
    记录 = []
    草稿 = 抽取草稿(原文, _模型(记录=记录))

    assert len(记录) == 1
    提示 = 记录[0]
    assert 原文 in 提示, "抽取提示里必须有原文全文"
    assert 提示.index(原文) > 提示.index("故事节拍"), "原文全文拼在提示末尾"
    assert "无主线索" in 提示
    assert "未支持" in 提示
    for 字段 in 人物身份字段:
        assert 字段 in 提示
    assert 草稿["人物卡"][0]["名称"] == "名称哨兵阿明"


def test_顶层键正好是契约字段且没有旧版的未支持命中():
    草稿 = 抽取草稿(原文, _模型())
    assert set(草稿) == {"人物卡", "场景卡", "风格ID", "故事节拍", "无主线索"}
    assert "未支持命中" not in 草稿
    assert 草稿["无主线索"] == []
    assert 整篇可出页(草稿) is True


def test_四个块分属不同字段且互不串写():
    草稿 = 抽取草稿(原文, _模型())

    卡 = 草稿["人物卡"][0]
    assert set(卡) == {"名称", "人物身份", "原文位置", "服装状态列表", "未支持"}
    assert 卡["名称"] == "名称哨兵阿明"
    assert 卡["原文位置"] == {"起": 0, "止": 8}

    身份 = 卡["人物身份"]
    assert "服装状态列表" not in 身份
    assert "场景卡" not in 卡
    assert "风格ID" not in 卡
    assert "故事节拍" not in 卡

    服装 = 卡["服装状态列表"][0]
    assert set(服装) == {"名称", "描述", "原文位置", "确认状态"}
    assert 服装["确认状态"] == "未确认"
    assert 服装["名称"] == "服装名哨兵"
    assert 服装["描述"] == "服装描述哨兵深蓝"
    assert 服装["原文位置"] == {"起": 9, "止": 14}

    场景 = 草稿["场景卡"][0]
    assert set(场景) == {"名称", "建筑外观", "原文位置", "确认状态"}
    assert 场景["确认状态"] == "未确认"
    assert 场景["名称"] == "场景名哨兵"
    assert 场景["建筑外观"] == "场景外观哨兵砖"
    assert 场景["原文位置"] == {"起": 15, "止": 24}

    风格 = 草稿["风格ID"]
    assert set(风格) == {"草稿", "确认状态"}
    assert 风格["草稿"] == "风格哨兵水墨"
    assert isinstance(风格["草稿"], str)
    assert 风格["确认状态"] == "未确认"

    assert 卡["未支持"] == []
    assert 人物可出页(卡) is True


def test_人物身份正好六个字段且缺省留空():
    输出 = _模型输出()
    del 输出["人物"][0]["身份"]["眼"]
    身份 = 抽取草稿(原文, _模型(输出))["人物卡"][0]["人物身份"]

    assert set(身份) == {"脸型", "发型与发色", "眼", "显著特征", "年龄", "体态"}
    assert 身份["脸型"] == "脸型哨兵鹅卵"
    assert 身份["发型与发色"] == "发型哨兵短黑"
    assert 身份["眼"] == "", "模型没给的身份字段留空"
    assert 身份["显著特征"] == "特征哨兵左眉疤"
    assert 身份["年龄"] == "年龄哨兵十七"
    assert 身份["体态"] == "体态哨兵清瘦"
    assert all(isinstance(值, str) for 值 in 身份.values())


def test_身份里不出现服装场景风格节拍和外来字段():
    草稿 = 抽取草稿(原文, _模型())
    卡 = 草稿["人物卡"][0]
    身份文 = json.dumps(卡["人物身份"], ensure_ascii=False)
    for 外来 in (
        "服装描述哨兵深蓝",
        "服装名哨兵",
        "场景外观哨兵砖",
        "场景名哨兵",
        "风格哨兵水墨",
        "节拍摘要哨兵推门",
        "旧版脸哨兵",
        "变后脸哨兵兽",
        "另一脸型哨兵兽",
        "另一年龄哨兵兽",
    ):
        assert 外来 not in 身份文

    服装文 = json.dumps(卡["服装状态列表"], ensure_ascii=False)
    for 外来 in ("脸型哨兵鹅卵", "场景外观哨兵砖", "风格哨兵水墨", "节拍摘要哨兵推门"):
        assert 外来 not in 服装文
    assert "已确认" not in 服装文

    场景文 = json.dumps(草稿["场景卡"], ensure_ascii=False)
    for 外来 in ("脸型哨兵鹅卵", "服装描述哨兵深蓝", "风格哨兵水墨", "节拍摘要哨兵推门"):
        assert 外来 not in 场景文

    风格文 = json.dumps(草稿["风格ID"], ensure_ascii=False)
    for 外来 in ("脸型哨兵鹅卵", "服装描述哨兵深蓝", "场景外观哨兵砖", "节拍摘要哨兵推门"):
        assert 外来 not in 风格文


def test_人物卡名称必须唯一():
    输出 = _模型输出()
    第二张 = json.loads(json.dumps(输出["人物"][0]))
    第二张["身份"] = dict.fromkeys(人物身份字段, "")
    输出["人物"].append(第二张)

    with pytest.raises(名称重复):
        抽取草稿(原文, _模型(输出))


def test_人物卡必须有名称():
    输出 = _模型输出()
    输出["人物"][0]["名称"] = ""
    with pytest.raises(草稿非法):
        抽取草稿(原文, _模型(输出))


def test_故事节拍带原文位置且不写进档案三块():
    草稿 = 抽取草稿(原文, _模型())
    节拍 = 草稿["故事节拍"]
    assert [条["顺序"] for 条 in 节拍] == [1, 2]
    assert 节拍[0] == {"顺序": 1, "摘要": "节拍摘要哨兵推门", "原文起": 0, "原文止": 8}
    assert 节拍[1] == {"顺序": 2, "摘要": "节拍摘要哨兵离校", "原文起": 9, "原文止": 24}

    for 块名 in ("人物卡", "场景卡", "风格ID"):
        块 = 草稿[块名]
        assert "故事节拍" not in _键集合(块)
        文 = json.dumps(块, ensure_ascii=False)
        assert "节拍摘要哨兵推门" not in 文
        assert "节拍摘要哨兵离校" not in 文


def test_节拍原文位置越界时判草稿非法():
    输出 = _模型输出()
    输出["故事节拍"][0]["原文止"] = len(原文) + 1
    with pytest.raises(草稿非法):
        抽取草稿(原文, _模型(输出))


def test_模型输出带代码围栏也能解析():
    文本 = "```json\n" + json.dumps(_模型输出(), ensure_ascii=False) + "\n```"
    草稿 = 抽取草稿(原文, _模型(原样文本=文本))
    assert 草稿["人物卡"][0]["名称"] == "名称哨兵阿明"


def test_模型输出不是合法JSON时拒绝():
    with pytest.raises(模型输出不可解析):
        抽取草稿(原文, _模型(原样文本="我觉得这个故事讲的是阿明推门。"))
    with pytest.raises(模型输出不可解析):
        解析模型输出("[1, 2, 3]")


def test_模型调用必须是可调用对象():
    with pytest.raises(TypeError):
        抽取草稿(原文, "这不是函数")
    with pytest.raises(TypeError):
        抽取草稿(123, _模型())


def test_模型返回非文本时拒绝():
    with pytest.raises(模型输出不可解析):
        抽取草稿(原文, lambda 提示: {"人物": []})


def test_纯函数可复现且不改输入():
    原样 = _模型输出()
    副本 = json.loads(json.dumps(原样))
    第一次 = 抽取草稿(原文, _模型(原样))
    第二次 = 抽取草稿(原文, _模型(原样))
    assert 原样 == 副本
    assert 第一次 == 第二次


def test_计字去掉空白():
    assert 计字("甲 乙\n丙\t丁") == 4
    assert 计字(" \n\t\u3000\u00a0") == 0


@pytest.mark.parametrize("字数", [10000, 20000])
def test_篇幅边界接受(字数):
    原文 = ("字" * 字数) + (" \n\t\u3000" * 10)
    assert 计字(原文) == 字数
    校验篇幅(原文)


@pytest.mark.parametrize("字数", [0, 9999, 20001])
def test_篇幅越界拒绝(字数):
    with pytest.raises(篇幅不符) as 捕获:
        校验篇幅("字" * 字数)
    assert 捕获.value.字数 == 字数


def test_空白不能把不足篇幅凑进范围():
    原文 = ("字" * 9999) + (" " * 5000) + "\n" * 20
    with pytest.raises(篇幅不符) as 捕获:
        校验篇幅(原文)
    assert 捕获.value.字数 == 9999


def test_评测样本那样的短节选也能抽取():
    """评测样本是原文节选，不受 1 万到 2 万字门槛约束，抽取本身不做篇幅门槛。"""
    节选 = "有人摇身一变，成了狼。"
    输出 = {
        "人物": [],
        "场景": [],
        "风格ID": "水墨",
        "故事节拍": [],
        "无主线索": [{"类别": "变身", "片段": 节选}],
    }
    assert 计字(节选) < 10000
    草稿 = 抽取草稿(节选, _模型(输出))
    assert len(草稿["无主线索"]) == 1


垫文 = "风从山那边吹过来，带着一点湿气。他站在门口，看着院子里的树影。"


def _铺到合格篇幅(核心: str = "") -> str:
    """用垫文把原文铺到合格篇幅。垫文里不出现任何未支持关键词。"""
    原文 = (垫文 * 500) + 核心
    assert 10000 <= 计字(原文) <= 20000, 计字(原文)
    return 原文


def test_正式入口对不足一万字的原文抛篇幅不符():
    节选 = "有人摇身一变，成了狼。"
    assert 计字(节选) < 10000
    with pytest.raises(篇幅不符) as 捕获:
        抽取短篇草稿(节选, _模型())
    assert 捕获.value.字数 == 计字(节选)


def test_正式入口对超过两万字的原文抛篇幅不符():
    原文 = "字" * 20001
    with pytest.raises(篇幅不符) as 捕获:
        抽取短篇草稿(原文, _模型())
    assert 捕获.value.字数 == 20001


def test_正式入口对合格篇幅抽出草稿():
    原文 = _铺到合格篇幅()
    草稿 = 抽取短篇草稿(原文, _模型())
    assert set(草稿) == {"人物卡", "场景卡", "风格ID", "故事节拍", "无主线索"}
    assert 草稿["人物卡"][0]["名称"] == "名称哨兵阿明"


def test_正式入口不先调模型就拦篇幅():
    记录 = []
    with pytest.raises(篇幅不符):
        抽取短篇草稿("太短了。", _模型(记录=记录))
    assert 记录 == [], "篇幅不合格时不应调用模型"


def test_不写页图也不写参考图(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)

    def _禁止打开(*args, **kwargs):
        raise AssertionError(f"不应打开文件: {args!r} {kwargs!r}")

    monkeypatch.setattr("builtins.open", _禁止打开)
    草稿 = 抽取草稿(原文, _模型())
    assert list(tmp_path.rglob("*")) == []
    文 = json.dumps(草稿, ensure_ascii=False).lower()
    for 痕迹 in (".png", ".jpg", ".jpeg", ".webp", ".pdf", "页图", "参考图", "样张", "分格"):
        assert 痕迹 not in 文


def test_抽取不访问网络(monkeypatch: pytest.MonkeyPatch):
    import socket

    def _禁止联网(*args, **kwargs):
        raise AssertionError("抽取不应访问网络")

    monkeypatch.setattr(socket, "socket", _禁止联网)
    monkeypatch.setattr(socket, "create_connection", _禁止联网)
    草稿 = 抽取草稿(原文, _模型())
    assert 草稿["人物卡"][0]["名称"] == "名称哨兵阿明"
