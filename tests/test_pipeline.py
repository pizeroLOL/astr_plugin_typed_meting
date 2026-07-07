"""MetingPipeline 单元测试。

通过公共接口测试管线核心逻辑，用 AsyncMock 替换 AsyncClient。
"""

import unittest
from unittest.mock import AsyncMock

from astrbot.api.message_components import File, Json
from httpx import HTTPError, Request, Response
from pylib_meting.cfg import Config, MetingConfig, MusicCardConfig, SearchConfig
from pylib_meting.pipeline import (
    MetingAPIError,
    MetingError,
    MetingParseError,
    MetingPipeline,
    MusicCardError,
    NoSongFoundError,
)
from pylib_meting.ty import SongItem

# ---- 测试数据 ----

# node 实现的典型响应（title/author 字段）
NODE_RESPONSE = """[{"title":"七里香","author":"周杰伦","url":"https://example.com/music/1.mp3","pic":"https://example.com/pic/1.jpg","lrc":"","url_320":"","url_flac":""}]"""

# php 实现的典型响应（name/artist 字段）
PHP_RESPONSE = """[{"name":"晴天","artist":"周杰伦","url":"https://example.com/music/2.mp3","pic":"https://example.com/pic/2.jpg"}]"""

# 多结果响应
MULTI_RESPONSE = """[{"title":"稻香","author":"周杰伦","url":"https://example.com/music/3.mp3","pic":"https://example.com/pic/3.jpg"},{"title":"简单爱","author":"周杰伦","url":"https://example.com/music/4.mp3","pic":"https://example.com/pic/4.jpg"}]"""

# 带 id 参数的歌曲 URL
SONG_WITH_ID = SongItem(
    name="七里香",
    artist="周杰伦",
    url="https://example.com/music/1.mp3?id=123456",
    pic="https://example.com/pic/1.jpg",
)

# 不带 id 的歌曲 URL
SONG_WITHOUT_ID = SongItem(
    name="晴天",
    artist="周杰伦",
    url="https://example.com/music/2.mp3",
    pic="https://example.com/pic/2.jpg",
)


def mock_response(status: int = 200, text: str = "", headers: dict | None = None) -> Response:
    """构造一个 mock httpx Response。"""
    req = Request("GET", "https://example.com/api")
    return Response(status, text=text, headers=headers or {}, request=req)


def mock_http_error(status: int = 500) -> HTTPError:
    """构造一个 mock HTTPError——被管线捕获后重新抛出为 MetingAPIError。"""
    req = Request("GET", "https://example.com/api")
    resp = Response(status, request=req)
    error = HTTPError("Server error")
    error.request = req
    error.response = resp
    return error


def make_config(
    *,
    kind: str = "node",
    source: str = "netease",
    card_enabled: bool = False,
    url: str = "https://example.com/meting/",
) -> Config:
    """快速构造测试 Config。

    注意：MetingConfig.model_validator 会根据 url 自动覆盖 kind。
    若 url 不在 SOURCE_URL_MAPPER 中，kind 会被设为 "custom"。
    """
    return Config(
        meting=MetingConfig(url=url, kind=kind, default_source=source),
        music_card=MusicCardConfig(enable=card_enabled),
        searching=SearchConfig(),
    )


class SpyLogger:
    """测试替身：记录所有日志调用。"""

    def __init__(self):
        self.calls: list[tuple[str, str, bool]] = []

    def __call__(self, mode: str, msg: str, exc_info: bool = False) -> None:
        self.calls.append((mode, msg, exc_info))


