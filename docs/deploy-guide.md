[LKML-BOT](https://mp.weixin.qq.com/s/WLGxKmgCilW4SJXFqDzw6Q) 是基于 [NoneBot 2](https://nonebot.dev/) 框架构建的机器人，用于监控 Linux 内核及其他子系统邮件列表，并通过 Discord / 飞书推送更新通知。

> 框架与组件引用：本项目使用 NoneBot 2 及其适配器生态（`nonebot-adapter-discord`、`nonebot-adapter-feishu`），并基于其插件与驱动机制实现业务逻辑。

## 平台能力对比

| 能力 | Discord | 飞书 |
|------|---------|------|
| 新邮件 / 回复通知 | ✅ Webhook 推送 | ✅ Webhook 推送 |
| PATCH 卡片 & Thread 跟踪 | ✅ 完整支持 | ✅ 卡片通知 |
| 命令交互（订阅/过滤/监控等） | ✅ 全部命令 | ❌ 不支持 |
| 接入方式 | Bot Token + Webhook | 自定义机器人 Webhook |

> 飞书端以**群自定义机器人 Webhook** 方式接入，仅接收通知推送，不支持命令交互。

## 功能特性

- 📧 监控多个邮件列表子系统
- 🔔 自动检测新邮件和回复，推送到 Discord / 飞书

## 如何启用

### 前置要求

- Python 3.9+
- **Discord Bot Token**（必需，用于连接 Discord 和命令交互）
- *飞书 Webhook URL（可选，用于通知推送）*

### 安装依赖

```bash
pip install -e .
```

### 获取飞书 Webhook URL（可选）

**步骤 1：邀请自定义机器人进群**

在 **飞书/Lark** 打开目标群聊，点击右上角 "更多" 按钮。选择 **"设置" → "群机器人"**。

> 注：在**外部群**中添加应用机器人需使用飞书 V7.19 及以上版本；其他使用场景无版本要求。


![](https://files.mdnice.com/user/128216/adbe801c-49f8-4532-bece-60627c6cbeb1.png)


点击 "添加机器人"，选择 "自定义机器人"。

![](https://files.mdnice.com/user/128216/9d614008-ef37-453c-bb1d-af22d73cba12.png)

![](https://files.mdnice.com/user/128216/f9bfedf8-743f-4510-b76c-da3145b068a6.png)

![](https://files.mdnice.com/user/128216/dac255ca-0ffe-4d79-a276-0260f8979fe9.png)

**步骤 2：配置机器人信息**

设置机器人的 头像、名称、描述。

![](https://files.mdnice.com/user/128216/9160fd61-5448-4d99-b159-3c3088e42334.png)

点击 "添加" 完成创建。

**步骤 3：获取Webhook地址**

创建完成后，系统会生成一个类似以下格式的地址（即接下来需要配置的环境变量 **LKML_FEISHU_WEBHOOK_URL** 的值）：

https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxxxxxxxxxxx

![](https://files.mdnice.com/user/128216/ad11c8d7-120f-4d18-aba1-b3bf4e748bf7.png)

### 配置环境变量

创建 `.env` 文件（或在系统环境变量中设置）：

```bash
# ===== Discord 配置（必需）=====
DISCORD_BOTS='[{"token": "YOUR_BOT_TOKEN", "intent": {"guild_messages": true, "direct_messages": true}}]'
LKML_DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
LKML_DISCORD_CHANNEL_ID=CHANNEL_ID

# Discord Webhook URL（必需，用于推送通知到频道）
# 获取方式：频道设置 > 整合 > Webhook > 新建
LKML_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# 飞书 Webhook URL（可选）
LKML_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...

# 监控间隔（默认 300 秒即 5 分钟，建议设为 60 秒）
LKML_MONITORING_INTERVAL=60
```

### 启动机器人

```bash
# 直接运行
python bot.py

# 或使用 Docker
docker compose up -d
```

机器人启动后会自动连接 Discord、初始化数据库、启动监控调度器。

## 配置项说明

### 必需配置

| 环境变量 | 说明 |
|---------|------|
| `DISCORD_BOTS` | Discord Bot Token JSON 配置 |
| `LKML_DISCORD_BOT_TOKEN` | Discord Bot Token（同上面的 token 值） |
| `LKML_DISCORD_CHANNEL_ID` | Discord 频道 ID（用于发送消息和创建 Thread） |
| `LKML_DISCORD_WEBHOOK_URL` | Discord Webhook URL（用于推送通知到频道） |

### 飞书通知（可选）

| 环境变量 | 说明 |
|---------|------|
| `LKML_FEISHU_WEBHOOK_URL` | 飞书 Webhook URL，未配置则不推送飞书通知 |

## 如何使用（Discord 命令）

> 以下命令仅在 **Discord** 平台可用。飞书端为 Webhook 通知，不支持命令交互。

### 命令格式

所有命令均需 @ 提及机器人：`@lkml-bot /命令 [参数...]`

### 可用命令

#### `/help`
查看帮助信息。

#### `/subscribe` / `/sub`
订阅子系统邮件列表。订阅后，新邮件或回复会自动推送通知。

```bash
# 订阅
@lkml-bot /sub rust-for-linux

# 批量订阅（空格或逗号分隔）
@lkml-bot /sub linux-kernel,netdev,dri-devel

# 查看订阅列表
@lkml-bot /sub list

# 搜索可订阅子系统
@lkml-bot /sub search linux
```

#### `/unsubscribe` / `/unsub`
取消订阅。

```bash
@lkml-bot /unsub rust-for-linux

# 批量取消
@lkml-bot /unsub linux-kernel,netdev,dri-devel
```

#### `/start-monitor` / `/stop-monitor` / `/run-monitor`
监控任务管理。机器人启动时会**自动开始监控**，通常无需手动操作。

- `/start-monitor` — 手动启动监控（仅在被停止后使用）
- `/stop-monitor` — 暂停监控
- `/run-monitor` — 立即执行一次检查（不等待定时触发）

#### `/filter`

控制哪些 PATCH 会创建卡片。支持**高亮模式**（默认，所有卡片都创建，匹配的额外标识）和**独占模式**（仅匹配的创建）。

子命令：

| 子命令 | 说明 |
|--------|------|
| `add <name> <conditions> [--exclusive]` | 添加规则（同名覆盖） |
| `list [--enabled-only]` | 列出规则 |
| `show <name\|id>` | 查看详情 |
| `remove <name\|id>` | 删除规则 |
| `enable / disable <name\|id>` | 启用 / 禁用规则 |

条件格式为 `key=value`，常用键：`author`、`author_email`、`subsystem`、`subject`、`keywords`、`cclist`。支持普通文本（子串包含，大小写不敏感）、正则（`/.../` 或 `/.../i`）和逗号分隔列表（OR 逻辑）。

```bash
# 按邮箱域名过滤（高亮模式）
/filter add email-domain author_email=@gmail\.com

# 独占模式 — 只创建匹配的卡片
/filter add my-rule author_email=/@example\.com$/ --exclusive
```

#### `/watch` / `/w`

为系列 PATCH 的 Cover Letter 创建专属 Thread，持续聚合后续回复。

```bash
/watch <message_id_header>
```

- 系列 PATCH 只为 Cover Letter 创建卡片；子补丁保存在数据库中用于 Thread 概览
- 有新回复时，自动更新概览并发送通知

### 使用流程

1. **首次使用**：机器人启动后自动开始监控，使用 `/sub <subsystem>` 订阅感兴趣的子系统
2. **日常使用**：机器人每 5 分钟自动检查邮件列表，有新消息时推送通知到 Discord / 飞书
3. **维护**：通常无需干预；如需暂停可用 `/stop-monitor`，恢复用 `/start-monitor`

## 注意事项

- 确保 Discord Bot 在目标频道有**发送消息**和**创建 Thread** 的权限
- 未配置 Webhook 的平台不会收到通知（仅记录日志）
- 飞书端仅接收通知推送，不支持命令交互
- 数据库默认使用 SQLite，数据文件位于 `./lkml_bot.db`（Docker 部署时挂载 `./data` 目录持久化）
