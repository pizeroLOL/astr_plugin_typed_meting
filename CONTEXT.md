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

**签名 / Sign**：
调用外部签名 API 获取已签名的音乐卡片 JSON（`CardSignResult`），然后以 `Json` 消息组件投递。签名失败时触发降级，不会直接报错。
_Avoid_：鉴权、加密

**降级 / Fallback**：
有意的设计决策：音乐卡片构造或签名失败时，管线自动退回以纯音频文件（`File`）投递歌曲，而非向用户暴露错误。仅在卡片启用且音源支持卡片时才尝试卡片路径。
_Avoid_：回退、兜底、容错

**API 类型 / API Kind**：
Meting API 的三种实现变体——`node`（metowolf/meting）、`php`（nanorocky/meting-api）、`custom`（用户自定义 URL 模板）。决定 `_build_url()` 如何拼接搜索请求 URL。
_Avoid_：模式、后端

**音源 / Source**：
歌曲的搜索来源平台，支持 `netease`（网易云音乐）、`tencent`（QQ 音乐）、`kugou`（酷狗音乐）、`kuwo`（酷我音乐），由 `MetingConfig.default_source` 控制默认值。
注意：Meting API 自身的 URL 参数名为 `server`，这是外部 API 的命名约定，非本项目的术语。
_Avoid_：平台、provider、server（API 参数名除外）

**点歌 / Order**：
一步式命令（`/点歌` 指令或 LLM tool `order_song`）——搜索关键词并立即投递第一条结果。与「搜歌」形成对比：点歌无需用户二次选择。
_Avoid_：直接点播、快速点歌

**搜歌 / Search**：
交互式命令（`/搜歌` 指令）——搜索并展示结果列表，用户通过 Session Waiter 选择序号后再投递。与「点歌」形成对比：搜歌多一轮交互。
_Avoid_：查找、检索

**Session Waiter**：
搜歌后的交互等待机制——用户执行 `/搜歌` 后进入等待状态，可在 TTL 内输入 `点歌 <序号>` 选择歌曲，输入 `退出` 或超时后结束会话。由 `SessionController` 和 `@session_waiter` 装饰器实现。
_Avoid_：会话、交互循环、等待器

**管线 / Pipeline**：
核心编排器（`MetingPipeline`），负责协调搜索、投递、卡片签名全流程。对外暴露三个 public 方法：`fetch_songs`（搜索）、`deliver_song`（投递）、`fetch_and_deliver_first`（搜索并投递第一条）。所有依赖通过 constructor 注入，接口即测试面。
_Avoid_：流程、服务、service

**投递 / Deliver**：
将一首歌以聊天消息形式发送给用户的行为——可能是音频文件（`File`）或音乐卡片（`Json`），由管线根据配置和签名结果自动决定。区别于搜索（只查不发）。
_Avoid_：发送、下发、推送
