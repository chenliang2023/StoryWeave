"""ITEM-1 · 文本模型供应商适配层：配置、请求形状、响应解析、错误路径、端到端。

全部用例用假的 `发送` 注入，绝不发生真实 HTTP；连一次真实网络调用都没有。
断言里不打印真实 key，只检查「信息里不含 key」。
"""

import json

import pytest

from storyweave import 抽取草稿, 整篇可出页
from storyweave.model_client import (
    供应商配置,
    从环境变量读配置,
    响应,
    构建调用模型,
    模型调用失败,
    默认发送,
    请求,
)

假key = "sk-假key-不该出现在任何信息里"
样本 = "有人摇身一变，成了狼。"


def _配置(**覆盖):
    参数 = {
        "供应商": "测试供应商",
        "模型": "测试模型",
        "base_url": "https://例子.测试/v1",
        "api_key": 假key,
        "超时秒": 12.5,
    }
    参数.update(覆盖)
    return 供应商配置(**参数)


def _内容(文本: str) -> str:
    """包成 [OI] 兼容响应体：choices[0].message.content。"""
    return json.dumps({"choices": [{"message": {"content": 文本}}]}, ensure_ascii=False)


def _假发送(响应体=None, 状态码=200, 记录=None, 抛出=None, 原样文本=None):
    """假的 发送(请求) -> 响应。记录收到的请求，便于断言形状。"""

    def 发送(请求):
        if 记录 is not None:
            记录.append(请求)
        if 抛出 is not None:
            raise 抛出
        return 响应(状态码=状态码, 文本=原样文本 if 原样文本 is not None else _内容(响应体 or ""))

    return 发送


def _草稿输出(无主线索=()):
    return {
        "人物": [],
        "场景": [],
        "风格ID": "水墨",
        "故事节拍": [],
        "无主线索": list(无主线索),
    }


# ---------- 配置 ----------


def test_配置是带五个字段的数据对象():
    配置 = _配置()
    assert 配置.供应商 == "测试供应商"
    assert 配置.模型 == "测试模型"
    assert 配置.base_url == "https://例子.测试/v1"
    assert 配置.api_key == 假key
    assert 配置.超时秒 == 12.5
    assert 配置 == _配置(), "同字段的配置应相等"


def _链上文(错) -> str:
    """把一个异常和它整条因果链（__cause__ / __context__）的文字拼起来。"""
    片段 = []
    当前 = 错
    while 当前 is not None:
        片段.append(f"{type(当前).__name__}: {当前}")
        for 属性 in ("doc", "filename", "url"):
            值 = getattr(当前, 属性, None)
            if isinstance(值, str):
                片段.append(值)
        下一个 = 当前.__cause__ if 当前.__cause__ is not None else 当前.__context__
        当前 = 下一个
    return " | ".join(片段)


