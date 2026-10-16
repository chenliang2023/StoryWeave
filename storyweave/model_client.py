"""文本模型供应商适配层：把「提示 -> 文本」的可注入函数落到一个真实可用的实现。

抽取本身（storyweave.extract）只依赖 `提示 -> 文本` 这个函数形状，不绑定供应商。
本模块负责那一层之外的接线：配置、请求形状、响应解析、错误归一。

## 默认供应商

默认走 [OI] 兼容的 chat completions 形状（`POST {base_url}/chat/completions`），
默认值由 `从环境变量读配置()` 给出：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `STORYWEAVE_供应商` | `openai兼容` | 只是标签，记在配置里便于排查 |
| `STORYWEAVE_模型` | `gpt-4o-mini` | 模型名，按需改 |
| `STORYWEAVE_BASE_URL` | `https://api.openai.com/v1` | 端点前缀，末尾斜杠会被吃掉 |
| `STORYWEAVE_API_KEY` | 空 | 缺省不给 key，也不从别处猜 |
| `STORYWEAVE_超时秒` | `60.0` | 必须为正数 |

## 怎么换供应商

本模块只实现一种线上协议（[OI] 兼容的 chat completions）。主流供应商都提供这个形状，
所以换供应商通常只改配置、不改代码：

- 换到兼容端点（自建网关、其他兼容服务）：设 `STORYWEAVE_BASE_URL` 与 `STORYWEAVE_模型`。
- 本地端点不校验 key：`STORYWEAVE_API_KEY` 留空，请求就不带 `Authorization` 头。
- 供应商协议不是这个形状：不要改本模块的解析逻辑，另写一个 `提示 -> 文本` 的函数，
  直接传给 `storyweave.extract.抽取草稿` 的 `调用模型` 参数即可；抽取不关心供应商。

## 接线方式

    from storyweave import 从环境变量读配置, 构建调用模型, 抽取短篇草稿

    调用模型 = 构建调用模型(从环境变量读配置())
    草稿 = 抽取短篇草稿(原文, 调用模型)

## 网络与测试

HTTP 发送是可注入的 `发送(请求) -> 响应`；默认实现 `默认发送` 用标准库 `urllib.request`，
不引第三方依赖。测试一律注入假的 `发送`，一次真实 HTTP 都不会发生。

## 错误

所有失败都归一到 `模型调用失败`：非 200、响应体不是 JSON、缺少
`choices[0].message.content`、发送过程中的超时或网络异常。异常信息里不带 api_key。
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

默认供应商 = "openai兼容"
默认模型 = "gpt-4o-mini"
默认base_url = "https://api.openai.com/v1"
默认超时秒 = 60.0

环境变量名 = {
    "供应商": "STORYWEAVE_供应商",
    "模型": "STORYWEAVE_模型",
    "base_url": "STORYWEAVE_BASE_URL",
    "api_key": "STORYWEAVE_API_KEY",
    "超时秒": "STORYWEAVE_超时秒",
}

脱敏替代 = "***"


class 模型调用失败(Exception):
    """调模型这条路上的任何失败。信息里不带 api_key。"""


@dataclass(frozen=True)
class 供应商配置:
    """一个供应商端点的接线信息。"""

    供应商: str = 默认供应商
    模型: str = 默认模型
    base_url: str = 默认base_url
    api_key: str = ""
    超时秒: float = 默认超时秒

    def 端点(self) -> str:
        """chat completions 的完整 URL。末尾斜杠不会拼出双斜杠。"""
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


def 从环境变量读配置(环境: Mapping[str, str] | None = None) -> 供应商配置:
    """从环境变量读配置，缺省用模块默认值。传入 环境 可换一份映射（测试用）。"""
    源 = os.environ if 环境 is None else 环境

    def 取值(键: str, 默认: str) -> str:
        原值 = 源.get(环境变量名[键], "")
        return 原值 if 原值 else 默认

    超时原文 = 源.get(环境变量名["超时秒"], "").strip()
    if 超时原文:
        try:
            超时秒 = float(超时原文)
        except ValueError:
            raise 模型调用失败(f"{环境变量名['超时秒']} 必须是数字，当前为 {超时原文!r}") from None
    else:
        超时秒 = 默认超时秒
    if 超时秒 <= 0:
        raise 模型调用失败(f"{环境变量名['超时秒']} 必须是正数，当前为 {超时秒}")

    return 供应商配置(
        供应商=取值("供应商", 默认供应商),
        模型=取值("模型", 默认模型),
        base_url=取值("base_url", 默认base_url),
        api_key=源.get(环境变量名["api_key"], "").strip(),
        超时秒=超时秒,
    )


def 默认发送(请求: 请求) -> 响应:
    """用标准库 urllib.request 真发一次 HTTP。

    只负责发送：非 200 也当成一次正常返回（HTTPError 里读回响应体）。
    网络层异常（超时、连不上）原样抛出，由 构建调用模型 归一成 模型调用失败。
    """
    网络请求 = urllib_request.Request(
        url=请求.url,
        data=请求.体,
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
    if not isinstance(配置, 供应商配置):
        raise TypeError("配置 必须是 供应商配置")
    if not callable(发送):
        raise TypeError("发送 必须是可调用的函数")

    def 调用模型(提示: str) -> str:
        if not isinstance(提示, str):
            raise TypeError("提示必须是字符串")
        报文 = _造请求(配置, 提示)
        try:
            回应 = 发送(报文)
        except Exception as 错:
            失败信息 = _脱敏(f"{type(错).__name__}: {错}", 配置.api_key)
        else:
            return _取文本(回应, 配置.api_key)
        # 在 except 块之外抛出：不留 __context__，原异常（可能带 api_key）不会被回溯带走。
        raise 模型调用失败(f"发送请求失败：{失败信息}")

    return 调用模型


def _造请求(配置: 供应商配置, 提示: str) -> 请求:
    体 = json.dumps(
        {"model": 配置.模型, "messages": [{"role": "user", "content": 提示}]},
        ensure_ascii=False,
    ).encode("utf-8")
    头部 = {"Content-Type": "application/json"}
    if 配置.api_key:
        头部["Authorization"] = f"Bearer {配置.api_key}"
    return 请求(url=配置.端点(), 方法="POST", 体=体, 头部=头部, 超时秒=配置.超时秒)


def _取文本(回应: Any, api_key: str) -> str:
    """从响应里取出 choices[0].message.content；任何不合形状都归一到 模型调用失败。"""
    if not isinstance(回应, 响应):
        raise 模型调用失败(f"发送返回的不是 响应，而是 {type(回应).__name__}")

    if 回应.状态码 != 200:
        片段 = _脱敏(_截断(回应.文本), api_key)
        raise 模型调用失败(f"模型返回状态码 {回应.状态码}：{片段}")
    try:
        数据 = json.loads(回应.文本)
    except json.JSONDecodeError as 错:
        解析原因 = 错.msg
    else:
        解析原因 = ""
    if 解析原因:
        # 在 except 块之外抛出：JSONDecodeError 的 .doc 会留着响应体，可能含 api_key。
        片段 = _脱敏(_截断(回应.文本), api_key)
        raise 模型调用失败(f"模型返回的不是合法 JSON（{解析原因}）：{片段}")

    if not isinstance(数据, Mapping):
        raise 模型调用失败("模型返回的 JSON 必须是对象")
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
