"""ITEM-1 自带的小评测集：样本数据加评测 harness。

样本是合成的原文节选加已知答案，覆盖契约写明的必含样本；节选不受 1 万到 2 万字篇幅门槛约束。
harness 逐条比较「该篇是否产生无主线索」「每个人物的未支持判定结果」「人物卡名称集合」，
以及涉及未支持人物时的「身份样貌」。正则提示与已知答案冲突时，结果跟已知答案走。
模型调用由调用方注入，harness 自己不访问网络。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from storyweave.extract import 人物身份字段, 抽取草稿

样本文件 = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "item1_评测集.json"


def 读样本(路径: Path | None = None) -> list[dict[str, Any]]:
    """读评测样本。每条样本带原文节选和已知答案。"""
    内容 = json.loads((路径 or 样本文件).read_text(encoding="utf-8"))
    return 内容["样本"]


def 跑评测集(调用模型: Callable[[str], str]) -> dict[str, Any]:
    """对每条样本跑一次抽取，再和已知答案比对，返回评分结果。"""
    逐条结果 = []
    for 样本 in 读样本():
        草稿 = 抽取草稿(样本["原文"], 调用模型)
        失败项 = 评分样本(草稿, 样本["已知答案"])
        逐条结果.append(
            {
                "编号": 样本["编号"],
                "说明": 样本.get("说明", ""),
                "通过": not 失败项,
                "失败项": 失败项,
            }
        )
    通过数 = sum(1 for 条 in 逐条结果 if 条["通过"])
    return {
        "通过": 通过数 == len(逐条结果),
        "样本数": len(逐条结果),
        "通过数": 通过数,
        "样本": 逐条结果,
    }


def 评分样本(草稿: Mapping[str, Any], 已知答案: Mapping[str, Any]) -> list[str]:
    """按已知答案的四个字段比对，返回失败项；全部对上就是空列表。"""
    失败项: list[str] = []

    线索 = 草稿.get("无主线索", [])
    if bool(线索) != bool(已知答案["产生无主线索"]):
        失败项.append(f"是否产生无主线索：期望 {已知答案['产生无主线索']}，实际 {bool(线索)}")
    if len(线索) != 已知答案["无主线索条数"]:
        失败项.append(f"无主线索条数：期望 {已知答案['无主线索条数']}，实际 {len(线索)}")

    卡表 = {卡["名称"]: 卡 for 卡 in 草稿.get("人物卡", [])}
    名称集合 = sorted(卡表)
    期望名称集合 = sorted(已知答案["人物卡名称集合"])
    if 名称集合 != 期望名称集合:
        失败项.append(f"人物卡名称集合：期望 {期望名称集合}，实际 {名称集合}")

    for 名称, 判定 in 已知答案["人物判定"].items():
        if 名称 not in 卡表:
            失败项.append(f"人物判定：缺少人物卡「{名称}」")
            continue
        实际 = "是" if 卡表[名称]["未支持"] else "否"
        if 实际 != 判定:
            失败项.append(f"人物判定：{名称} 期望 {判定}，实际 {实际}")

    for 名称, 期望样貌 in 已知答案.get("身份样貌", {}).items():
        if 名称 not in 卡表:
            失败项.append(f"身份样貌：缺少人物卡「{名称}」")
            continue
        身份 = 卡表[名称]["人物身份"]
        for 字段 in 人物身份字段:
            期望值 = 期望样貌.get(字段, "")
            实际值 = 身份.get(字段, "")
            if 实际值 != 期望值:
                失败项.append(f"身份样貌：{名称}.{字段} 期望 {期望值!r}，实际 {实际值!r}")

    return 失败项
