"""ITEM-2 · 确认关卡的出页检查与跳过标记。

契约把两种粒度分得很清：

- 未处理的无主线索 → **整篇**不得出页（`整篇出页检查`）。
- 未支持且未跳过的未支持判定 → **该人物**不得出页（`人物出页检查`）。

跳过标记记在草稿上（不是档案项，也不进引用记录）：每条无主线索、每个未支持人物各记一条，
互不覆盖。本模块只写这两个标记位，并据此算能不能出页。

参考图的带图要求分两档：人物身份与风格 ID 在本关卡就要有已确认参考图；服装状态与场景卡
首次确认时允许暂无图，它们的带图要求要等 ITEM-3 建好引用记录后按引用计数判定，所以本模块不拦。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from storyweave.archive import 已确认


class 关卡非法(ValueError):
    """确认关卡遇到不合契约的输入。"""


def 跳过无主线索(草稿: dict[str, Any], 序号: int) -> dict[str, Any]:
    """主人明确跳过一条无主线索。跳过标记记在这条线索上，不影响别的线索。"""
    线索表 = 草稿.get("无主线索")
    if not isinstance(线索表, list) or not _序号有效(序号, len(线索表)):
        raise 关卡非法(f"没有这条无主线索：序号 {序号}")
    线索表[序号]["已跳过"] = True
    return 草稿


def 跳过未支持(草稿: dict[str, Any], 名称: str, 序号: int) -> dict[str, Any]:
    """主人明确跳过某个人物的一条未支持判定。跳过标记记在这条上，不影响别的条目或别人物。"""
    卡 = _找草稿人物卡(草稿, 名称)
    未支持表 = 卡.get("未支持")
    if not isinstance(未支持表, list) or not _序号有效(序号, len(未支持表)):
        raise 关卡非法(f"人物「{名称}」没有这条未支持判定：序号 {序号}")
    未支持表[序号]["已跳过"] = True
    return 草稿


def 整篇出页检查(档案: Mapping[str, Any], 草稿: Mapping[str, Any]) -> dict[str, Any]:
    """整篇能不能出页，以及被什么拦住。

    拦住整篇的有：未处理的无主线索；任一人物身份、服装状态、场景卡或风格 ID 未确认；
    人物身份缺已确认参考图；风格 ID 缺已确认样张。
    未支持人物是另一种粒度，由 人物出页检查 负责，不在这里把整篇判死。
    """
    理由: list[str] = []

    for 条 in 草稿.get("无主线索", []) or []:
        if not 条.get("已跳过"):
            理由.append(f"还有未处理的无主线索：{条.get('类别')}「{条.get('片段')}」")

    for 卡 in 档案.get("人物卡", []) or []:
        if 卡["身份确认状态"] != 已确认:
            理由.append(f"人物身份未确认：{卡['身份ID']}")
        elif not _图已确认(卡.get("身份参考图")):
            理由.append(f"人物身份缺已确认参考图：{卡['身份ID']}")
        for 套 in 卡["服装状态列表"]:
            if 套["确认状态"] != 已确认:
                理由.append(f"服装状态未确认：{套['服装状态ID']}")

    for 场景 in 档案.get("场景卡", []) or []:
        if 场景["确认状态"] != 已确认:
            理由.append(f"场景卡未确认：{场景['场景卡ID']}")

    风格块 = 档案.get("风格ID") or {}
    if 风格块.get("确认状态") != 已确认:
        理由.append(f"风格 ID 未确认：{风格块.get('风格ID')}")
    elif not _图已确认(风格块.get("样张")):
        理由.append(f"风格 ID 缺已确认样张：{风格块.get('风格ID')}")

    return {"可出页": not 理由, "拒绝理由": 理由}


def 人物出页检查(
    档案: Mapping[str, Any], 草稿: Mapping[str, Any], 名称: str
) -> dict[str, Any]:
    """某个人物能不能出页，以及被什么拦住。

    只看这个人物：它自己有没有未跳过的未支持判定、它的身份与服装状态有没有确认、
    它的身份有没有已确认参考图。整篇的无主线索由 整篇出页检查 负责，不在这里重复算。
    """
    草稿卡 = _找草稿人物卡(草稿, 名称)
    理由: list[str] = []

    for 条 in 草稿卡.get("未支持", []) or []:
        if not 条.get("已跳过"):
            理由.append(f"该人物有未跳过的未支持判定：{条.get('类别')}「{条.get('片段')}」")

    档案卡 = _找档案人物卡(档案, 名称)
    if 档案卡["身份确认状态"] != 已确认:
        理由.append(f"人物身份未确认：{档案卡['身份ID']}")
    elif not _图已确认(档案卡.get("身份参考图")):
        理由.append(f"人物身份缺已确认参考图：{档案卡['身份ID']}")
    for 套 in 档案卡["服装状态列表"]:
        if 套["确认状态"] != 已确认:
            理由.append(f"服装状态未确认：{套['服装状态ID']}")

    return {"可出页": not 理由, "拒绝理由": 理由}


# ---------- 内部 ----------


def _序号有效(序号: Any, 长度: int) -> bool:
    return isinstance(序号, int) and not isinstance(序号, bool) and 0 <= 序号 < 长度


def _图已确认(图: Any) -> bool:
    return isinstance(图, Mapping) and 图.get("确认状态") == 已确认


def _找草稿人物卡(草稿: Mapping[str, Any], 名称: str) -> Mapping[str, Any]:
    for 卡 in 草稿.get("人物卡", []) or []:
        if 卡.get("名称") == 名称:
            return 卡
    raise 关卡非法(f"草稿里没有这个人物卡：{名称}")


def _找档案人物卡(档案: Mapping[str, Any], 名称: str) -> Mapping[str, Any]:
    for 卡 in 档案.get("人物卡", []) or []:
        if 卡.get("名称") == 名称:
            return 卡
    raise 关卡非法(f"档案里没有这个人物卡：{名称}")
