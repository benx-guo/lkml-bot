# LKML-BOT

基于 [NoneBot 2](https://nonebot.dev/) 框架构建的机器人，用于监控 Linux 内核及其他子系统邮件列表，并通过 Discord/Feishu 推送更新与指令交互。支持监控多个子系统，并可用 Discord 命令进行订阅与管理。

> 框架与组件引用：本项目使用 NoneBot 2 及其适配器生态（例如 `nonebot-adapter-discord`、`nonebot-adapter-feishu`），并基于其插件与驱动机制实现业务逻辑。

## 功能特性

- 📧 监控多个邮件列表子系统
- 🔔 自动检测新邮件和回复，并发送通知到 Discord/Feishu

## 如何启用

### 前置要求

- Python 3.9+
- NoneBot 框架
- Discord Bot Token

### 安装依赖

```bash
# 安装运行时依赖
pip install -e .

# 安装开发依赖（包括代码规范和格式化工具）
pip install -e ".[dev]"
```

### 配置环境变量

创建 `.env` 文件（或在系统环境变量中设置）：

```bash
# Discord Bot Token（必需）
DISCORD_BOTS='[{"token": "YOUR_BOT_TOKEN", "intent": {"guild_messages": true, "direct_messages": true}}]'

# Discord Webhook URL（用于发送通知消息）
LKML_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# 数据库连接 URL（可选，默认为 sqlite+aiosqlite:///./lkml_bot.db）
LKML_DATABASE_URL=sqlite+aiosqlite:///./lkml_bot.db

# 手动配置的额外子系统（可选，逗号分隔）
LKML_MANUAL_SUBSYSTEMS=rust-for-linux

# 每次更新显示的最大news数量（可选，默认 20）
LKML_MAX_NEWS_COUNT=20

# 监控任务执行周期（秒，可选，默认 300 秒即 5 分钟）
# 最小值为 60 秒（1 分钟），避免过于频繁的请求
LKML_MONITORING_INTERVAL=300
```

### 启动机器人

```bash
# 使用 NoneBot CLI 启动
nb run

# 或使用 Python 直接运行
python bot.py
```

机器人启动后会自动：
- 连接到 Discord
- 加载插件
- 初始化数据库
- 启动监控调度器（如果已启动监控任务）

## 配置项说明

### 必需配置

| 环境变量 | 说明 | 示例 |
|---------|------|------|
| `DISCORD_BOTS` | Discord Bot Token JSON 配置 | `[{"token": "YOUR_TOKEN", ...}]` |
| `LKML_DISCORD_WEBHOOK_URL` | Discord Webhook URL，用于发送通知消息。如果未配置，消息只会在日志中记录 | - |

### 可选配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `LKML_DATABASE_URL` | 数据库连接 URL | `sqlite+aiosqlite:///./lkml_bot.db` |
| `LKML_MANUAL_SUBSYSTEMS` | 手动配置的额外子系统列表（逗号分隔）。内核子系统会自动从 vger 缓存获取，此配置用于添加无法从网页直接获取的子系统 | - |
| `LKML_MAX_NEWS_COUNT` | 每次更新显示的最大新闻数量 | `20` |
| `LKML_MONITORING_INTERVAL` | 监控任务执行周期（秒）。最小值为 60 秒（1 分钟），避免过于频繁的请求 | `300`（5 分钟） |

## 如何使用

### 命令格式

所有命令均需要 @ 提及机器人，格式为：`@机器人 /命令 [参数...]`

### 可用命令

#### `/help`
查看帮助信息，自动汇总所有已注册的命令。

**示例：**
```
@lkml-bot /help
```

#### `/subscribe <subsystem>`
订阅一个子系统的邮件列表。订阅后，当该子系统有新邮件或回复时，你会收到通知。

**参数：**
- `<subsystem>`: 子系统名称，如 `lkml`、`rust-for-linux`、`netdev`、`dri-devel` 等

**示例：**
```
@lkml-bot /subscribe lkml
@lkml-bot /subscribe rust-for-linux
```

#### `/unsubscribe <subsystem>`
取消订阅一个子系统的邮件列表。

**参数：**
- `<subsystem>`: 子系统名称

**示例：**
```
@lkml-bot /unsubscribe lkml
```

#### `/start-monitor`
启动邮件列表监控定时任务。启动后，机器人会定期检查所有已订阅的子系统，并在发现新邮件时发送通知。

**注意**：机器人启动时会自动启动监控任务，此命令仅在监控被停止后需要手动启动时使用。

**示例：**
```
@lkml-bot /start-monitor
```

#### `/stop-monitor`
停止邮件列表监控定时任务。

**示例：**
```
@lkml-bot /stop-monitor
```

#### `/run-monitor`
立即执行一次邮件列表监控任务，不等待定时触发。用于测试或手动触发检查。

**示例：**
```
@lkml-bot /run-monitor
```

**注意**：目前所有命令都可以使用，管理员权限功能将在后续版本中实现。

1. **首次使用**：
   - 机器人启动时会自动启动监控任务（无需手动操作）
   - 用户执行 `/subscribe <subsystem>` 订阅感兴趣的子系统

2. **日常使用**：
   - 机器人自动定期检查邮件列表（每 5 分钟）
   - 当有新邮件或回复时，自动发送通知到 Discord Webhook
   - 用户可以随时订阅/取消订阅子系统

3. **维护**：
   - 可以使用 `/start-monitor` 启动监控（如果被停止）
   - 可以使用 `/stop-monitor` 暂停监控
   - 使用 `/run-monitor` 手动触发一次检查

## 注意事项

- 监控任务启动后会自动定期检查邮件列表更新并发送通知到 Discord/Feishu 频道
- 确保 Discord Bot 在目标频道有发送消息的权限
- 如果没有配置 `LKML_DISCORD_WEBHOOK_URL`，监控结果只会在日志中记录，不会发送到 Discord

## TODO

- [ ] 实现从服务器缓存获取 vger 子系统列表的功能（`src/lkml/vger_cache.py`）
  - Bot 的服务器缓存会存储所有从 vger 获取的内核子系统信息（键值对格式）
  - 需要在 `get_vger_subsystems_from_cache()` 函数中实现从服务器缓存读取逻辑
  - 函数应返回子系统名称列表，例如: `["lkml", "netdev", "dri-devel", ...]`
- [ ] 实现管理员权限系统
  - 目前所有命令都可以使用，`check_admin()` 函数暂时返回 `True`
  - 后续需要实现 Discord 用户/角色权限验证
  - 管理员命令（如 `/start-monitor`、`/stop-monitor`、`/run-monitor`）应限制为特定用户或角色才能执行
- [ ] 实现 `/add-user` 命令
  - 添加用户过滤功能，支持在子系统邮件列表中搜索指定用户/组织
  - 启用后仅发送来自已订阅用户的特定邮件
- [ ] 实现 `/del-user` 命令
  - 删除已添加的用户过滤
  - 移除后不再发送与该用户相关的邮件信息
- [ ] 实现 `/news` 命令
  - 强制发送当前时间最新的前 N 条邮件列表记录
  - 支持指定子系统或所有已订阅子系统

## 项目结构

```
src/
├── lkml/                        # 核心业务逻辑（独立于机器人框架）
│   ├── config.py                # 配置管理（LKMLConfig）
│   ├── vger_subsystem.py        # vger 子系统来源（get_vger_subsystems）
│   ├── scheduler.py             # 任务调度器（LKMLScheduler）
│   ├── db/                      # 数据库接口与模型
│   │   ├── database.py          # 数据库接口与实现（LKMLDatabase）
│   │   └── models.py            # SQLAlchemy 模型
│   ├── service/                 # 业务服务层
│   │   ├── service.py           # 基础服务
│   │   ├── monitoring_service.py# 监控相关服务
│   │   ├── subsystem_service.py # 子系统相关服务
│   │   └── query_service.py     # 查询相关服务
│   └── feed/                    # 邮件列表监控
│       ├── feed.py              # Feed 抓取与入库
│       ├── feed_monitor.py      # 监控编排（LKMLFeedMonitor）
│       └── types.py             # 数据类型定义
└── plugins/
    └── lkml_bot/                # NoneBot 插件实现
        ├── __init__.py          # 插件入口（注册调度器、启动/停止钩子）
        ├── config.py            # 插件侧配置（继承 LKMLConfig）
        ├── shared.py            # 插件共享工具
        ├── message_sender.py    # 聚合发送器
        ├── commands/            # 命令处理器
        ├── adapters/            # 消息适配器（Discord 等）
        └── renders/             # 消息渲染器（Discord/Feishu）
```

## 代码规范和格式化

项目使用 [Ruff](https://github.com/astral-sh/ruff) 进行代码检查和格式化，使用 [MyPy](https://mypy.readthedocs.io/) 进行类型检查。

### 安装开发工具

```bash
pip install -e ".[dev]"
```

### 使用方法

```bash
# 检查代码（不修改文件）
ruff check .

# 自动修复可修复的问题
ruff check --fix .

# 格式化代码
ruff format .

# 类型检查
mypy src/

# 运行所有检查
ruff check . && ruff format --check . && mypy src/
```

### VS Code 集成

推荐安装以下 VS Code 扩展：
- [Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff) - 代码检查和格式化
- [MyPy Type Checker](https://marketplace.visualstudio.com/items?itemName=ms-python.mypy-type-checker) - 类型检查

## 文档

更多信息请查看 [NoneBot 官方文档](https://nonebot.dev/)


## 许可证

本项目使用 MIT License。详情见根目录的 `LICENSE` 文件。
