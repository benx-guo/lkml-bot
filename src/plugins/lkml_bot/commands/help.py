"""帮助命令模块"""

from nonebot import on_message
from nonebot.rule import to_me
from nonebot.adapters import Message
from nonebot.params import EventMessage

from ..shared import COMMAND_REGISTRY, get_base_help_header, register_command

# 只有当消息 @ 到机器人，且纯文本以 "/help" 开头时才回复
# 优先级设为 40，block=False 确保如果匹配失败不会阻止其他命令
HelpCmd = on_message(rule=to_me(), priority=40, block=False)


@HelpCmd.handle()
async def handle_help(message: Message = EventMessage()):
    """聚合并展示各命令声明的帮助信息"""
    text = message.extract_plain_text().strip()
    if not text.startswith("/help"):
        return  # 不是 help 命令，不处理，让其他命令处理

    lines = ["🤖 **LKML Bot 帮助**", "", get_base_help_header().rstrip(), ""]

    if not COMMAND_REGISTRY:
        lines.append("目前没有可用命令。")
    else:
        # 分组显示：管理员命令和公开命令
        admin_commands = [m for m in COMMAND_REGISTRY if m.get("admin_only")]
        public_commands = [m for m in COMMAND_REGISTRY if not m.get("admin_only")]

        if admin_commands:
            lines.append("**管理员命令:**")
            for meta in admin_commands:
                usage = meta.get("usage", "")
                desc = meta.get("description", "")
                lines.append(f"• `{usage}` - {desc}")
            lines.append("")

        if public_commands:
            lines.append("**公开命令:**")
            for meta in public_commands:
                usage = meta.get("usage", "")
                desc = meta.get("description", "")
                lines.append(f"• `{usage}` - {desc}")

    # 处理 help 命令时使用 finish 会阻止事件传播
    await HelpCmd.finish("\n".join(lines))


# 注册 help 命令自身（公开命令）
register_command(
    name="help",
    usage="/help",
    description="查看帮助信息",
    admin_only=False,
)
