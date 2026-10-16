"""ITEM-2 · 档案：把 ITEM-1 的草稿落成可确认、可修改、可复用的档案。

契约里的档案分三块：人物身份、服装状态、场景卡；另加一个全篇只有一个的风格 ID。
每一项都可带一张参考图。确认状态记在人物身份、每一套服装状态、每张场景卡和风格 ID 上，
不记成整张人物卡的一个布尔值。

修改的级联规则：
- 改人物身份 → 该身份、其下全部服装状态、以及它们的参考图一并退回未确认。
- 改某一套服装 / 某张场景卡 / 风格 ID → 只把该项与其参考图退回未确认。

参考图由本步提供生成或接收，主人自带一张也可以；参考图有自己的确认状态，
「缺已确认参考图」由 `storyweave.gate` 判定。档案是纯数据：不写文件、不访问网络。

项 ID（引用记录与出页检查都用它定位）：
`身份:{名称}` / `服装:{名称}:{位置}` / `场景:{名称}` / `风格:{风格文字}`。
服装状态 ID 的序号部分跟着它在人物卡里的位置，所以重跑抽取后顺序变了，ID 也会跟着变。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from storyweave.extract import 人物身份字段

未确认 = "未确认"
已确认 = "已确认"

生成 = "生成"
主人自带 = "主人自带"

身份前缀 = "身份:"
服装前缀 = "服装:"
场景前缀 = "场景:"
风格前缀 = "风格:"


class 档案非法(ValueError):
    """档案操作遇到不合契约的输入。"""


def 建档案(草稿: Mapping[str, Any]) -> dict[str, Any]:
    """从 ITEM-1 的草稿建一份档案：全部项都是未确认，都还没有参考图。

    只搬契约里的三块加风格 ID；未支持判定、故事节拍、无主线索都不是档案项，不搬。
    """
    if not isinstance(草稿, Mapping):
        raise 档案非法("草稿必须是对象")
    人物表 = 草稿.get("人物卡")
    场景表 = 草稿.get("场景卡")
    风格块 = 草稿.get("风格ID")
    if not isinstance(人物表, list):
        raise 档案非法("草稿里的人物卡必须是列表")
    if not isinstance(场景表, list):
        raise 档案非法("草稿里的场景卡必须是列表")
    if not isinstance(风格块, Mapping):
        raise 档案非法("草稿里的风格ID必须是对象")

    风格文字 = _文本(风格块.get("草稿"), "风格ID.草稿")
    return {
        "人物卡": [_造人物卡(人物) for 人物 in 人物表],
        "场景卡": [_造场景卡(场景) for 场景 in 场景表],
        "风格ID": {
            "风格ID": 风格前缀 + 风格文字,
            "草稿": 风格文字,
            "确认状态": 未确认,
            "样张": None,
        },
    }


def 找项(档案: Mapping[str, Any], 项ID: str) -> dict[str, Any]:
    """按项 ID 取到那一项本身（可变对象），取不到就抛 档案非法。"""
    前缀, 余下 = _拆ID(项ID)
    if 前缀 == 身份前缀:
        return _按名称找卡(档案, 余下)
    if 前缀 == 服装前缀:
        名称, 分隔, 序号文 = 余下.rpartition(":")
        if not 分隔:
            raise 档案非法(f"服装状态 ID 要写成 服装:人物:位置：{项ID}")
        try:
            序号 = int(序号文)
        except ValueError:
            raise 档案非法(f"服装状态 ID 的位置必须是整数：{项ID}") from None
        套表 = _按名称找卡(档案, 名称)["服装状态列表"]
        if not 0 <= 序号 < len(套表):
            raise 档案非法(f"没有这个服装状态：{项ID}")
        return 套表[序号]
    if 前缀 == 场景前缀:
        for 场景 in 档案.get("场景卡", []):
            if 场景["名称"] == 余下:
                return 场景
        raise 档案非法(f"没有这个场景卡：{项ID}")
    风格块 = 档案.get("风格ID", {})
    if 风格块.get("风格ID") == 项ID:
        return 风格块
    raise 档案非法(f"没有这个风格 ID：{项ID}")


def 参考图提示(档案: Mapping[str, Any], 项ID: str) -> str:
    """按该项的文字拼一段出图提示，交给图像模型生成参考图。"""
    前缀, _ = _拆ID(项ID)
    项 = 找项(档案, 项ID)
    if 前缀 == 身份前缀:
        身份 = 项["人物身份"]
        细节 = "，".join(f"{字段}{身份.get(字段, '')}" for 字段 in 人物身份字段 if 身份.get(字段))
        return f"画一张人物「{项['名称']}」的正脸参考图：{细节}。只要一张正脸。"
    if 前缀 == 服装前缀:
        return f"画一张人物「{_服装所属人物(档案, 项)}」的服装参考图：{项['描述']}。"
    if 前缀 == 场景前缀:
        return f"画一张场景「{项['名称']}」的建筑外观参考图：{项['建筑外观']}。"
    return f"画一张本版风格样张：风格 {项['草稿']}。"


def 确认人物卡(档案: dict[str, Any], 名称: str) -> dict[str, Any]:
    """确认人物卡：把该卡当前的身份与全部服装状态标为已确认。

    参考图有自己的确认状态，要单独用 确认参考图 确认。
    """
    卡 = _按名称找卡(档案, 名称)
    卡["身份确认状态"] = 已确认
    for 套 in 卡["服装状态列表"]:
        套["确认状态"] = 已确认
    return 档案


def 确认服装状态(档案: dict[str, Any], 服装状态ID: str) -> dict[str, Any]:
    """只确认这一套服装，不动身份与其他套。"""
    _要求前缀(服装状态ID, 服装前缀)
    找项(档案, 服装状态ID)["确认状态"] = 已确认
    return 档案


def 确认场景卡(档案: dict[str, Any], 场景卡ID: str) -> dict[str, Any]:
    """只确认这张场景卡。"""
    _要求前缀(场景卡ID, 场景前缀)
    找项(档案, 场景卡ID)["确认状态"] = 已确认
    return 档案


def 确认风格ID(档案: dict[str, Any]) -> dict[str, Any]:
    """确认本版风格 ID。样张要单独用 确认参考图 确认。"""
    档案["风格ID"]["确认状态"] = 已确认
    return 档案


def 改人物身份(档案: dict[str, Any], 名称: str, 新身份: Mapping[str, Any]) -> dict[str, Any]:
    """改人物身份：只认六项身份字段，并把身份与其下全部服装状态和它们的参考图退回未确认。"""
    if not isinstance(新身份, Mapping):
        raise 档案非法("新身份必须是对象")
    卡 = _按名称找卡(档案, 名称)
    卡["人物身份"] = {字段: _文本(新身份.get(字段), f"新身份.{字段}") for 字段 in 人物身份字段}
    _退回未确认(卡, "身份确认状态", "身份参考图")
    for 套 in 卡["服装状态列表"]:
        _退回未确认(套, "确认状态", "参考图")
    return 档案


def 改服装状态(档案: dict[str, Any], 服装状态ID: str, 新描述: str) -> dict[str, Any]:
    """改一套服装的描述：只把这一套与它的参考图退回未确认。"""
    _要求前缀(服装状态ID, 服装前缀)
    项 = 找项(档案, 服装状态ID)
    项["描述"] = _文本(新描述, "新描述")
    _退回未确认(项, "确认状态", "参考图")
    return 档案


def 改场景卡(档案: dict[str, Any], 场景卡ID: str, 新建筑外观: str) -> dict[str, Any]:
    """改一张场景卡的建筑外观：只把这张与它的参考图退回未确认。"""
    _要求前缀(场景卡ID, 场景前缀)
    项 = 找项(档案, 场景卡ID)
    项["建筑外观"] = _文本(新建筑外观, "新建筑外观")
    _退回未确认(项, "确认状态", "参考图")
    return 档案


def 改风格ID(档案: dict[str, Any], 新风格: str) -> dict[str, Any]:
    """改本版风格 ID：风格 ID 与其样张一并退回未确认。

    风格 ID 跟着它的文字走，所以改了文字，项 ID 也换成新的。
    """
    文字 = _文本(新风格, "新风格")
    风格块 = 档案["风格ID"]
    风格块["草稿"] = 文字
    风格块["风格ID"] = 风格前缀 + 文字
    _退回未确认(风格块, "确认状态", "样张")
    return 档案


def 附参考图(
    档案: dict[str, Any], 项ID: str, 图片: bytes, 来源: str = 主人自带
) -> dict[str, Any]:
    """给某一项挂上一张参考图。挂上时是未确认，要用 确认参考图 确认。"""
    if not isinstance(图片, bytes):
        raise 档案非法("参考图必须是字节")
    前缀, _ = _拆ID(项ID)
    项 = 找项(档案, 项ID)
    项[_参考图键(前缀)] = {"来源": 来源, "图片": 图片, "确认状态": 未确认}
    return 档案


def 生成参考图(
    档案: dict[str, Any], 项ID: str, 生成图: Callable[[str], bytes]
) -> dict[str, Any]:
    """按该项文字生成一张参考图并挂上。

    生成图 由调用方注入（`storyweave.model_client.构建生成图` 产出的那种 `提示 -> 图片字节`），
    本函数自己不访问网络。生成失败时原样抛出，档案不留半张图。
    """
    if not callable(生成图):
        raise TypeError("生成图 必须是可调用的函数")
    提示 = 参考图提示(档案, 项ID)
    图片 = 生成图(提示)
    return 附参考图(档案, 项ID, 图片, 来源=生成)


def 确认参考图(档案: dict[str, Any], 项ID: str) -> dict[str, Any]:
    """确认某一项的参考图。还没有图就抛 档案非法。"""
    前缀, _ = _拆ID(项ID)
    项 = 找项(档案, 项ID)
    图 = 项.get(_参考图键(前缀))
    if not isinstance(图, dict):
        raise 档案非法(f"这一项还没有参考图：{项ID}")
    图["确认状态"] = 已确认
    return 档案


def 合并草稿(档案: dict[str, Any], 新草稿: Mapping[str, Any]) -> dict[str, Any]:
    """改完原文重跑抽取后，把新草稿并进档案。

    新草稿只替换尚未确认的抽取结果：已确认的人物身份、服装状态、场景卡、风格 ID 及其参考图
    不被覆盖，也不被重新抽取；新草稿里已消失且未确认的项被丢掉，已确认的项留下。
    新草稿多出来的项按未确认收进来。
    """
    新档 = 建档案(新草稿)

    旧卡表 = {卡["名称"]: 卡 for 卡 in 档案["人物卡"]}
    新卡表 = {卡["名称"]: 卡 for 卡 in 新档["人物卡"]}
    人物合并: list[dict[str, Any]] = []
    for 名称, 新卡 in 新卡表.items():
        旧卡 = 旧卡表.get(名称)
        人物合并.append(_并人物卡(旧卡, 新卡) if 旧卡 is not None else 新卡)
    for 卡 in 档案["人物卡"]:
        if 卡["名称"] not in 新卡表 and 卡["身份确认状态"] == 已确认:
            人物合并.append(卡)
    档案["人物卡"] = 人物合并

    旧场表 = {场["名称"]: 场 for 场 in 档案["场景卡"]}
    新场表 = {场["名称"]: 场 for 场 in 新档["场景卡"]}
    场景合并: list[dict[str, Any]] = []
    for 名称, 新场 in 新场表.items():
        旧场 = 旧场表.get(名称)
        if 旧场 is None:
            场景合并.append(新场)
            continue
        if 旧场["确认状态"] != 已确认:
            旧场["建筑外观"] = 新场["建筑外观"]
            旧场["原文位置"] = 新场["原文位置"]
            _退回未确认(旧场, "确认状态", "参考图")
        场景合并.append(旧场)
    for 场 in 档案["场景卡"]:
        if 场["名称"] not in 新场表 and 场["确认状态"] == 已确认:
            场景合并.append(场)
    档案["场景卡"] = 场景合并

    风格块 = 档案["风格ID"]
    if 风格块["确认状态"] != 已确认:
        新风格块 = 新档["风格ID"]
        风格块["草稿"] = 新风格块["草稿"]
        风格块["风格ID"] = 新风格块["风格ID"]
        _退回未确认(风格块, "确认状态", "样张")

    return 档案


# ---------- 内部 ----------


def _造人物卡(人物: Any) -> dict[str, Any]:
    if not isinstance(人物, Mapping):
        raise 档案非法("人物卡必须是对象")
    名称 = 人物.get("名称")
    if not isinstance(名称, str) or not 名称.strip():
        raise 档案非法("人物卡必须有名称")
    身份 = 人物.get("人物身份")
    if not isinstance(身份, Mapping):
        raise 档案非法(f"人物「{名称}」缺少人物身份")
    服装表 = 人物.get("服装状态列表", [])
    if not isinstance(服装表, list):
        raise 档案非法(f"人物「{名称}」的服装状态列表必须是列表")
    return {
        "名称": 名称,
        "身份ID": 身份前缀 + 名称,
        "人物身份": {字段: _文本(身份.get(字段), f"人物「{名称}」的身份.{字段}") for 字段 in 人物身份字段},
        "身份确认状态": 未确认,
        "身份参考图": None,
        "原文位置": _位置(人物),
        "服装状态列表": [_造服装(名称, 序号, 套) for 序号, 套 in enumerate(服装表)],
    }


def _造服装(名称: str, 序号: int, 套: Any) -> dict[str, Any]:
    if not isinstance(套, Mapping):
        raise 档案非法(f"人物「{名称}」的服装状态必须是对象")
    return {
        "服装状态ID": f"{服装前缀}{名称}:{序号}",
        "名称": _文本(套.get("名称"), "服装.名称"),
        "描述": _文本(套.get("描述"), "服装.描述"),
        "原文位置": _位置(套),
        "确认状态": 未确认,
        "参考图": None,
    }


def _造场景卡(场景: Any) -> dict[str, Any]:
    if not isinstance(场景, Mapping):
        raise 档案非法("场景卡必须是对象")
    名称 = 场景.get("名称")
    if not isinstance(名称, str) or not 名称.strip():
        raise 档案非法("场景卡必须有名称")
    return {
        "场景卡ID": 场景前缀 + 名称,
        "名称": 名称,
        "建筑外观": _文本(场景.get("建筑外观"), "场景.建筑外观"),
        "原文位置": _位置(场景),
        "确认状态": 未确认,
        "参考图": None,
    }


def _并人物卡(旧卡: dict[str, Any], 新卡: dict[str, Any]) -> dict[str, Any]:
    if 旧卡["身份确认状态"] != 已确认:
        旧卡["人物身份"] = 新卡["人物身份"]
        旧卡["原文位置"] = 新卡["原文位置"]
        _退回未确认(旧卡, "身份确认状态", "身份参考图")
    旧卡["服装状态列表"] = _并服装(旧卡["服装状态列表"], 新卡["服装状态列表"])
    return 旧卡


def _并服装(旧套表: list[dict[str, Any]], 新套表: list[dict[str, Any]]) -> list[dict[str, Any]]:
    旧表 = {套["名称"]: 套 for 套 in 旧套表}
    合并: list[dict[str, Any]] = []
    for 新套 in 新套表:
        旧套 = 旧表.get(新套["名称"])
        if 旧套 is None:
            合并.append(新套)
            continue
        if 旧套["确认状态"] != 已确认:
            旧套["描述"] = 新套["描述"]
            旧套["原文位置"] = 新套["原文位置"]
            _退回未确认(旧套, "确认状态", "参考图")
        合并.append(旧套)
    留下的名称 = {套["名称"] for 套 in 新套表}
    for 旧套 in 旧套表:
        if 旧套["名称"] not in 留下的名称 and 旧套["确认状态"] == 已确认:
            合并.append(旧套)
    _重编服装ID(合并)
    return 合并


def _重编服装ID(套表: list[dict[str, Any]]) -> None:
    """服装状态 ID 的序号部分跟着位置走，合并后重新编号，保证不重。"""
    for 位置, 套 in enumerate(套表):
        原ID = 套.get("服装状态ID", "")
        人物名 = 原ID[len(服装前缀) :].rpartition(":")[0] if 原ID.startswith(服装前缀) else ""
        套["服装状态ID"] = f"{服装前缀}{人物名}:{位置}"


def _服装所属人物(档案: Mapping[str, Any], 套: Mapping[str, Any]) -> str:
    """从服装状态 ID 里取回它属于哪个人物（出图提示要写清是谁穿这身）。"""
    套ID = 套.get("服装状态ID", "")
    for 卡 in 档案.get("人物卡", []) or []:
        if 套 in 卡["服装状态列表"]:
            return 卡["名称"]
    return 套ID[len(服装前缀) :].rpartition(":")[0]


def _拆ID(项ID: str) -> tuple[str, str]:
    if not isinstance(项ID, str):
        raise 档案非法("项 ID 必须是字符串")
    for 前缀 in (身份前缀, 服装前缀, 场景前缀, 风格前缀):
        if 项ID.startswith(前缀):
            return 前缀, 项ID[len(前缀) :]
    raise 档案非法(f"认不出这个项 ID：{项ID}")


def _要求前缀(项ID: str, 期望前缀: str) -> None:
    前缀, _ = _拆ID(项ID)
    if 前缀 != 期望前缀:
        raise 档案非法(f"这项不是 {期望前缀} 类：{项ID}")


def _参考图键(前缀: str) -> str:
    if 前缀 == 身份前缀:
        return "身份参考图"
    if 前缀 == 风格前缀:
        return "样张"
    return "参考图"


def _按名称找卡(档案: Mapping[str, Any], 名称: str) -> dict[str, Any]:
    for 卡 in 档案.get("人物卡", []):
        if 卡["名称"] == 名称:
            return 卡
    raise 档案非法(f"没有这个人物卡：{名称}")


def _退回未确认(项: dict[str, Any], 确认键: str, 图键: str) -> None:
    项[确认键] = 未确认
    图 = 项.get(图键)
    if isinstance(图, dict):
        图["确认状态"] = 未确认


def _文本(值: Any, 名字: str) -> str:
    if 值 is None:
        return ""
    if not isinstance(值, str):
        raise 档案非法(f"{名字}必须是字符串")
    return 值


def _位置(来源: Mapping[str, Any]) -> dict[str, int] | None:
    位置 = 来源.get("原文位置")
    if not isinstance(位置, Mapping):
        return None
    起 = 位置.get("起")
    止 = 位置.get("止")
    if isinstance(起, int) and isinstance(止, int) and not isinstance(起, bool) and not isinstance(止, bool):
        return {"起": 起, "止": 止}
    return None
