# Typed Meting

为 AstrBot 提供点歌/搜歌能力的插件，通过 Meting API 搜索音乐并返回音频文件或音乐卡片。

## Language

**Meting API**：
第三方音乐搜索 API，有 node（metowolf/meting）和 php（nanorocky/meting-api）两种实现，返回 JSON 格式的歌曲列表。
_Avoid_：搜索接口、音乐 API

**SongItem**：
一首歌的数据模型，包含歌名（name）、艺人（artist）、专辑（album，可选）、歌曲 URL（url）、封面图片 URL（pic）。
_Avoid_：歌曲、曲目、track

**音乐卡片 / Music Card**：
通过签名 API 生成的 QQ 音乐 JSON 卡片消息，在聊天中以结构化卡片展示歌曲信息（封面、歌名、艺人、跳转链接），而非纯文本或文件。
_Avoid_：Ark 消息、分享卡片

**音源 / Source**：
歌曲的搜索来源平台，支持 `netease`（网易云音乐）、`tencent`（QQ 音乐）、`kugou`（酷狗音乐）、`kuwo`（酷我音乐），由 `MetingConfig.default_source` 控制默认值。
_Avoid_：平台、provider、server

**Session Waiter**：
搜歌后的交互等待机制——用户执行 `/搜歌` 后进入等待状态，可在 TTL 内输入 `点歌 <序号>` 选择歌曲，输入 `退出` 或超时后结束会话。由 `SessionController` 和 `@session_waiter` 装饰器实现。
_Avoid_：会话、交互循环、等待器