def test_从环境变量读配置(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STORYWEAVE_供应商", "环境供应商")
    monkeypatch.setenv("STORYWEAVE_模型", "环境模型")
    monkeypatch.setenv("STORYWEAVE_BASE_URL", "https://环境.测试/v1")
    monkeypatch.setenv("STORYWEAVE_API_KEY", "环境key")
    monkeypatch.setenv("STORYWEAVE_超时秒", "7.5")

    配置 = 从环境变量读配置()
    assert 配置.供应商 == "环境供应商"
    assert 配置.模型 == "环境模型"
    assert 配置.base_url == "https://环境.测试/v1"
    assert 配置.api_key == "环境key"
    assert 配置.超时秒 == 7.5


def test_环境变量缺省时给出合理值(monkeypatch: pytest.MonkeyPatch):
    for 名 in ("供应商", "模型", "BASE_URL", "API_KEY", "超时秒"):
        monkeypatch.delenv(f"STORYWEAVE_{名}", raising=False)

    配置 = 从环境变量读配置()
    assert 配置.供应商
    assert 配置.模型
    assert 配置.base_url.startswith("https://")
    assert 配置.api_key == "", "缺省不给 key，不猜也不读别处"
    assert 配置.超时秒 > 0
    assert isinstance(配置.超时秒, float)


def test_超时秒不是正数时拒绝(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STORYWEAVE_超时秒", "0")
    with pytest.raises(模型调用失败):
        从环境变量读配置()
    monkeypatch.setenv("STORYWEAVE_超时秒", "不是数字")
    with pytest.raises(模型调用失败):
        从环境变量读配置()


def test_构建调用模型校验入参():
    with pytest.raises(TypeError):
        构建调用模型({"不是": "配置"})
    with pytest.raises(TypeError):
        构建调用模型(_配置(), 发送="这不是函数")


# ---------- 请求形状 ----------


def test_产出的函数正是提示到文本的模型调用():
    调用模型 = 构建调用模型(_配置(), 发送=_假发送("原样返回"))
    assert callable(调用模型)
    assert 调用模型("随便一段提示") == "原样返回"


def test_请求形状是_oi_兼容的_chat_completions():
    记录 = []
    调用模型 = 构建调用模型(_配置(), 发送=_假发送(_内容("好的").strip('"'), 记录=记录))
    调用模型("请通读这段原文。")

    assert len(记录) == 1
    请求 = 记录[0]
    assert 请求.url == "https://例子.测试/v1/chat/completions"
    assert 请求.方法 == "POST"
    assert 请求.超时秒 == 12.5

    头部 = {名.lower(): 值 for 名, 值 in 请求.头部.items()}
    assert 头部["content-type"] == "application/json"
    assert 头部["authorization"] == f"Bearer {假key}", "带上 Authorization，但断言不打印真实 key"

    体 = json.loads(请求.体.decode("utf-8"))
    assert 体["model"] == "测试模型"
    assert [条["role"] for 条 in 体["messages"]] == ["user"]
    assert 体["messages"][0]["content"] == "请通读这段原文。"


def test_base_url_末尾斜杠不会拼出双斜杠():
    记录 = []
    调用模型 = 构建调用模型(_配置(base_url="https://例子.测试/v1/"), 发送=_假发送("", 记录=记录))
    调用模型("提示")
    assert 记录[0].url == "https://例子.测试/v1/chat/completions"


def test_没配_key_时不发_authorization_头():
    记录 = []
    调用模型 = 构建调用模型(_配置(api_key=""), 发送=_假发送("", 记录=记录))
    调用模型("提示")
    头部 = {名.lower(): 值 for 名, 值 in 记录[0].头部.items()}
    assert "authorization" not in 头部


def test_提示原样进入请求体():
    记录 = []
    调用模型 = 构建调用模型(_配置(), 发送=_假发送("", 记录=记录))
    提示 = "把这段原文抽成草稿：有人摇身一变，成了狼。"
    调用模型(提示)
    体 = json.loads(记录[0].体.decode("utf-8"))
    assert 体["messages"][0]["content"] == 提示


# ---------- 响应解析 ----------


def test_正常响应取_choices_零号_message_content():
    调用模型 = 构建调用模型(_配置(), 发送=_假发送(原样文本=_内容("正文一段")))
    assert 调用模型("提示") == "正文一段"


def test_带代码围栏的响应能直接喂给抽取草稿():
    """抽取草稿 里已有 _去代码围栏：适配层原样返回文本，围栏由那一层剥掉。"""
    围栏文本 = "```json\n" + json.dumps(_草稿输出([{"类别": "变身", "片段": 样本}]), ensure_ascii=False) + "\n```"
    调用模型 = 构建调用模型(_配置(), 发送=_假发送(原样文本=_内容(围栏文本)))

    草稿 = 抽取草稿(样本, 调用模型)
    assert len(草稿["无主线索"]) == 1
    assert 草稿["无主线索"][0]["类别"] == "变身"
    assert 整篇可出页(草稿) is False


# ---------- 错误路径 ----------


def test_非两百状态码转成模型调用失败():
    调用模型 = 构建调用模型(_配置(), 发送=_假发送(状态码=500, 原样文本='{"error":"服务器炸了"}'))
    with pytest.raises(模型调用失败) as 捕获:
        (调用模型("提示"))
    assert "500" in str(捕获.value)


def test_响应体不是_json_时转成模型调用失败():
    调用模型 = 构建调用模型(_配置(), 发送=_假发送(原样文本="这不是 JSON"))
    with pytest.raises(模型调用失败):
        调用模型("提示")


def test_缺少_choices_时转成模型调用失败():
    调用模型 = 构建调用模型(_配置(), 发送=_假发送(原样文本='{"choices": []}'))
    with pytest.raises(模型调用失败):
        调用模型("提示")


def test_缺少_content_时转成模型调用失败():
    调用模型 = 构建调用模型(_配置(), 发送=_假发送(原样文本='{"choices": [{"message": {}}]}'))
    with pytest.raises(模型调用失败):
        调用模型("提示")


def test_content_不是字符串时转成模型调用失败():
    调用模型 = 构建调用模型(_配置(), 发送=_假发送(原样文本='{"choices": [{"message": {"content": 42}}]}'))
    with pytest.raises(模型调用失败):
        调用模型("提示")


def test_发送抛异常时转成模型调用失败():
    for 异常 in (TimeoutError("超时"), OSError("网络不通"), ValueError("随便什么错")):
        调用模型 = 构建调用模型(_配置(), 发送=_假发送(抛出=异常))
        with pytest.raises(模型调用失败):
            调用模型("提示")


def test_错误信息里不含_api_key():
    """五条错误路径逐个检查：非 200、非 JSON、缺字段、发送抛异常。"""
    用例 = [
        _假发送(状态码=401, 原样文本='{"error":"unauthorized"}'),
        _假发送(原样文本="不是 JSON"),
        _假发送(原样文本='{"choices": []}'),
        _假发送(原样文本='{"choices": [{"message": {}}]}'),
        _假发送(抛出=OSError(f"连接被拒（对方回了 {假key}）")),
    ]
    for 发送 in 用例:
        调用模型 = 构建调用模型(_配置(), 发送=发送)
        with pytest.raises(模型调用失败) as 捕获:
            调用模型("提示")
        信息 = str(捕获.value)
        assert 假key not in 信息, "异常信息不得带 api_key"
        assert 假key not in _链上文(捕获.value), "异常的因果链上也不得带 api_key"


def test_非两百响应体里回显的_key_也被脱敏():
    """服务端把 key 回显在错误体里时，也要挡住，不能原样带出去。"""
    调用模型 = 构建调用模型(_配置(), 发送=_假发送(状态码=401, 原样文本=f'{{"error":"bad key {假key}"}}'))
    with pytest.raises(模型调用失败) as 捕获:
        调用模型("提示")
    assert 假key not in str(捕获.value)
    assert "401" in str(捕获.value)


# ---------- 端到端 ----------


def test_端到端_假发送产出的模型调用接进抽取草稿():
    """适配层接进主链路的证明：契约那条无主变身样本，产出无主线索且整篇不得出页。"""
    记录 = []
    发送 = _假发送(原样文本=_内容(json.dumps(_草稿输出([{"类别": "变身", "片段": 样本}]), ensure_ascii=False)), 记录=记录)
    调用模型 = 构建调用模型(_配置(), 发送=发送)

    草稿 = 抽取草稿(样本, 调用模型)

    提示 = json.loads(记录[0].体.decode("utf-8"))["messages"][0]["content"]
    assert 样本 in 提示, "原文全文确实经由适配层送到了模型"
    assert set(草稿) == {"人物卡", "场景卡", "风格ID", "故事节拍", "无主线索"}
    assert len(草稿["无主线索"]) == 1
    assert 草稿["人物卡"] == []
    assert 整篇可出页(草稿) is False


def test_适配层不访问网络(monkeypatch: pytest.MonkeyPatch):
    """注入假发送时，socket 和 urlopen 都不该被碰到。"""
    import socket
    import urllib.request

    def _禁止联网(*args, **kwargs):
        raise AssertionError("注入假发送时不应访问网络")

    monkeypatch.setattr(socket, "socket", _禁止联网)
    monkeypatch.setattr(socket, "create_connection", _禁止联网)
    monkeypatch.setattr(urllib.request, "urlopen", _禁止联网)

    调用模型 = 构建调用模型(_配置(), 发送=_假发送("离线返回"))
    assert 调用模型("提示") == "离线返回"
    草稿 = 抽取草稿(样本, 构建调用模型(_配置(), 发送=_假发送(原样文本=_内容(json.dumps(_草稿输出([{"类别": "变身", "片段": 样本}]), ensure_ascii=False)))))
    assert 整篇可出页(草稿) is False


def test_默认发送就是默认值且可被替换():
    import inspect

    签名 = inspect.signature(构建调用模型)
    assert 签名.parameters["发送"].default is 默认发送
    assert callable(默认发送)


# ---------- 默认发送（打桩 urlopen，仍不发真实 HTTP） ----------


class _假回话:
    """假的 urlopen 返回值：够用的上下文管理器。"""

    def __init__(self, 状态: int, 体: bytes):
        self.status = 状态
        self._体 = 体

    def read(self) -> bytes:
        return self._体

    def __enter__(self):
        return self

    def __exit__(self, *参数):
        return False


def test_默认发送把请求交给_urlopen_并读回响应(monkeypatch: pytest.MonkeyPatch):
    import urllib.request

    记录 = []

    def _假urlopen(网络请求, timeout=None):
        记录.append((网络请求, timeout))
        return _假回话(200, '{"choices": []}'.encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", _假urlopen)

    回应 = 默认发送(
        请求(
            url="https://例子.测试/v1/chat/completions",
            方法="POST",
            体=b'{"a":1}',
            头部={"Content-Type": "application/json"},
            超时秒=3.5,
        )
    )

    assert 回应 == 响应(状态码=200, 文本='{"choices": []}')
    网络请求, timeout = 记录[0]
    assert 网络请求.full_url == "https://例子.测试/v1/chat/completions"
    assert 网络请求.get_method() == "POST"
    assert 网络请求.data == b'{"a":1}'
    assert 网络请求.get_header("Content-type") == "application/json"
    assert timeout == 3.5


def test_默认发送把_HTTPError_当成一次正常返回(monkeypatch: pytest.MonkeyPatch):
    import io
    import urllib.error
    import urllib.request

    def _假urlopen(网络请求, timeout=None):
        raise urllib.error.HTTPError(
            网络请求.full_url, 429, "Too Many Requests", {}, io.BytesIO('{"error":"限流"}'.encode("utf-8"))
        )

    monkeypatch.setattr(urllib.request, "urlopen", _假urlopen)
    回应 = 默认发送(请求(url="https://例子.测试/v1/chat/completions", 方法="POST", 体=b"{}"))
    assert 回应 == 响应(状态码=429, 文本='{"error":"限流"}')


def test_默认发送的网络异常由上层归一成模型调用失败(monkeypatch: pytest.MonkeyPatch):
    import urllib.error
    import urllib.request

    def _假urlopen(网络请求, timeout=None):
        raise urllib.error.URLError(f"连不上（顺手带上 {假key}）")

    monkeypatch.setattr(urllib.request, "urlopen", _假urlopen)
    调用模型 = 构建调用模型(_配置())
    with pytest.raises(模型调用失败) as 捕获:
        调用模型("提示")
    assert 假key not in str(捕获.value)
    assert 假key not in _链上文(捕获.value), "不保留原异常，避免回溯里漏 key"


def test_非json响应体里带_key_时链上也不带_key():
    """响应体是坏 JSON 且里面回显了 key：JSONDecodeError 会留着原文，不能让它挂在链上。"""
    坏体 = f'{{"error": "{假key}"'  # 故意缺右括号
    调用模型 = 构建调用模型(_配置(), 发送=_假发送(原样文本=坏体))
    with pytest.raises(模型调用失败) as 捕获:
        调用模型("提示")
    assert 假key not in str(捕获.value)
    assert 假key not in _链上文(捕获.value)
