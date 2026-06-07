# Typed Meting

用于为接入使用了如下项目的用户提供接入 Astrbot 的能力，提供返回音乐卡片和文件两种选项。

- node `https://github.com/metowolf/meting`
- php `https://github.com/nanorocky/meting-api`

## 开发

### 运行测试

运行所有测试

```bash
python -m unittest discover -s tests -v
```

运行单个测试文件

```bash
python -m unittest tests.test_generate_conf_schema -v
```

### 生成配置 Schema

```bash
python tools/generate_conf_schema.py
```

该脚本会自动生成 `_conf_schema.json` 并使用数据模型进行校验。
