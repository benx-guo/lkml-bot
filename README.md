# LKML-BOT

基于 [NoneBot 2](https://nonebot.dev/) 框架构建的机器人，用于监控 Linux 内核及其他子系统邮件列表，并通过 Discord / 飞书推送更新通知。

## 快速开始

```bash
pip install -e .
cp .env.example .env  # 编辑 .env 填入 Discord Bot Token、Channel ID、Webhook URL
python bot.py
```

详细配置与命令说明见 [部署及应用指南](docs/deploy-guide.md)。

## 开发

```bash
# 格式化代码
make format

# 代码检查
make check-lint
```

## 许可证

MIT License