class TestMetingPipeline(unittest.IsolatedAsyncioTestCase):
    """管线公共接口测试。"""

    def setUp(self):
        self.client = AsyncMock()
        self.logger = SpyLogger()

    # ---- fetch_songs ----

    async def test_fetch_songs_parses_node_response(self):
        """fetch_songs 正确解析 node 实现的 title/author 字段。"""
        self.client.get.return_value = mock_response(text=NODE_RESPONSE)
        pipeline = MetingPipeline(self.client, make_config(), log=self.logger)

        songs = await pipeline.fetch_songs("七里香")

        self.assertEqual(len(songs), 1)
        self.assertEqual(songs[0].name, "七里香")
        self.assertEqual(songs[0].artist, "周杰伦")
        self.assertEqual(str(songs[0].url), "https://example.com/music/1.mp3")

    async def test_fetch_songs_parses_php_response(self):
        """fetch_songs 正确解析 php 实现的 name/artist 字段。"""
        self.client.get.return_value = mock_response(text=PHP_RESPONSE)
        pipeline = MetingPipeline(self.client, make_config(kind="php"), log=self.logger)

        songs = await pipeline.fetch_songs("晴天")

        self.assertEqual(len(songs), 1)
        self.assertEqual(songs[0].name, "晴天")

    async def test_fetch_songs_returns_multiple_results(self):
        """fetch_songs 返回多条结果。"""
        self.client.get.return_value = mock_response(text=MULTI_RESPONSE)
        pipeline = MetingPipeline(self.client, make_config(), log=self.logger)

        songs = await pipeline.fetch_songs("周杰伦")

        self.assertEqual(len(songs), 2)
        self.assertEqual(songs[0].name, "稻香")
        self.assertEqual(songs[1].name, "简单爱")

    async def test_fetch_songs_raises_on_http_error(self):
        """fetch_songs 在 HTTP 错误时抛出 MetingAPIError。"""
        self.client.get.side_effect = mock_http_error(500)
        pipeline = MetingPipeline(self.client, make_config(), log=self.logger)

        with self.assertRaises(MetingAPIError) as ctx:
            await pipeline.fetch_songs("七里香")
        self.assertEqual(ctx.exception.status, 500)

    async def test_fetch_songs_raises_on_invalid_json(self):
        """fetch_songs 在 JSON 解析失败时抛出 MetingParseError。"""
        self.client.get.return_value = mock_response(text="not json")
        pipeline = MetingPipeline(self.client, make_config(), log=self.logger)

        with self.assertRaises(MetingParseError):
            await pipeline.fetch_songs("七里香")

    async def test_fetch_songs_raises_on_missing_required_fields(self):
        """fetch_songs 在缺少必填字段时抛出 MetingParseError。"""
        self.client.get.return_value = mock_response(text='[{"title":"test"}]')
        pipeline = MetingPipeline(self.client, make_config(), log=self.logger)

        with self.assertRaises(MetingParseError):
            await pipeline.fetch_songs("test")

    # ---- fetch_and_deliver_first ----

    async def test_fetch_and_deliver_first_returns_song(self):
        """fetch_and_deliver_first 搜索成功并返回消息链和文本。"""
        self.client.get.return_value = mock_response(text=NODE_RESPONSE)
        pipeline = MetingPipeline(self.client, make_config(), log=self.logger)

        msg_chain, text = await pipeline.fetch_and_deliver_first("七里香")

        self.assertIn("七里香", text)
        self.assertIn("周杰伦", text)
        self.assertEqual(len(msg_chain.chain), 1)
        self.assertIsInstance(msg_chain.chain[0], File)

    async def test_fetch_and_deliver_first_raises_on_no_result(self):
        """fetch_and_deliver_first 在空结果时抛出 NoSongFoundError。"""
        self.client.get.return_value = mock_response(text="[]")
        pipeline = MetingPipeline(self.client, make_config(), log=self.logger)

        with self.assertRaises(NoSongFoundError) as ctx:
            await pipeline.fetch_and_deliver_first("不存在")
        self.assertEqual(ctx.exception.keyword, "不存在")

    # ---- deliver_song ----

    async def test_deliver_song_returns_file_when_card_disabled(self):
        """deliver_song 在卡片禁用时返回 File 消息。"""
        pipeline = MetingPipeline(self.client, make_config(card_enabled=False), log=self.logger)

        msg_chain, text = await pipeline.deliver_song(SONG_WITH_ID)

        self.assertEqual(len(msg_chain.chain), 1)
        self.assertIsInstance(msg_chain.chain[0], File)
        self.assertIn("七里香", text)

    async def test_deliver_song_returns_file_when_no_id(self):
        """deliver_song 在歌曲 URL 缺少 id 时 fallback 到 File。

        即使卡片启用且音源支持，无 id 时也应 fallback。
        """
        pipeline = MetingPipeline(
            self.client,
            make_config(card_enabled=True, source="netease"),
            log=self.logger,
        )

        msg_chain, _ = await pipeline.deliver_song(SONG_WITHOUT_ID)

        self.assertIsInstance(msg_chain.chain[0], File)
        self.assertTrue(any("缺少id" in msg for _, msg, _ in self.logger.calls))

    async def test_deliver_song_builds_card_when_enabled(self):
        """deliver_song 在卡片启用且音源支持时构造 JSON 卡片。"""
        self.client.get.side_effect = [
            mock_response(status=302, headers={"Location": "https://cdn.example.com/cover.jpg"}),
            mock_response(text='{"code":1,"data":{"config":{"token":"test"}}}'),
        ]
        pipeline = MetingPipeline(
            self.client,
            make_config(card_enabled=True, source="netease"),
            log=self.logger,
        )

        msg_chain, text = await pipeline.deliver_song(SONG_WITH_ID)

        self.assertIsInstance(msg_chain.chain[0], Json)
        self.assertIn("七里香", text)

    async def test_deliver_song_falls_back_to_file_when_pic_redirect_fails(self):
        """deliver_song 在封面重定向失败时 fallback 到 File。"""
        self.client.get.return_value = mock_response(status=200, text="not a redirect")
        pipeline = MetingPipeline(
            self.client,
            make_config(card_enabled=True, source="netease"),
            log=self.logger,
        )

        msg_chain, _ = await pipeline.deliver_song(SONG_WITH_ID)

        self.assertIsInstance(msg_chain.chain[0], File)

    async def test_deliver_song_falls_back_to_file_when_sign_fails(self):
        """deliver_song 在签名 API 失败时 fallback 到 File。"""
        self.client.get.side_effect = [
            mock_response(status=302, headers={"Location": "https://cdn.example.com/cover.jpg"}),
            mock_http_error(500),
        ]
        pipeline = MetingPipeline(
            self.client,
            make_config(card_enabled=True, source="netease"),
            log=self.logger,
        )

        msg_chain, _ = await pipeline.deliver_song(SONG_WITH_ID)

        self.assertIsInstance(msg_chain.chain[0], File)


