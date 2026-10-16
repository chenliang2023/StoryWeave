"""ITEM-3 · 页剧本：按已确认档案和当前故事节拍写出按阅读顺序排列的分页脚本。

每页给出分格、对白，以及一份引用记录。引用记录只保存四类 ID（身份 / 服装状态 / 场景卡 /
风格ID），不保存节拍 ID，也不保存隐式依赖；每页另带 `节拍顺序`，用它指回故事节拍的原文位置
（`页原文位置`）。页数按情节决定，不设固定格数。

页剧本一经生成即冻结：

- 生成时把当时的故事节拍存成快照（深拷贝）；草稿上的节拍之后被改动，整篇页剧本失效
  （`节拍已改` / `页剧本已失效`）。
- 引用计数只在生成时算一次，之后不随档案变化。要改计数只能整篇重写（`重写页剧本`）：
  旧页剧本被标成已失效、世代加一，供 ITEM-4 判「旧页剧本与全部页面失效」。
- 冻结守到哪一步：`重写页剧本` 拒绝从已失效的剧本再重写，所以世代沿一条链递增；但本模块
  不保存「当前剧本」是哪一份，`写页剧本` 被独立调用两次会得到两份同为世代 1 的有效剧本。
  首次生成只调一次，由调用方保证。

契约把外貌与服装排除在页剧本之外：生成时扫一遍身份字段值与服装描述，命中就拒绝，免得
页剧本抢了档案的活。这是逐字子串匹配，只能挡住照抄：改写的说法（「打了补丁的棉袄」）挡不住，
人物卡名称、服装名称与场景卡的建筑外观也不在扫描范围内。档案只喂已确认的项，引用记录也
只能命中已确认的项。

带图要求分两档：人物身份与风格 ID 由确认关卡常项要求（DEC-6），跟引用计数无关；
服装状态与场景卡被 2 页以上引用时才要求带参考图（`要求参考图`），由 `落实带图要求` 把
「要求带图却还没有已确认参考图」的项退回未确认。

模型调用由调用方注入（`提示 -> 文本`），本模块不绑定供应商，也不访问网络。
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from typing import Any

from storyweave.archive import 已确认, 未确认, 找项, 档案非法
from storyweave.extract import 人物身份字段, 解析模型输出

模型调用 = Callable[[str], str]

身份引用 = "身份"
服装引用 = "服装状态"
场景引用 = "场景卡"
风格引用 = "风格ID"
引用类别 = (身份引用, 服装引用, 场景引用, 风格引用)

ID前缀 = {"身份:": 身份引用, "服装:": 服装引用, "场景:": 场景引用, "风格:": 风格引用}

带图门槛 = 2
描述扫描下限 = 2

页剧本提示模板 = """你是短篇漫画的页剧本编剧。按下面这份已确认的档案和故事节拍，\
写出按阅读顺序排列的页剧本：每一页给出分格与对白，并给出一份引用记录。

要求：
1. 只输出一个 JSON 对象：不要解释，不要 Markdown 代码围栏，不要多余文字。
2. 只写动作与对白，绝不写外貌或服装：脸型、发型与发色、眼、显著特征、年龄、体态，\
以及衣服的样子，都由档案和参考图负责，页剧本里一个字都不要提。
3. 情节只来自故事节拍，不新增原文没有的情节。每一页都要在 节拍顺序 里写出它落在哪几条节拍上，\
取值只能是下面列出的节拍序号。
4. 页数按情节决定，不设固定格数；每页的分格数也按这一页要讲的事决定。
5. 引用记录只写四类 ID，键名照抄 身份 / 服装状态 / 场景卡 / 风格ID，值是该页引用到的 ID 列表。\
不写节拍 ID，不加别的键，也不要写没有列在下面的 ID。
6. 对白写成可读文本，一句一行。

JSON 结构如下（字段名照抄）：
{结构}

故事节拍如下：
{节拍}

