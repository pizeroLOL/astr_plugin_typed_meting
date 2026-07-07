# Typed Meting

AstrBot 点歌/搜歌插件，对接 Meting API（node / php 两种实现）。

## Setup

```bash
uv sync
```

### 运行测试

```bash
python -m unittest discover -s tests -v
```

### 生成配置 Schema

```bash
python tools/generate_conf_schema.py
```

该脚本自动生成 `_conf_schema.json`，并用数据模型校验。

## 代码地图

| 文件 | 职责 |
|------|------|
| `main.py` | 插件入口，`class Plugin(Star)`。三个命令：`/点歌`、`/搜歌`、`llm_tool order_song` |
| `cfg.py` | 配置模型：`Config` > `MetingConfig` / `MusicCardConfig` / `SearchConfig` |
| `utils.py` | 工具函数：URL 构造（node/php/custom）、音乐卡片构造、`session_waiter` 包装 |
| `ty.py` | 数据类型：`SongItem`、`CardInfo`、`CardSignResult`、`PluginLogger` 等 |

## 约定

- 使用 `ruff format .` 和 `ruff check .` 格式化/检查
- 使用 conventional commits（`feat:`, `fix:`, `chore:` 等）
- 注释用中文
- 路径操作用 `pathlib.Path`

### Python 类型标注

- **class 成员字段必须在类级别标注类型**，即使值在 `__init__` 中赋值。示例：
  ```python
  class Foo:
      _client: AsyncClient
      _config: Config

      def __init__(self, client: AsyncClient, config: Config):
          self._client = client
          self._config = config
  ```
- 所有函数/方法签名必须标注参数和返回值类型
- 用 `| None` 而非 `Optional[...]`