class TestMetingPipelineInternals(unittest.TestCase):
    """管线内部静态方法测试。"""

    # ---- _parse_songs ----

    def test_parse_songs_remaps_node_fields(self):
        """_parse_songs 正确映射 node 的 title→name、author→artist。"""
        songs = MetingPipeline._parse_songs(NODE_RESPONSE, url="test")

        self.assertEqual(len(songs), 1)
        self.assertEqual(songs[0].name, "七里香")
        self.assertEqual(songs[0].artist, "周杰伦")

    def test_parse_songs_handles_php_fields_directly(self):
        """_parse_songs 正确处理 php 的 name/artist 字段。"""
        songs = MetingPipeline._parse_songs(PHP_RESPONSE, url="test")

        self.assertEqual(songs[0].name, "晴天")
        self.assertEqual(songs[0].artist, "周杰伦")

    def test_parse_songs_raises_on_invalid_json(self):
        """_parse_songs 在非法 JSON 时抛出 MetingParseError。"""
        with self.assertRaises(MetingParseError):
            MetingPipeline._parse_songs("not json", url="test")

    def test_parse_songs_raises_on_empty_response(self):
        """_parse_songs 在空响应时抛出 MetingParseError。"""
        with self.assertRaises(MetingParseError):
            MetingPipeline._parse_songs("", url="test")

    # ---- _build_url ----

    def test_build_url_node_format(self):
        """_build_url 构造 node 实现的标准 URL 格式。

        注意: MetingConfig.model_validator 会根据 url 自动判定 kind。
        使用已知 node 映射的 URL 以触发正确的 kind。
        """
        cfg = make_config(
            kind="node",
            source="netease",
            url="https://musicapi.chuyel.top/meting/",
        )
        pipeline = MetingPipeline(AsyncMock(), cfg, log=SpyLogger())

        url = pipeline._build_url("七里香")

        self.assertIn("api?", url)
        self.assertIn("server=netease", url)
        self.assertIn("type=search", url)
        self.assertIn("id=%E4%B8%83%E9%87%8C%E9%A6%99", url)

    def test_build_url_php_format(self):
        """_build_url 构造 php 实现的标准 URL 格式。

        使用已知 php 映射的 URL 以触发正确的 kind。
        """
        cfg = make_config(
            kind="php",
            source="tencent",
            url="https://metingapi.nanorocky.top/",
        )
        pipeline = MetingPipeline(AsyncMock(), cfg, log=SpyLogger())

        url = pipeline._build_url("晴天")

        self.assertIn("server=tencent", url)
        self.assertIn("type=search", url)
        self.assertIn("dwrc=false", url)

    def test_build_url_custom_template(self):
        """_build_url 使用自定义模板拼接 URL。"""
        cfg = make_config(
            kind="custom",
            source="netease",
            url="https://api.example.com/$server/$keyword",
        )
        pipeline = MetingPipeline(AsyncMock(), cfg, log=SpyLogger())

        url = pipeline._build_url("七里香")

        self.assertIn("netease", url)
        self.assertIn("%E4%B8%83%E9%87%8C%E9%A6%99", url)


class TestMetingErrors(unittest.TestCase):
    """错误类型测试。"""

    def test_meting_error_hierarchy(self):
        """验证错误继承链。"""
        self.assertTrue(issubclass(MetingAPIError, MetingError))
        self.assertTrue(issubclass(MetingParseError, MetingError))
        self.assertTrue(issubclass(NoSongFoundError, MetingError))
        self.assertTrue(issubclass(MusicCardError, MetingError))

    def test_exceptions_can_be_caught_by_base(self):
        """所有子类可被 MetingError 捕获。"""
        try:
            raise MetingAPIError("url", 500)
        except MetingError:
            pass

        try:
            raise NoSongFoundError("keyword")
        except MetingError:
            pass

    def test_api_error_stores_details(self):
        """MetingAPIError 保存 URL 和状态码。"""
        err = MetingAPIError("https://example.com/api", 503)
        self.assertEqual(err.url, "https://example.com/api")
        self.assertEqual(err.status, 503)

    def test_parse_error_stores_url(self):
        """MetingParseError 保存 URL。"""
        err = MetingParseError("https://example.com/api", "bad json")
        self.assertEqual(err.url, "https://example.com/api")

    def test_no_song_error_stores_keyword(self):
        """NoSongFoundError 保存搜索关键词。"""
        err = NoSongFoundError("不存在")
        self.assertEqual(err.keyword, "不存在")


if __name__ == "__main__":
    unittest.main()
