"""ITEM-2 · 供应商适配层追加：拉取模型（文本 + 图像）与图像生成接缝。

全部用例注入假的 `发送`，一次真实 HTTP 都不发生。
"""

import base64
import json

import pytest

from storyweave.model_client import (
    供应商配置,
    从环境变量读图像配置,
    从环境变量读配置,
    响应,
    图像生成端点,
    模型列表端点,
    构建生成图,
    构建调用模型,
    模型调用失败,
    拉取模型,
    请求,
    默认发送,
)

假key = "sk-假key-不该出现在任何信息里"
假图片 = b"\x89PNG\r\n\x1a\nfake-image-bytes"
图像key = "sk-图像key-也不该出现"


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


def _假发送(状态码=200, 原样文本=None, 记录=None, 抛出=None):
    def 发送(请求):
        if 记录 is not None:
            记录.append(请求)
        if 抛出 is not None:
            raise 抛出
        return 响应(状态码=状态码, 文本=原样文本 if 原样文本 is not None else "{}")

    return 发送


def _链上文(错) -> str:
    片段 = []
    当前 = 错
    while 当前 is not None:
        片段.append(f"{type(当前).__name__}: {当前}")
        for 属性 in ("doc", "url", "filename"):
            值 = getattr(当前, 属性, None)
            if isinstance(值, str):
                片段.append(值)
        当前 = 当前.__cause__ if 当前.__cause__ is not None else 当前.__context__
    return " | ".join(片段)


# ---------- 端点 ----------


def test_模型列表端点拼在_base_url_之后():
    assert 模型列表端点(_配置()) == "https://例子.测试/v1/models"
    assert 模型列表端点(_配置(base_url="https://例子.测试/v1/")) == "https://例子.测试/v1/models"


def test_图像生成端点拼在_base_url_之后():
    assert 图像生成端点(_配置()) == "https://例子.测试/v1/images/generations"
    assert 图像生成端点(_配置(base_url="https://例子.测试/v1/")) == "https://例子.测试/v1/images/generations"


# ---------- 拉取模型 ----------


def test_拉取模型请求形状是_get_带授权头():
    记录 = []
    拉取模型(_配置(), 发送=_假发送(原样文本='{"data": []}', 记录=记录))

    assert len(记录) == 1
    请求 = 记录[0]
    assert 请求.url == "https://例子.测试/v1/models"
    assert 请求.方法 == "GET"
    assert 请求.体 == b""
    assert 请求.超时秒 == 12.5
    头部 = {名.lower(): 值 for 名, 值 in 请求.头部.items()}
    assert 头部["authorization"] == f"Bearer {假key}"


def test_拉取模型返回去重排序后的模型名():
    体 = json.dumps(
        {"data": [{"id": "模型乙"}, {"id": "模型甲"}, {"id": "模型乙"}, {"id": "模型丙"}]},
        ensure_ascii=False,
    )
    assert 拉取模型(_配置(), 发送=_假发送(原样文本=体)) == sorted(["模型乙", "模型甲", "模型丙"])


def test_拉取模型没有模型时返回空列表():
    assert 拉取模型(_配置(), 发送=_假发送(原样文本='{"data": []}')) == []


def test_没配_key_时拉取模型不发授权头():
    记录 = []
    拉取模型(_配置(api_key=""), 发送=_假发送(原样文本='{"data": []}', 记录=记录))
    头部 = {名.lower(): 值 for 名, 值 in 记录[0].头部.items()}
    assert "authorization" not in 头部


@pytest.mark.parametrize(
    ("状态码", "原样文本"),
    [
        (401, '{"error": "unauthorized"}'),
        (500, "服务器炸了"),
        (200, "这不是 JSON"),
        (200, '{"data": "不是列表"}'),
        (200, '{"没有": "data"}'),
        (200, '{"data": [{"没有id": 1}]}'),
        (200, '{"data": [{"id": 42}]}'),
    ],
)
def test_拉取模型的各种坏响应都归一成模型调用失败(状态码, 原样文本):
    with pytest.raises(模型调用失败):
        拉取模型(_配置(), 发送=_假发送(状态码=状态码, 原样文本=原样文本))


