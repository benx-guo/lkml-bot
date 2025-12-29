"""帮助命令模块"""

from nonebot import on_message
from nonebot.rule import to_me
from nonebot.adapters import Message, Event
from nonebot.adapters.discord import MessageCreateEvent
from nonebot.params import EventMessage

from ..shared import (
    COMMAND_REGISTRY,
    get_bot_mention_name,
    register_command,
    send_embed_message,
)

# 只有当消息 @ 到机器人，且纯文本以 "/help" 开头时才回复
# 优先级设为 40，block=False 确保如果不匹配不会阻止其他命令
HelpCmd = on_message(rule=to_me(), priority=40, block=False)


def _build_help_embed() -> tuple[str, str]:
    """构建帮助信息的标题和描述

    Returns:
        (title, description) 元组
    """
    bot_name = get_bot_mention_name()

    description_parts = [f"**命令格式**\n```\n{bot_name} /<子命令> [参数...]\n```"]

    if not COMMAND_REGISTRY:
        description_parts.append("目前没有可用命令。")
    else:
        # 分组显示：管理员命令和公开命令
        admin_commands = [m for m in COMMAND_REGISTRY if m.get("admin_only")]
        public_commands = [m for m in COMMAND_REGISTRY if not m.get("admin_only")]

        if admin_commands:
            description_parts.append("**管理员命令**")
            for meta in admin_commands:
                usage = meta.get("usage", "")
                desc = meta.get("description", "")
                description_parts.append(f"• `{usage}` - {desc}")
            description_parts.append("")

        if public_commands:
            description_parts.append("**公开命令**")
            for meta in public_commands:
                usage = meta.get("usage", "")
                desc = meta.get("description", "")
                description_parts.append(f"• `{usage}` - {desc}")

    return "LKML Bot 帮助", "\n".join(description_parts)


@HelpCmd.handle()
async def handle_help(event: Event, message: Message = EventMessage()):
    """聚合并展示各命令声明的帮助信息"""
    text = message.extract_plain_text().strip()
    if not text.startswith("/help"):
        return  # 不是 help 命令，不处理，让其他命令处理

    # 只处理 MessageCreateEvent，忽略更新事件
    if not isinstance(event, MessageCreateEvent):
        return

    title, description = _build_help_embed()
    await send_embed_message(event, title, description, HelpCmd)


# 注册 help 命令自身（公开命令）
register_command(
    name="help",
    usage="/help",
    description="查看帮助信息",
    admin_only=False,
)
