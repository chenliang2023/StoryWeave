"""ITEM-1 自带小评测集：样本覆盖、harness 评分、离线假模型（判 pass / 判 fail）。

全部用例用假模型，不访问网络，也不调用任何付费模型。
"""

import json

import pytest

from storyweave import 人物身份字段
from storyweave.eval_item1 import 样本文件, 跑评测集, 读样本

# 契约 ITEM-1 写明的必含样本，逐条核对原文与期望值。
必含样本 = [
    ("有人摇身一变，成了狼。", True, {}, []),
    ("她扮成鬼脸逗他笑。", False, {"她": "否"}, ["她"]),
    ("老师扮成圣诞老人来上课。", False, {"老师": "否"}, ["老师"]),
    ("她变成了一名少年。", False, {"她": "是"}, ["她"]),
    ("他变成了一个大人。", False, {"他": "是"}, ["他"]),
    ("他换了一副面孔，谁也没认出来。", False, {"他": "是"}, ["他"]),
]


def _按原文找样本(提示: str) -> dict:
    for 样本 in 读样本():
        if 样本["原文"] in 提示:
            return 样本
    raise AssertionError("提示里没有评测样本的原文")


def _假模型(判错=False, 填变后样貌=False):
    """按已知答案造答案的假模型；两个开关用来故意答错。"""

    def 调用模型(提示: str) -> str:
        样本 = _按原文找样本(提示)
        答案 = 样本["已知答案"]
        人物 = []
        for 名称, 判定 in 答案["人物判定"].items():
            判是 = 判定 == "是"
            if 判错 and not 判是:
                判是 = True  # 故意答错：把判否的人物判成是
            身份 = dict.fromkeys(人物身份字段, "")
            期望样貌 = 答案.get("身份样貌", {}).get(名称, {})
            if 填变后样貌 and 判是 and not 期望样貌:
                身份.update({"脸型": "狼脸", "发型与发色": "灰毛", "眼": "竖瞳", "显著特征": "獠牙", "年龄": "十六", "体态": "四足"})
            身份.update(期望样貌)
            未支持 = []
            if 判是:
                未支持 = [{"类别": 答案.get("未支持类别", {}).get(名称, "变身"), "片段": 样本["原文"]}]
            人物.append(
                {
                    "名称": 名称,
                    "身份": 身份,
                    "原文起": 0,
                    "原文止": len(样本["原文"]),
                    "服装": [],
                    "未支持": 未支持,
                }
            )
        无主线索 = [
            {"类别": 答案.get("无主线索类别", "变身"), "片段": 样本["原文"]}
            for _ in range(答案["无主线索条数"])
        ]
        return json.dumps(
            {"人物": 人物, "场景": [], "风格ID": "水墨", "故事节拍": [], "无主线索": 无主线索},
            ensure_ascii=False,
        )

    return 调用模型


def test_评测集覆盖契约要求的必含样本():
    样本表 = 读样本()
    assert len(样本表) >= 6
    按原文 = {样本["原文"]: 样本 for 样本 in 样本表}

    for 原文, 产生无主线索, 人物判定, 名称集合 in 必含样本:
        assert 原文 in 按原文, f"缺必含样本：{原文}"
        答案 = 按原文[原文]["已知答案"]
        assert 答案["产生无主线索"] is 产生无主线索
        assert 答案["人物判定"] == 人物判定
        assert 答案["人物卡名称集合"] == 名称集合
        assert 答案["无主线索条数"] == (1 if 产生无主线索 else 0)

    无主样本 = 按原文["有人摇身一变，成了狼。"]["已知答案"]
    assert 无主样本["人物卡名称集合"] == [], "不得新建名为「有人」的人物卡"

    for 原文 in ("她变成了一名少年。", "他变成了一个大人。", "他换了一副面孔，谁也没认出来。"):
        assert 按原文[原文]["已知答案"]["身份样貌"] == {原文[0]: {}}, "涉及未支持人物时要给身份样貌期望值"


def test_样本文件在tests的fixtures下且可解析():
    assert 样本文件.name == "item1_评测集.json"
    assert 样本文件.parent.name == "fixtures"
    assert 样本文件.exists()
    assert len(json.loads(样本文件.read_text(encoding="utf-8"))["样本"]) == len(读样本())


def test_照抄已知答案的假模型判通过():
    结果 = 跑评测集(_假模型())
    assert 结果["样本数"] == len(读样本())
    assert 结果["通过数"] == 结果["样本数"]
    assert 结果["通过"] is True
    assert all(样本["通过"] for 样本 in 结果["样本"])
    assert [样本["失败项"] for 样本 in 结果["样本"]] == [[]] * 结果["样本数"]


def test_故意答错未支持判定的假模型被判失败():
    结果 = 跑评测集(_假模型(判错=True))
    assert 结果["通过"] is False
    assert 结果["通过数"] < 结果["样本数"]
    失败 = {样本["编号"]: 样本["失败项"] for 样本 in 结果["样本"] if not 样本["通过"]}
    assert set(失败) == {"样本-2", "样本-3"}, "「扮成」这两条已知答案与字样冲突，必须判失败"
    assert any("人物判定" in 项 for 项 in 失败["样本-2"])


def test_故意把变后样貌填进身份的假模型被判失败():
    结果 = 跑评测集(_假模型(填变后样貌=True))
    assert 结果["通过"] is False
    失败 = {样本["编号"]: 样本["失败项"] for 样本 in 结果["样本"] if not 样本["通过"]}
    assert set(失败) == {"样本-4", "样本-5", "样本-6", "样本-8"}
    assert all(any("身份样貌" in 项 for 项 in 项表) for 项表 in 失败.values())


def test_评测集跑起来不访问网络(monkeypatch: pytest.MonkeyPatch):
    import socket

    def _禁止联网(*args, **kwargs):
        raise AssertionError("评测集不应访问网络")

    monkeypatch.setattr(socket, "socket", _禁止联网)
    monkeypatch.setattr(socket, "create_connection", _禁止联网)
    assert 跑评测集(_假模型())["通过"] is True