def test_拉取模型的错误信息与因果链都不带_key():
    for 发送 in (
        _假发送(状态码=401, 原样文本=f'{{"error":"bad key {假key}"}}'),
        _假发送(原样文本=f'{{"data": "{假key}"'),
        _假发送(抛出=OSError(f"连不上（对方回了 {假key}）")),
    ):
        with pytest.raises(模型调用失败) as 捕获:
            拉取模型(_配置(), 发送=发送)
        assert 假key not in str(捕获.value)
        assert 假key not in _链上文(捕获.value)


def test_拉取模型对发送返回非响应对象时拒绝():
    with pytest.raises(模型调用失败):
        拉取模型(_配置(), 发送=lambda 请求: {"状态码": 200})


# ---------- 图像供应商配置 ----------


def test_图像配置读_图像_前缀的环境变量(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STORYWEAVE_图像_供应商", "图像供应商")
    monkeypatch.setenv("STORYWEAVE_图像_模型", "图像模型")
    monkeypatch.setenv("STORYWEAVE_图像_BASE_URL", "https://图像.测试/v1")
    monkeypatch.setenv("STORYWEAVE_图像_API_KEY", 图像key)
    monkeypatch.setenv("STORYWEAVE_图像_超时秒", "30")

    配置 = 从环境变量读图像配置()
    assert 配置.供应商 == "图像供应商"
    assert 配置.模型 == "图像模型"
    assert 配置.base_url == "https://图像.测试/v1"
    assert 配置.api_key == 图像key
    assert 配置.超时秒 == 30.0


def test_图像配置缺省时给出合理值(monkeypatch: pytest.MonkeyPatch):
    for 名 in ("供应商", "模型", "BASE_URL", "API_KEY", "超时秒"):
        monkeypatch.delenv(f"STORYWEAVE_图像_{名}", raising=False)
    配置 = 从环境变量读图像配置()
    assert 配置.供应商
    assert 配置.模型
    assert 配置.base_url.startswith("https://")
    assert 配置.api_key == ""
    assert 配置.超时秒 > 0


def test_文本配置与图像配置互不串(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STORYWEAVE_模型", "文本模型")
    monkeypatch.setenv("STORYWEAVE_图像_模型", "图像模型")
    monkeypatch.setenv("STORYWEAVE_API_KEY", 假key)
    monkeypatch.setenv("STORYWEAVE_图像_API_KEY", 图像key)

    assert 从环境变量读配置().模型 == "文本模型"
    assert 从环境变量读配置().api_key == 假key
    assert 从环境变量读图像配置().模型 == "图像模型"
    assert 从环境变量读图像配置().api_key == 图像key


def test_图像配置超时非法时拒绝(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STORYWEAVE_图像_超时秒", "0")
    with pytest.raises(模型调用失败):
        从环境变量读图像配置()
    monkeypatch.setenv("STORYWEAVE_图像_超时秒", "不是数字")
    with pytest.raises(模型调用失败):
        从环境变量读图像配置()


# ---------- 图像生成 ----------


def test_构建生成图产出提示到图片的函数():
    体 = json.dumps({"data": [{"b64_json": base64.b64encode(假图片).decode("ascii")}]})
    生成 = 构建生成图(_配置(), 发送=_假发送(原样文本=体))
    assert callable(生成)
    assert 生成("画一张正脸") == 假图片


def test_图像生成请求形状是_post_带模型与提示():
    记录 = []
    体 = json.dumps({"data": [{"b64_json": base64.b64encode(假图片).decode("ascii")}]})
    生成 = 构建生成图(_配置(), 发送=_假发送(原样文本=体, 记录=记录))
    生成("画一张正脸参考图")

    请求 = 记录[0]
    assert 请求.url == "https://例子.测试/v1/images/generations"
    assert 请求.方法 == "POST"
    头部 = {名.lower(): 值 for 名, 值 in 请求.头部.items()}
    assert 头部["content-type"] == "application/json"
    assert 头部["authorization"] == f"Bearer {假key}"
    体 = json.loads(请求.体.decode("utf-8"))
    assert 体["model"] == "测试模型"
    assert 体["prompt"] == "画一张正脸参考图"


def test_图像生成接进档案的生成参考图(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """适配层产出的生成函数直接喂给档案的 生成参考图。"""
    from storyweave.archive import 建档案, 生成参考图
    from storyweave import 抽取草稿

    原文 = "阿明推开院门。"
    草稿输出 = {
        "人物": [
            {
                "名称": "阿明",
                "身份": {"脸型": "鹅卵脸"},
                "原文起": 0,
                "原文止": 3,
                "服装": [],
                "未支持": [],
            }
        ],
        "场景": [],
        "风格ID": "水墨",
        "故事节拍": [],
        "无主线索": [],
    }
    草稿 = 抽取草稿(原文, lambda 提示: json.dumps(草稿输出, ensure_ascii=False))
    档案 = 建档案(草稿)

    记录 = []
    体 = json.dumps({"data": [{"b64_json": base64.b64encode(假图片).decode("ascii")}]})
    生成 = 构建生成图(_配置(), 发送=_假发送(原样文本=体, 记录=记录))
    生成参考图(档案, "身份:阿明", 生成)

    图 = 档案["人物卡"][0]["身份参考图"]
    assert 图["来源"] == "生成"
    assert 图["图片"] == 假图片
    assert 图["确认状态"] == "未确认"
    assert "阿明" in json.loads(记录[0].体.decode("utf-8"))["prompt"]


@pytest.mark.parametrize(
    ("状态码", "原样文本"),
    [
        (400, '{"error": "bad prompt"}'),
        (200, "这不是 JSON"),
        (200, '{"data": []}'),
        (200, '{"没有": "data"}'),
        (200, '{"data": [{"没有图片字段": 1}]}'),
        (200, '{"data": [{"b64_json": "这不是合法base64!!"}]}'),
    ],
)
def test_图像生成的各种坏响应都归一成模型调用失败(状态码, 原样文本):
    生成 = 构建生成图(_配置(), 发送=_假发送(状态码=状态码, 原样文本=原样文本))
    with pytest.raises(模型调用失败):
        生成("画一张正脸")


def test_图像生成的错误信息与因果链都不带_key():
    for 发送 in (
        _假发送(状态码=400, 原样文本=f'{{"error":"bad key {假key}"}}'),
        _假发送(原样文本=f'{{"data": "{假key}"'),
        _假发送(抛出=TimeoutError(f"超时（对方回了 {假key}）")),
    ):
        生成 = 构建生成图(_配置(), 发送=发送)
        with pytest.raises(模型调用失败) as 捕获:
            生成("画一张正脸")
        assert 假key not in str(捕获.value)
        assert 假key not in _链上文(捕获.value)


def test_构建生成图校验入参():
    with pytest.raises(TypeError):
        构建生成图({"不是": "配置"})
    with pytest.raises(TypeError):
        构建生成图(_配置(), 发送="这不是函数")


def test_构建生成图的发送默认是默认发送():
    import inspect

    assert inspect.signature(构建生成图).parameters["发送"].default is 默认发送


def test_拉取模型与图像生成都不访问网络(monkeypatch: pytest.MonkeyPatch):
    import socket
    import urllib.request

    def _禁止联网(*args, **kwargs):
        raise AssertionError("注入假发送时不应访问网络")

    monkeypatch.setattr(socket, "socket", _禁止联网)
    monkeypatch.setattr(socket, "create_connection", _禁止联网)
    monkeypatch.setattr(urllib.request, "urlopen", _禁止联网)

    体 = json.dumps({"data": [{"b64_json": base64.b64encode(假图片).decode("ascii")}]})
    assert 拉取模型(_配置(), 发送=_假发送(原样文本='{"data": [{"id": "某模型"}]}')) == ["某模型"]
    assert 构建生成图(_配置(), 发送=_假发送(原样文本=体))("画图") == 假图片
    assert 构建调用模型(_配置(), 发送=_假发送(原样文本='{"choices": [{"message": {"content": "ok"}}]}'))("提示") == "ok"
