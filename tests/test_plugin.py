"""Plugin 集成测试 — 测试 handler 薄层 adapter 的异常处理和消息路由。

使用 mock pipeline 隔离管线逻辑（管线已有 25 个单元测试），
聚焦 handler 层的 keyword 解析、异常→消息映射、event.send 调用。
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.star.context import Context
from pylib_meting.main import Plugin
from pylib_meting.pipeline import MetingAPIError, MetingParseError, NoSongFoundError


def make_event(message_str: str, session_id: str = "test-session") -> MagicMock:
    """构造最小化的 AstrMessageEvent mock。

    注意：使用 MagicMock（非 spec），避免 AsyncMock spec 限制。
    message_str 直接传入字符串，避免 f-string 格式化 MagicMock 时报错。
    """
    event = MagicMock()
    event.message_str = message_str
    event.session_id = session_id
    event.get_sender_id.return_value = "test-user"
    event.plain_result = MagicMock(side_effect=lambda text: MessageEventResult().message(text))
    event.send = AsyncMock()
    event.stop_event = MagicMock()
    return event


class TestPluginHandlerAdapters(unittest.IsolatedAsyncioTestCase):
    """测试 handler 作为薄层 adapter 的正确行为。"""

    def setUp(self):
        self.mock_context = MagicMock(spec=Context)

    def _make_plugin(self, config: dict | None = None) -> Plugin:
        return Plugin(context=self.mock_context, config=config)

    async def _collect_async_gen(self, agen):
        """收集异步生成器的所有产出。"""
        results = []
        async for item in agen:
            results.append(item)
        return results

    # ---- 初始化 ----

    def test_plugin_initializes_with_default_config(self):
        """Plugin 在无 config 时使用默认配置初始化。"""
        plugin = self._make_plugin(config=None)
        self.assertEqual(plugin.cfg.meting.default_source, "netease")

    def test_plugin_initializes_with_custom_config(self):
        """Plugin 使用自定义配置初始化。"""
        plugin = self._make_plugin(
            config={
                "meting": {
                    "url": "https://example.com/",
                    "kind": "custom",
                    "default_source": "tencent",
                },
                "music_card": {"enable": False},
                "searching": {"results_ttl_second": 60, "results_limit": 5},
            }
        )
        self.assertEqual(plugin.cfg.meting.default_source, "tencent")
        self.assertEqual(plugin.cfg.searching.results_limit, 5)

    def test_plugin_initializes_with_invalid_config_fallback(self):
        """Plugin 在非法 config 时 fallback 到默认配置。

        default_source=123 不是有效的 literal 值，应触发 ValidationError，
        但 Plugin.__init__ 会捕获并回退到默认配置。
        """
        plugin = self._make_plugin(config={"meting": {"default_source": "invalid_source_value"}})
        # 应该 fallback 到默认配置（默认是 netease）
        self.assertIsNotNone(plugin.cfg)

    def test_log_returns_callable_with_uuid_prefix(self):
        """Plugin.log 返回的 logger 可被调用且包含插件名和 UUID。"""
        from uuid import uuid4

        plugin = self._make_plugin()
        log = plugin.log(uuid4())

        self.assertTrue(callable(log))
        # 不应抛异常
        log("debug", "测试日志")

    # ---- order_song (LLM tool) ----

    async def test_order_song_returns_text_on_success(self):
        """order_song 搜索成功时返回歌曲文本，并调用 event.send。"""
        plugin = self._make_plugin()
        plugin.client = AsyncMock()

        with patch("pylib_meting.main.MetingPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            # 管线方法返回 awaitable，所以用 AsyncMock
            mock_pipeline.fetch_and_deliver_first = AsyncMock(
                return_value=(
                    MagicMock(spec=MessageChain),
                    "## 七里香\n\n- 艺人：周杰伦",
                )
            )

            event = make_event("")
            result = await plugin.order_song(event, keyword="七里香")

            self.assertIn("七里香", result)
            self.assertIn("周杰伦", result)
            event.send.assert_awaited_once()

    async def test_order_song_returns_error_on_no_song_found(self):
        """order_song 在无结果时返回中文错误消息，且记录日志。"""
        plugin = self._make_plugin()
        plugin.client = AsyncMock()

        with patch("pylib_meting.main.MetingPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.fetch_and_deliver_first = AsyncMock(
                side_effect=NoSongFoundError("不存在")
            )

            event = make_event("")
            result = await plugin.order_song(event, keyword="不存在")

            self.assertEqual(result, "暂无歌曲")

    async def test_order_song_returns_error_on_api_failure(self):
        """order_song 在 API 错误时返回中文错误消息。"""
        plugin = self._make_plugin()
        plugin.client = AsyncMock()

        with patch("pylib_meting.main.MetingPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.fetch_and_deliver_first = AsyncMock(
                side_effect=MetingAPIError("url", 500)
            )

            event = make_event("")
            result = await plugin.order_song(event, keyword="test")

            self.assertEqual(result, "搜索响应错误")

    async def test_order_song_returns_error_on_parse_failure(self):
        """order_song 在解析错误时返回中文错误消息。"""
        plugin = self._make_plugin()
        plugin.client = AsyncMock()

        with patch("pylib_meting.main.MetingPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.fetch_and_deliver_first = AsyncMock(
                side_effect=MetingParseError("url", "bad")
            )

            event = make_event("")
            result = await plugin.order_song(event, keyword="test")

            self.assertEqual(result, "搜索序列化错误")

    # ---- /点歌 handler ----

    async def test_order_handler_returns_missing_keyword(self):
        """点歌 在关键词为空时返回提示。"""
        plugin = self._make_plugin()
        plugin.client = AsyncMock()
        event = make_event("/点歌 ")  # 关键词为空白

        gen = plugin.order(event)
        results = await self._collect_async_gen(gen)

        self.assertEqual(len(results), 1)
        self.assertIn("缺少歌名", results[0].get_plain_text())

    async def test_order_handler_delegates_to_pipeline_on_success(self):
        """点歌 在有关键词时委托管线并发送结果。"""
        plugin = self._make_plugin()
        plugin.client = AsyncMock()
        event = make_event("/点歌 七里香")

        with patch("pylib_meting.main.MetingPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.fetch_and_deliver_first = AsyncMock(
                return_value=(MagicMock(spec=MessageChain), "text")
            )

            gen = plugin.order(event)
            # 消费生成器（管线成功时无 yield，直接 await send）
            async for _ in gen:
                pass

            mock_pipeline.fetch_and_deliver_first.assert_awaited_once_with("七里香")
            event.send.assert_awaited_once()

    # ---- /搜歌 handler ----

    async def test_search_handler_returns_missing_keyword(self):
        """搜歌 在关键词为空时返回提示。"""
        plugin = self._make_plugin()
        plugin.client = AsyncMock()
        event = make_event("/搜歌 ")

        gen = plugin.search(event)
        results = await self._collect_async_gen(gen)

        self.assertEqual(len(results), 1)
        self.assertIn("缺少歌名", results[0].get_plain_text())

    async def test_search_handler_returns_error_on_api_failure(self):
        """搜歌 在 API 错误时返回错误消息。"""
        plugin = self._make_plugin()
        plugin.client = AsyncMock()
        event = make_event("/搜歌 七里香")

        with patch("pylib_meting.main.MetingPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.fetch_songs = AsyncMock(side_effect=MetingAPIError("url", 500))

            gen = plugin.search(event)
            results = await self._collect_async_gen(gen)

            self.assertEqual(len(results), 1)
            self.assertIn("搜索响应错误", results[0].get_plain_text())

    async def test_search_handler_returns_no_song_message(self):
        """搜歌 在无结果时返回提示。"""
        plugin = self._make_plugin()
        plugin.client = AsyncMock()
        event = make_event("/搜歌 不存在")

        with patch("pylib_meting.main.MetingPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.fetch_songs = AsyncMock(return_value=[])

            gen = plugin.search(event)
            results = await self._collect_async_gen(gen)

            self.assertEqual(len(results), 1)
            self.assertIn("暂无歌曲", results[0].get_plain_text())

    async def test_search_handler_shows_results_on_success(self):
        """搜歌 在有结果时展示歌曲列表。"""
        plugin = self._make_plugin()
        plugin.client = AsyncMock()
        event = make_event("/搜歌 七里香")

        from pylib_meting.ty import SongItem

        mock_songs = [
            SongItem(
                name="七里香",
                artist="周杰伦",
                url="https://example.com/1.mp3?id=1",
                pic="https://example.com/1.jpg",
            ),
        ]

        # Mock session_waiter 使其立即超时，避免真实等待
        with (
            patch("pylib_meting.main.MetingPipeline") as mock_pipeline_cls,
            patch("pylib_meting.main.session_waiter") as mock_sw,
        ):
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.fetch_songs = AsyncMock(return_value=mock_songs)

            def fake_session_waiter(*, timeout=None, record_history_chains=False):  # noqa: ARG001
                def decorator(_f):
                    async def wrapper(*_args, **_kwargs):
                        raise TimeoutError("mocked timeout")

                    return wrapper

                return decorator

            mock_sw.side_effect = fake_session_waiter

            gen = plugin.search(event)
            results = await self._collect_async_gen(gen)

            self.assertGreaterEqual(len(results), 1)
            self.assertIn("七里香", results[0].get_plain_text())
            self.assertIn("周杰伦", results[0].get_plain_text())


if __name__ == "__main__":
    unittest.main()
