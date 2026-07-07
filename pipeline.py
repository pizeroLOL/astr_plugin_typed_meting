"""Meting 管线 — 点歌/搜歌的核心 deep 模块。

三个 public 方法组成 interface：
  fetch_songs(keyword) → list[SongItem]
  deliver_song(song)  → MessageChain, str
  fetch_and_deliver_first(keyword) → MessageChain, str

内部吸收 URL 构造、HTTP 请求、卡片签名、File fallback 的全部细节。
"""

from string import Template
from urllib.parse import quote, urljoin

from astrbot.api.message_components import File, Json
from astrbot.core.message.message_event_result import MessageChain
from httpx import URL, AsyncClient, HTTPError
from pydantic import ValidationError

from .cfg import Config
from .ty import CardSignResult, PluginLogger, SongItem, Songs
from .utils import SOURCE_FORMAT_MAPPER, SOURCE_JUMP_MAPPER

SONG_TEXT = Template("## $name\n\n- 艺人：$artist\n- 专辑图片：$pic\n- 歌曲链接：$url\n")


class MetingError(Exception):
    """管线中所有错误的基类。"""


class MetingAPIError(MetingError):
    """Metting API HTTP 请求失败。"""

    def __init__(self, url: str, status: int | None = None) -> None:
        self.url = url
        self.status = status
        super().__init__(f"API 错误 {url} (status={status})")


class MetingParseError(MetingError):
    """API 响应 JSON 解析失败。"""

    def __init__(self, url: str, raw: str) -> None:
        self.url = url
        self.raw = raw[:200]
        super().__init__(f"解析错误 {url}")


class NoSongFoundError(MetingError):
    """搜索返回空结果。"""

    def __init__(self, keyword: str) -> None:
        self.keyword = keyword
        super().__init__(f"暂无歌曲: {keyword}")


class MusicCardError(MetingError):
    """音乐卡片构造/签名失败——管线内部用于触发 fallback。"""


class MetingPipeline:
    """点歌/搜歌核心管线。

    依赖通过 constructor 注入，接口即测试面。
    """

    def __init__(self, client: AsyncClient, cfg: Config, log: PluginLogger) -> None:
        self._client = client
        self._cfg = cfg
        self._log = log

    # ---- public interface ----

    async def fetch_songs(self, keyword: str) -> list[SongItem]:
        """搜索歌曲，返回 SongItem 列表。

        Raises:
            MetingAPIError:   HTTP 请求失败
            MetingParseError: 响应 JSON 无法解析
        """
        url = self._build_url(keyword)
        self._log("debug", f"builded {url}")
        raw = await self._get_json(url)
        return self._parse_songs(raw, url)

    async def deliver_song(self, song: SongItem) -> tuple[MessageChain, str]:
        """投递一首歌，返回 (消息链, LLM 文本)。

        内部决定用音乐卡片还是文件，卡片构造失败时自动 fallback。
        """
        text = SONG_TEXT.safe_substitute(song.model_dump(mode="json"))
        msg = await self._build_delivery(song)
        return msg, text

    async def fetch_and_deliver_first(self, keyword: str) -> tuple[MessageChain, str]:
        """搜索并投递第一首——order_song 和 /点歌 的便捷入口。

        Raises:
            MetingAPIError / MetingParseError / NoSongFoundError
        """
        songs = await self.fetch_songs(keyword)
        if not songs:
            raise NoSongFoundError(keyword)
        return await self.deliver_song(songs[0])

    # ---- 内部实现 ----

    async def _get_json(self, url: str) -> str:
        try:
            rsp = await self._client.get(url, follow_redirects=True)
            rsp.raise_for_status()
            return rsp.text
        except HTTPError as e:
            raise MetingAPIError(url, getattr(e.response, "status_code", None)) from e

    @staticmethod
    def _parse_songs(raw: str, url: str) -> list[SongItem]:
        try:
            return Songs.model_validate_json(raw).root
        except ValidationError as e:
            raise MetingParseError(url, raw) from e

    async def _build_delivery(self, song: SongItem) -> MessageChain:
        source = self._cfg.meting.default_source
        if self._cfg.music_card.enable and source in SOURCE_JUMP_MAPPER:
            card_info = await self._resolve_card_info(song, source)
            if card_info is not None:
                try:
                    card_json = await self._sign_card(card_info)
                    return MessageChain([card_json])
                except MusicCardError:
                    pass  # fallback 到 File
        return MessageChain([File(name=f"{song.name}.mp3", url=str(song.url))])

    async def _resolve_card_info(self, song: SongItem, source: str) -> dict | None:
        """解析歌曲的卡片信息（原 build_card_info 逻辑）。"""
        id_ = URL(str(song.url)).params.get("id")
        if id_ is None:
            self._log("warn", f"url `{song.url}` 缺少id")
            return None
        raw_pic = str(song.pic)
        if source == "netease":
            raw_pic += ("&" if "?" in raw_pic else "?") + "picsize=320"
        pic_url = await self._resolve_redirect(raw_pic)
        if pic_url is None:
            self._log("warn", f"缺少 `pic_url` {song.pic} -> {raw_pic} -> None")
            return None
        return {
            "url": str(song.url).replace("http://", "https://"),
            "song": song.name,
            "singer": song.artist,
            "cover": pic_url,
            "jump": Template(SOURCE_JUMP_MAPPER[source]).substitute({"id": quote(id_)}),
            "format": SOURCE_FORMAT_MAPPER.get(source, source),
        }

    async def _sign_card(self, card_info: dict) -> Json:
        """调用签名 API，返回 JSON 消息组件（原 build_card_msg 逻辑）。

        Raises:
            MusicCardError: 签名请求失败或响应无法解析
        """
        try:
            rsp = await self._client.get(
                self._cfg.music_card.sign_url,
                params=card_info,
                follow_redirects=True,
            )
            rsp.raise_for_status()
            return CardSignResult.model_validate_json(rsp.text).into_json()
        except HTTPError as e:
            self._log("warn", f"签名错误 {e.request.url} -> {e}", exc_info=True)
            raise MusicCardError from e
        except ValidationError as e:
            self._log("warn", "签名序列化错误", exc_info=True)
            raise MusicCardError from e

    async def _resolve_redirect(self, url: str) -> str | None:
        try:
            rsp = await self._client.get(url, follow_redirects=False)
            if rsp.status_code in (301, 302, 303, 307, 308):
                return str(rsp.headers.get("Location", "")) or None
            return None
        except HTTPError:
            return None

    def _build_url(self, keyword: str) -> str:
        cfg = self._cfg.meting
        if cfg.kind == "php":
            has_q = "?" in cfg.url
            base = (
                cfg.url
                if has_q and cfg.url[-1] == "&"
                else cfg.url + "&"
                if has_q
                else cfg.url + "?"
            )
            params = {
                "server": cfg.default_source,
                "type": "search",
                "id": "0",
                "dwrc": "false",
                "keyword": keyword,
            }
            return base + "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items())
        if cfg.kind == "node":
            return (
                urljoin(cfg.url, "api")
                + "?"
                + "&".join(
                    f"{k}={quote(v, safe='')}"
                    for k, v in {
                        "server": cfg.default_source,
                        "type": "search",
                        "id": keyword,
                    }.items()
                )
            )
        return Template(cfg.url).substitute(
            {"server": quote(cfg.default_source), "keyword": quote(keyword)}
        )