已确认档案如下：
{档案}
"""

结构模板 = """{
  "页": [
    {
      "分格": [{"画面": "", "对白": [""]}],
      "节拍顺序": [1],
      "引用记录": {"身份": [], "服装状态": [], "场景卡": [], "风格ID": []}
    }
  ]
}"""


class 页剧本非法(ValueError):
    """页剧本的结构或引用不合契约要求。"""


def 构建页剧本提示(档案: Mapping[str, Any], 草稿: Mapping[str, Any]) -> str:
    """把已确认档案与当前故事节拍拼成页剧本提示。

    档案里未确认的项不进提示：模型看不到，也就写不进引用记录。
    """
    if not isinstance(档案, Mapping):
        raise TypeError("档案必须是对象")
    if not isinstance(草稿, Mapping):
        raise TypeError("草稿必须是对象")
    return 页剧本提示模板.format(结构=结构模板, 节拍=_节拍文本(草稿), 档案=_档案文本(档案))


def 写页剧本(
    档案: Mapping[str, Any], 草稿: Mapping[str, Any], 调用模型: 模型调用
) -> dict[str, Any]:
    """按已确认档案和当前故事节拍写出页剧本：构建提示 → 调用模型 → 解析 → 校验。

    页 ID 按阅读顺序生成（页1、页2…）。返回的页剧本是纯数据：不写文件，也不改档案。
    引用计数与带图要求在这里算定，之后不再重算；要改计数只能 重写页剧本。
    """
    if not callable(调用模型):
        raise TypeError("调用模型 必须是可调用的函数")
    输出 = 解析模型输出(调用模型(构建页剧本提示(档案, 草稿)))
    类别 = _项类别(档案)
    已确认项 = _已确认项(档案)
    页表 = _页表(输出, 档案, 类别, 已确认项, _节拍表(草稿))
    计数 = _统计计数(页表)
    return {
        "页": 页表,
        "引用计数": 计数,
        "要求带图": {
            项ID: True
            for 项ID, 次数 in 计数.items()
            if 次数 >= 带图门槛 and 类别.get(项ID) in (服装引用, 场景引用)
        },
        "节拍快照": copy.deepcopy(list(草稿.get("故事节拍") or [])),
        "世代": 1,
        "已失效": False,
    }


def 重写页剧本(
    档案: Mapping[str, Any],
    草稿: Mapping[str, Any],
    旧页剧本: dict[str, Any],
    调用模型: 模型调用,
) -> dict[str, Any]:
    """整篇重写页剧本：唯一能改变引用计数的方式。

    重写把旧页剧本标成已失效、世代加一，旧剧本与它出的页全部作废；新剧本按新引用记录
    重新计数并重新判定带图要求。不支持逐页增删或改写。

    只能从「当前那一份」重写：旧页剧本已经被标成失效时拒绝，否则拿同一份旧剧本连着重写两次
    会产出两份同世代的有效剧本，ITEM-4 就分不出哪份是当前的。本模块不记录「当前剧本」是哪
    一份，首次生成只认一次 写页剧本 调用，这一点由调用方保证。
    """
    if 旧页剧本.get("已失效"):
        raise 页剧本非法("不能从已失效的页剧本重写，请用当前那一份")
    新页剧本 = 写页剧本(档案, 草稿, 调用模型)
    新页剧本["世代"] = _世代(旧页剧本) + 1
    旧页剧本["已失效"] = True
    return 新页剧本


def 引用次数(页剧本: Mapping[str, Any], 项ID: str) -> int:
    """这一项被多少张不同的页引用。计数在生成时算定，不随档案变化。"""
    return int((页剧本.get("引用计数") or {}).get(项ID, 0))


def 要求参考图(页剧本: Mapping[str, Any], 项ID: str) -> bool:
    """这一项要不要带参考图。

    人物身份与风格 ID 一律要求（DEC-6：正脸参考图、风格样张）；服装状态与场景卡只在被
    2 页以上引用时才要求，计数取自页剧本生成时算定的那一份。
    """
    if _前缀(项ID) in (身份引用, 风格引用):
        return True
    return bool((页剧本.get("要求带图") or {}).get(项ID))


def 页原文位置(页剧本: Mapping[str, Any], 页ID: str) -> list[dict[str, int]]:
    """这一页通过节拍指回的原文位置，按该页 节拍顺序 里给出的次序返回。"""
    页 = _找页(页剧本, 页ID)
    顺序表 = 页.get("节拍顺序")
    if not isinstance(顺序表, list):
        raise 页剧本非法(f"页 {页ID} 没有 节拍顺序")
    快照 = {条.get("顺序"): 条 for 条 in 页剧本.get("节拍快照") or []}
    位置: list[dict[str, int]] = []
    for 顺序 in 顺序表:
        条 = 快照.get(顺序)
        if 条 is None:
            raise 页剧本非法(f"页 {页ID} 指向的节拍不在冻结快照里：{顺序}")
        位置.append({"起": 条.get("原文起"), "止": 条.get("原文止")})
    return 位置


def 节拍已改(页剧本: Mapping[str, Any], 草稿: Mapping[str, Any]) -> bool:
    """页剧本冻结之后，草稿上的故事节拍有没有被改动。"""
    return list(页剧本.get("节拍快照") or []) != list(草稿.get("故事节拍") or [])


def 页剧本已失效(页剧本: Mapping[str, Any], 草稿: Mapping[str, Any]) -> bool:
    """这份页剧本还能不能用：整篇重写过的旧剧本，或节拍被改过，都算失效。"""
    return bool(页剧本.get("已失效")) or 节拍已改(页剧本, 草稿)


def 落实带图要求(档案: dict[str, Any], 页剧本: Mapping[str, Any]) -> dict[str, Any]:
    """把「要求带参考图、却还没有已确认参考图」的服装状态或场景卡退回未确认。

    契约的落地口径：计数升到 2 页以上时该项退回未确认，用 ITEM-2 的参考图能力补图并
    重新确认后才能出页。已有已确认参考图的项不动；人物身份与风格 ID 不走引用计数，也不动。

    只接受当前那一份页剧本：已失效的旧剧本带着旧计数，按它落实会把本不该要图的项卡住。
    要求带图的项 ID 在档案里找不到时直接报错——那说明档案的项 ID 已经对不上页剧本的引用
    （例如重抽后服装状态 ID 被重新编号），静默跳过会无声放掉「2 页以上必须有图」这条要求。
    """
    if 页剧本.get("已失效"):
        raise 页剧本非法("页剧本已失效，不能按它落实带图要求")
    for 项ID in 页剧本.get("要求带图") or {}:
        if _前缀(项ID) not in (服装引用, 场景引用):
            continue
        项 = _找档案项(档案, 项ID)
        if 项 is None:
            raise 页剧本非法(f"档案里找不到要求带图的项，项 ID 已经对不上：{项ID}")
        if not _图已确认(项.get("参考图")):
            项["确认状态"] = 未确认
    return 档案


# ---------- 校验 ----------


def _页表(
    输出: Mapping[str, Any],
    档案: Mapping[str, Any],
    类别: Mapping[str, str],
    已确认项: set[str],
    节拍表: Mapping[int, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    原始页 = 输出.get("页")
    if not isinstance(原始页, list) or not 原始页:
        raise 页剧本非法("页剧本至少要有页")
    页表 = [
        _页(页, f"页{序号}", 类别, 已确认项, 节拍表)
        for 序号, 页 in enumerate(原始页, start=1)
    ]
    _查阅读顺序(页表)
    _查描述(档案, 页表)
    return 页表


def _页(
    页: Any,
    页ID: str,
    类别: Mapping[str, str],
    已确认项: set[str],
    节拍表: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(页, Mapping):
        raise 页剧本非法(f"{页ID} 必须是对象")
    return {
        "页ID": 页ID,
        "分格": _分格表(页.get("分格"), 页ID),
        "节拍顺序": _节拍顺序(页.get("节拍顺序"), 页ID, 节拍表),
        "引用记录": _引用记录(页.get("引用记录"), 页ID, 类别, 已确认项),
    }


def _分格表(值: Any, 页ID: str) -> list[dict[str, Any]]:
    if not isinstance(值, list) or not 值:
        raise 页剧本非法(f"{页ID} 至少要有分格")
    分格表 = []
    for 序号, 格 in enumerate(值, start=1):
        if not isinstance(格, Mapping):
            raise 页剧本非法(f"{页ID} 第 {序号} 格必须是对象")
        对白 = 格.get("对白") or []
        if not isinstance(对白, list) or not all(isinstance(句, str) for 句 in 对白):
            raise 页剧本非法(f"{页ID} 第 {序号} 格的对白必须是字符串列表")
        分格表.append(
            {
                "画面": _文本(格.get("画面"), f"{页ID} 第 {序号} 格的画面"),
                "对白": list(对白),
            }
        )
    return 分格表


def _节拍顺序(
    值: Any, 页ID: str, 节拍表: Mapping[int, Mapping[str, Any]]
) -> list[int]:
    if not isinstance(值, list) or not 值:
        raise 页剧本非法(f"{页ID} 必须落在至少一条故事节拍上")
    顺序表 = []
    for 顺序 in 值:
        if isinstance(顺序, bool) or not isinstance(顺序, int):
            raise 页剧本非法(f"{页ID} 的节拍顺序必须是整数")
        if 顺序 not in 节拍表:
            raise 页剧本非法(f"{页ID} 指向不存在的节拍：{顺序}")
        if 顺序 not in 顺序表:
            顺序表.append(顺序)
    return 顺序表


def _引用记录(
    值: Any, 页ID: str, 类别: Mapping[str, str], 已确认项: set[str]
) -> dict[str, list[str]]:
    if not isinstance(值, Mapping):
        raise 页剧本非法(f"{页ID} 的引用记录必须是对象")
    多余 = [键 for 键 in 值 if 键 not in 引用类别]
    if 多余:
        raise 页剧本非法(f"{页ID} 的引用记录只能有四类键，多出：{多余}")
    记录: dict[str, list[str]] = {}
    for 键 in 引用类别:
        ID表 = 值.get(键) or []
        if not isinstance(ID表, list) or not all(isinstance(项ID, str) for 项ID in ID表):
            raise 页剧本非法(f"{页ID} 的引用记录.{键} 必须是 ID 列表")
        记录[键] = _去重([_查引用(项ID, 页ID, 键, 类别, 已确认项) for 项ID in ID表])
    return 记录


def _查引用(
    项ID: str, 页ID: str, 键: str, 类别: Mapping[str, str], 已确认项: set[str]
) -> str:
    实际 = 类别.get(项ID)
    if 实际 is None:
        raise 页剧本非法(f"{页ID} 引用了档案里没有的项：{项ID}")
    if 实际 != 键:
        raise 页剧本非法(f"{页ID} 把 {项ID}（{实际}）写进了 引用记录.{键}")
    if 项ID not in 已确认项:
        raise 页剧本非法(f"{页ID} 引用了还没确认的项：{项ID}")
    return 项ID


def _查阅读顺序(页表: list[dict[str, Any]]) -> None:
    """页剧本按阅读顺序排列：越靠后的页，起手的节拍不能往回退。"""
    上一条 = 0
    for 页 in 页表:
        本条 = min(页["节拍顺序"])
        if 本条 < 上一条:
            raise 页剧本非法(f"{页['页ID']} 的节拍往回退了：{本条} < {上一条}")
        上一条 = 本条


def _查描述(档案: Mapping[str, Any], 页表: list[dict[str, Any]]) -> None:
    """页剧本不许写外貌或服装描述：扫身份字段值与服装描述，命中就拒。"""
    for 页 in 页表:
        文本 = " ".join(_页文本(页))
        for 来源, 词 in _禁词表(档案):
            if 词 in 文本:
                raise 页剧本非法(f"{页['页ID']} 写了外貌或服装描述（{来源}）：{词}")


def _禁词表(档案: Mapping[str, Any]) -> list[tuple[str, str]]:
    禁词: list[tuple[str, str]] = []
    for 卡 in 档案.get("人物卡", []) or []:
        身份 = 卡.get("人物身份") or {}
        for 字段 in 人物身份字段:
            词 = _文本(身份.get(字段), "").strip()
            if len(词) >= 描述扫描下限:
                禁词.append((f"人物「{卡.get('名称')}」的{字段}", 词))
        for 套 in 卡.get("服装状态列表", []) or []:
            词 = _文本(套.get("描述"), "").strip()
            if len(词) >= 描述扫描下限:
                禁词.append((f"服装状态 {套.get('服装状态ID')}", 词))
    return 禁词


def _页文本(页: Mapping[str, Any]) -> list[str]:
    文本: list[str] = []
    for 格 in 页["分格"]:
        文本.append(格["画面"])
        文本.extend(格["对白"])
    return 文本


# ---------- 内部 ----------


def _统计计数(页表: list[dict[str, Any]]) -> dict[str, int]:
    """按引用记录统计每项被多少不同页引用（每页已去重，所以是不同页数）。"""
    计数: dict[str, int] = {}
    for 页 in 页表:
        for 键 in 引用类别:
            for 项ID in 页["引用记录"][键]:
                计数[项ID] = 计数.get(项ID, 0) + 1
    return 计数


def _项类别(档案: Mapping[str, Any]) -> dict[str, str]:
    """档案里每一项 ID 到它属于哪一类引用的映射（含未确认项）。"""
    类别: dict[str, str] = {}
    for 卡 in 档案.get("人物卡", []) or []:
        类别[卡["身份ID"]] = 身份引用
        for 套 in 卡.get("服装状态列表", []) or []:
            类别[套["服装状态ID"]] = 服装引用
    for 场 in 档案.get("场景卡", []) or []:
        类别[场["场景卡ID"]] = 场景引用
    风格块 = 档案.get("风格ID") or {}
    if 风格块.get("风格ID"):
        类别[风格块["风格ID"]] = 风格引用
    return 类别


def _已确认项(档案: Mapping[str, Any]) -> set[str]:
    集合: set[str] = set()
    for 卡 in 档案.get("人物卡", []) or []:
        if 卡.get("身份确认状态") == 已确认:
            集合.add(卡["身份ID"])
        for 套 in 卡.get("服装状态列表", []) or []:
            if 套.get("确认状态") == 已确认:
                集合.add(套["服装状态ID"])
    for 场 in 档案.get("场景卡", []) or []:
        if 场.get("确认状态") == 已确认:
            集合.add(场["场景卡ID"])
    风格块 = 档案.get("风格ID") or {}
    if 风格块.get("确认状态") == 已确认 and 风格块.get("风格ID"):
        集合.add(风格块["风格ID"])
    return 集合


def _节拍表(草稿: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    表: dict[int, Mapping[str, Any]] = {}
    for 条 in 草稿.get("故事节拍", []) or []:
        顺序 = 条.get("顺序")
        if isinstance(顺序, int) and not isinstance(顺序, bool):
            表[顺序] = 条
    return 表


def _节拍文本(草稿: Mapping[str, Any]) -> str:
    行 = [
        f"{条.get('顺序')}. {条.get('摘要')}（原文起 {条.get('原文起')}，原文止 {条.get('原文止')}）"
        for 条 in 草稿.get("故事节拍", []) or []
    ]
    return "\n".join(行) if 行 else "（没有故事节拍）"


def _档案文本(档案: Mapping[str, Any]) -> str:
    """只列已确认的项：模型看不到未确认的项，也就写不进引用记录。"""
    行 = ["人物卡："]
    有 = False
    for 卡 in 档案.get("人物卡", []) or []:
        if 卡.get("身份确认状态") != 已确认:
            continue
        有 = True
        行.append(f"- {卡['身份ID']}（名称 {卡.get('名称')}）")
        for 套 in 卡.get("服装状态列表", []) or []:
            if 套.get("确认状态") == 已确认:
                行.append(f"  - {套['服装状态ID']}（名称 {套.get('名称')}）")
    if not 有:
        行.append("- （没有已确认的人物卡）")
    行.append("场景卡：")
    有 = False
    for 场 in 档案.get("场景卡", []) or []:
        if 场.get("确认状态") == 已确认:
            有 = True
            行.append(f"- {场['场景卡ID']}（名称 {场.get('名称')}）")
    if not 有:
        行.append("- （没有已确认的场景卡）")
    行.append("风格ID：")
    风格块 = 档案.get("风格ID") or {}
    if 风格块.get("确认状态") == 已确认:
        行.append(f"- {风格块['风格ID']}")
    else:
        行.append("- （风格 ID 还没确认）")
    return "\n".join(行)


def _找页(页剧本: Mapping[str, Any], 页ID: str) -> Mapping[str, Any]:
    for 页 in 页剧本.get("页", []) or []:
        if 页.get("页ID") == 页ID:
            return 页
    raise 页剧本非法(f"页剧本里没有这一页：{页ID}")


def _找档案项(档案: Mapping[str, Any], 项ID: str) -> dict[str, Any] | None:
    try:
        return 找项(档案, 项ID)
    except 档案非法:
        return None


def _前缀(项ID: str) -> str:
    if not isinstance(项ID, str):
        raise 页剧本非法("项 ID 必须是字符串")
    for 文, 类 in ID前缀.items():
        if 项ID.startswith(文):
            return 类
    raise 页剧本非法(f"认不出这个项 ID：{项ID}")


def _图已确认(图: Any) -> bool:
    return isinstance(图, Mapping) and 图.get("确认状态") == 已确认


def _世代(页剧本: Mapping[str, Any]) -> int:
    值 = 页剧本.get("世代")
    return 值 if isinstance(值, int) and not isinstance(值, bool) else 1


def _去重(值: list[str]) -> list[str]:
    已见: set[str] = set()
    结果 = []
    for 项 in 值:
        if 项 not in 已见:
            已见.add(项)
            结果.append(项)
    return 结果


def _文本(值: Any, 名字: str) -> str:
    if 值 is None:
        return ""
    if not isinstance(值, str):
        raise 页剧本非法(f"{名字}必须是字符串")
    return 值
