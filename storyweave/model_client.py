"""文本模型与图像模型的供应商适配层：配置、调用、拉取模型、图像生成。

抽取本身（storyweave.extract）只依赖 `提示 -> 文本` 这个函数形状，不绑定供应商。
本模块负责那一层之外的接线：配置、请求形状、响应解析、错误归一。

## 默认供应商

默认走 [OI] 兼容的三种端点：`POST {base_url}/chat/completions`（文本）、
`GET {base_url}/models`（拉取模型）、`POST {base_url}/images/generations`（图像生成）。
默认值由两个读配置函数给出：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `STORYWEAVE_供应商` | `openai兼容` | 只是标签，记在配置里便于排查 |
| `STORYWEAVE_模型` | `gpt-4o-mini` | 文本模型名 |
| `STORYWEAVE_BASE_URL` | `https://api.openai.com/v1` | 端点前缀，末尾斜杠会被吃掉 |
| `STORYWEAVE_API_KEY` | 空 | 缺省不给 key，也不从别处猜 |
| `STORYWEAVE_超时秒` | `60.0` | 必须为正数 |
| `STORYWEAVE_图像_供应商` | `openai兼容` | 图像供应商标签 |
| `STORYWEAVE_图像_模型` | `gpt-image-1` | 图像模型名 |
| `STORYWEAVE_图像_BASE_URL` | `https://api.openai.com/v1` | 图像端点前缀 |
| `STORYWEAVE_图像_API_KEY` | 空 | 图像 key 缺省为空 |
| `STORYWEAVE_图像_超时秒` | `60.0` | 必须为正数 |

`从环境变量读配置()` 取文本那一组，`从环境变量读图像配置()` 取图像那一组；两组互不串。

## 怎么换供应商

本模块只实现一种线上协议（[OI] 兼容）。主流供应商都提供这个形状，换供应商通常只改配置：

- 换到兼容端点（自建网关、其他兼容服务）：改对应的 `BASE_URL` 与 `模型`。
- 端点不校验 key：把 `API_KEY` 留空，请求就不带 `Authorization` 头。
- 文本与图像不在同一端点：分别设两组环境变量。
- 协议不是这个形状：不要改本模块的解析逻辑，另写一个 `提示 -> 文本`（或 `提示 -> 图片字节`）
  的函数，直接传给 `抽取草稿` 的 `调用模型` 或 `storyweave.archive.生成参考图` 的 `生成`。

## 接线方式

    from storyweave import 从环境变量读配置, 从环境变量读图像配置, 构建调用模型, 构建生成图, 抽取短篇草稿

    草稿 = 抽取短篇草稿(原文, 构建调用模型(从环境变量读配置()))
    生成 = 构建生成图(从环境变量读图像配置())
    可选模型 = 拉取模型(从环境变量读配置())   # 或 从环境变量读图像配置()，看要列哪一家的

## 网络与测试

HTTP 发送是可注入的 `发送(请求) -> 响应`；默认实现 `默认发送` 用标准库 `urllib.request`，
不引第三方依赖。测试一律注入假的 `发送`，一次真实 HTTP 都不会发生。

## 错误

所有失败都归一到 `模型调用失败`：非 200、响应体不是 JSON、响应缺少需要的字段、
发送过程中的超时或网络异常。异常信息与其因果链都不带 api_key。
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

默认供应商 = "openai兼容"
默认模型 = "gpt-4o-mini"
默认图像模型 = "gpt-image-1"
默认base_url = "https://api.openai.com/v1"
默认超时秒 = 60.0

环境变量名 = {
    "供应商": "STORYWEAVE_供应商",
    "模型": "STORYWEAVE_模型",
    "base_url": "STORYWEAVE_BASE_URL",
    "api_key": "STORYWEAVE_API_KEY",
    "超时秒": "STORYWEAVE_超时秒",
}

图像环境变量名 = {
    "供应商": "STORYWEAVE_图像_供应商",
    "模型": "STORYWEAVE_图像_模型",
    "base_url": "STORYWEAVE_图像_BASE_URL",
    "api_key": "STORYWEAVE_图像_API_KEY",
    "超时秒": "STORYWEAVE_图像_超时秒",
}

脱敏替代 = "***"


class 模型调用失败(Exception):
    """调模型这条路上的任何失败。信息与其因果链都不带 api_key。"""


@dataclass(frozen=True)
class 供应商配置:
    """一个供应商端点的接线信息。"""

    供应商: str = 默认供应商
    模型: str = 默认模型
    base_url: str = 默认base_url
    api_key: str = ""
    超时秒: float = 默认超时秒

    def 端点(self) -> str:
        """文本 chat completions 的完整 URL。末尾斜杠不会拼出双斜杠。"""
        return f"{self.base_url.rstrip('/')}/chat/completions"


@dataclass(frozen=True)
class 请求:
    """一次 HTTP 发送的全部输入。发送实现只看这个对象。"""

    url: str
    方法: str
    体: bytes
    头部: Mapping[str, str] = field(default_factory=dict)
    超时秒: float = 默认超时秒


@dataclass(frozen=True)
class 响应:
    """一次 HTTP 发送的结果。非 200 也算一次正常返回，由上层判定。"""

    状态码: int
    文本: str


def 模型列表端点(配置: 供应商配置) -> str:
    """拉取模型的完整 URL。"""
    return f"{配置.base_url.rstrip('/')}/models"


def 图像生成端点(配置: 供应商配置) -> str:
    """图像生成的完整 URL。"""
    return f"{配置.base_url.rstrip('/')}/images/generations"


def 从环境变量读配置(环境: Mapping[str, str] | None = None) -> 供应商配置:
    """读文本模型那一组环境变量，缺省用模块默认值。"""
    return _读配置(os.environ if 环境 is None else 环境, 环境变量名, 默认模型)


def 从环境变量读图像配置(环境: Mapping[str, str] | None = None) -> 供应商配置:
    """读图像模型那一组环境变量（`STORYWEAVE_图像_*`），缺省用模块默认值。"""
    return _读配置(os.environ if 环境 is None else 环境, 图像环境变量名, 默认图像模型)


def 默认发送(请求: 请求) -> 响应:
    """用标准库 urllib.request 真发一次 HTTP。

    只负责发送：非 200 也当成一次正常返回（HTTPError 里读回响应体）。
    网络层异常（超时、连不上）原样抛出，由上层归一成 模型调用失败。
    """
    网络请求 = urllib_request.Request(
        url=请求.url,
        data=请求.体 if 请求.体 else None,
        headers=dict(请求.头部),
        method=请求.方法,
    )
    try:
        with urllib_request.urlopen(网络请求, timeout=请求.超时秒) as 回应:
            return 响应(状态码=int(回应.status), 文本=回应.read().decode("utf-8", errors="replace"))
    except urllib_error.HTTPError as 错:
        return 响应(状态码=int(错.code), 文本=错.read().decode("utf-8", errors="replace"))


def 构建调用模型(
    配置: 供应商配置, 发送: Callable[[请求], 响应] = 默认发送
) -> Callable[[str], str]:
    """把配置落成一个 `提示 -> 文本` 的函数，形状与 抽取草稿 的 调用模型 参数一致。

    发送 可注入：默认 默认发送 走真网络；测试注入假发送，一次 HTTP 都不会发生。
    """
    _查入参(配置, 发送)

    def 调用模型(提示: str) -> str:
        报文 = _造文本请求(配置, 提示)
        回应 = _取响应(发送, 报文, 配置.api_key)
        return _取文本(回应, 配置.api_key)

    return 调用模型


def 拉取模型(配置: 供应商配置, 发送: Callable[[请求], 响应] = 默认发送) -> list[str]:
    """拉取该供应商可用的模型名，去重后按名字排序返回。

    走 [OI] 兼容的 `GET {base_url}/models`，取 `data[*].id`。
    文本供应商与图像供应商用同一个形状，所以传哪一组配置就列哪一家的模型。
    """
    _查入参(配置, 发送)
    报文 = 请求(
        url=模型列表端点(配置),
        方法="GET",
        体=b"",
        头部=_认证头(配置),
        超时秒=配置.超时秒,
    )
    回应 = _取响应(发送, 报文, 配置.api_key)
    数据 = _取json(回应, 配置.api_key)

    模型表 = 数据.get("data")
    if not isinstance(模型表, list):
        raise 模型调用失败("模型列表返回里没有 data 列表")
    名表: list[str] = []
    for 条 in 模型表:
        if not isinstance(条, Mapping) or not isinstance(条.get("id"), str):
            raise 模型调用失败("模型列表里每一条都要有字符串 id")
        名表.append(条["id"])
    return sorted(set(名表))


def 构建生成图(
    配置: 供应商配置, 发送: Callable[[请求], 响应] = 默认发送
) -> Callable[[str], bytes]:
    """把配置落成一个 `提示 -> 图片字节` 的函数，形状与 生成参考图 的 生成 参数一致。

    走 [OI] 兼容的 `POST {base_url}/images/generations`，取 `data[0].b64_json` 解码。
    只接 b64_json：返回图片 URL 的供应商需要另写一个 `提示 -> 图片字节` 的函数。
    """
    _查入参(配置, 发送)

    def 生成(提示: str) -> bytes:
        报文 = _造图像请求(配置, 提示)
        回应 = _取响应(发送, 报文, 配置.api_key)
        数据 = _取json(回应, 配置.api_key)

        图表 = 数据.get("data")
        if not isinstance(图表, list) or not 图表:
            raise 模型调用失败("图像返回里没有 data[0]")
        首张 = 图表[0]
        if not isinstance(首张, Mapping):
            raise 模型调用失败("图像返回里的 data[0] 必须是对象")
        编码 = 首张.get("b64_json")
        if not isinstance(编码, str):
            raise 模型调用失败("图像返回里缺少 data[0].b64_json（本实现不接图片 URL）")
        try:
            图片 = base64.b64decode(编码, validate=True)
        except Exception as 错:
            解码原因 = type(错).__name__
        else:
            return 图片
        raise 模型调用失败(f"图像返回里的 data[0].b64_json 不是合法 base64（{解码原因}）")

    return 生成


# ---------- 内部 ----------


def _读配置(源: Mapping[str, str], 变量名: Mapping[str, str], 默认模型名: str) -> 供应商配置:
    def 取值(键: str, 默认: str) -> str:
        原值 = 源.get(变量名[键], "")
        return 原值 if 原值 else 默认

    超时键 = 变量名["超时秒"]
    超时原文 = 源.get(超时键, "").strip()
    if 超时原文:
        try:
            超时秒 = float(超时原文)
        except ValueError:
            raise 模型调用失败(f"{超时键} 必须是数字，当前为 {超时原文!r}") from None
    else:
        超时秒 = 默认超时秒
    if 超时秒 <= 0:
        raise 模型调用失败(f"{超时键} 必须是正数，当前为 {超时秒}")

    return 供应商配置(
        供应商=取值("供应商", 默认供应商),
        模型=取值("模型", 默认模型名),
        base_url=取值("base_url", 默认base_url),
        api_key=源.get(变量名["api_key"], "").strip(),
        超时秒=超时秒,
    )


def _查入参(配置: Any, 发送: Any) -> None:
    if not isinstance(配置, 供应商配置):
        raise TypeError("配置 必须是 供应商配置")
    if not callable(发送):
        raise TypeError("发送 必须是可调用的函数")


def _认证头(配置: 供应商配置) -> dict[str, str]:
    头部 = {"Content-Type": "application/json"}
    if 配置.api_key:
        头部["Authorization"] = f"Bearer {配置.api_key}"
    return 头部


def _造文本请求(配置: 供应商配置, 提示: str) -> 请求:
    if not isinstance(提示, str):
        raise TypeError("提示必须是字符串")
    体 = json.dumps(
        {"model": 配置.模型, "messages": [{"role": "user", "content": 提示}]},
        ensure_ascii=False,
    ).encode("utf-8")
    return 请求(url=配置.端点(), 方法="POST", 体=体, 头部=_认证头(配置), 超时秒=配置.超时秒)


def _造图像请求(配置: 供应商配置, 提示: str) -> 请求:
    if not isinstance(提示, str):
        raise TypeError("提示必须是字符串")
    体 = json.dumps({"model": 配置.模型, "prompt": 提示}, ensure_ascii=False).encode("utf-8")
    return 请求(
        url=图像生成端点(配置), 方法="POST", 体=体, 头部=_认证头(配置), 超时秒=配置.超时秒
    )


def _取响应(发送: Callable[[请求], 响应], 报文: 请求, api_key: str) -> 响应:
    """发一次请求，把发送过程的异常归一成 模型调用失败。

    失败信息在 except 块之外抛出：不留 __context__，原异常（可能带 api_key）不会被回溯带走。
    """
    try:
        回应 = 发送(报文)
    except Exception as 错:
        失败信息 = f"发送请求失败：{_脱敏(f'{type(错).__name__}: {错}', api_key)}"
    else:
        if isinstance(回应, 响应):
            return 回应
        失败信息 = f"发送返回的不是 响应，而是 {type(回应).__name__}"
    raise 模型调用失败(失败信息)


def _取json(回应: 响应, api_key: str) -> Mapping[str, Any]:
    """把响应体读成一个 JSON 对象；非 200 或不合形状都归一成 模型调用失败。"""
    if 回应.状态码 != 200:
        raise 模型调用失败(f"模型返回状态码 {回应.状态码}：{_脱敏(_截断(回应.文本), api_key)}")

    try:
        数据 = json.loads(回应.文本)
    except json.JSONDecodeError as 错:
        解析原因 = 错.msg
    else:
        解析原因 = ""
    if 解析原因:
        # 在 except 块之外抛出：JSONDecodeError 的 .doc 会留着响应体，可能含 api_key。
        raise 模型调用失败(
            f"模型返回的不是合法 JSON（{解析原因}）：{_脱敏(_截断(回应.文本), api_key)}"
        )

    if not isinstance(数据, Mapping):
        raise 模型调用失败("模型返回的 JSON 必须是对象")
    return 数据


def _取文本(回应: 响应, api_key: str) -> str:
    """从响应里取出 choices[0].message.content。"""
    数据 = _取json(回应, api_key)

    选项 = 数据.get("choices")
    if not isinstance(选项, list) or not 选项:
        raise 模型调用失败("模型返回里没有 choices[0]")
    首条 = 选项[0]
    if not isinstance(首条, Mapping):
        raise 模型调用失败("模型返回里的 choices[0] 必须是对象")
    消息 = 首条.get("message")
    if not isinstance(消息, Mapping):
        raise 模型调用失败("模型返回里缺少 choices[0].message")
    内容 = 消息.get("content")
    if not isinstance(内容, str):
        raise 模型调用失败(f"模型返回里缺少 choices[0].message.content 文本，当前为 {type(内容).__name__}")
    return 内容


def _脱敏(文本: str, api_key: str) -> str:
    if not api_key:
        return 文本
    return 文本.replace(api_key, 脱敏替代)


def _截断(文本: str, 上限: int = 200) -> str:
    return 文本 if len(文本) <= 上限 else 文本[:上限] + "…"
