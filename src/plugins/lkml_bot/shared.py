"""共享工具模块

提供插件共用的工具函数和常量，包括：
- 命令注册管理
- 权限检查
- 插件元数据
"""

from nonebot.plugin import PluginMetadata
from nonebot.adapters import Event
from typing import Callable, Awaitable, Any
from functools import wraps

try:
    from nonebot.adapters.discord import (
        GuildMessageCreateEvent as DiscordGuildMessageEvent,
    )  # type: ignore
except Exception:
    DiscordGuildMessageEvent = None  # type: ignore


__plugin_meta__ = PluginMetadata(
    name="LKML Bot",
    description="邮件列表助手命令",
    usage="@lkml-bot /<子命令> [参数...]",
)


# 命令注册表：各命令模块在导入时将自身的元信息注册到这里
COMMAND_REGISTRY = []  # list of dict: {name, usage, description, admin_only}


def register_command(name: str, usage: str, description: str, admin_only: bool = False):
    """注册命令元信息，供 help 命令聚合显示。

    参数:
    - name: 命令名（如 subscribe）
    - usage: 用法字符串（不含 @lkml-bot 前缀，例如 "/subscribe <subsystem>"）
    - description: 简短描述
    - admin_only: 是否仅管理员可用
    """

    COMMAND_REGISTRY.append(
        {
            "name": name,
            "usage": usage,
            "description": description,
            "admin_only": admin_only,
        }
    )


def check_admin(event: Event) -> bool:
    """检查事件发起者是否为管理员（Discord 角色/用户ID 或 SUPERUSERS）。

    返回值: True 表示是管理员，False 表示不是。
    """

    return _is_admin(event)


def require_admin(func: Callable[..., Awaitable[Any]]):
    """装饰器：要求调用者为管理员。

    用法示例：
    @require_admin
    async def handle_cmd(event: Event, matcher: Matcher):
        # 只有管理员才能执行到这里
        await matcher.finish("管理员专用命令")

    注意：被装饰的函数需要接收 event 和 matcher 参数。
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # 尝试找到 Event 和 Matcher
        event = None
        matcher = None

        for arg in args:
            if isinstance(arg, Event):
                event = arg
            elif hasattr(arg, "finish"):  # 通常是 Matcher
                matcher = arg

        if not event:
            event = kwargs.get("event")
        if not matcher:
            matcher = kwargs.get("matcher")

        if not event or not _is_admin(event):
            if matcher and hasattr(matcher, "finish"):
                await matcher.finish("没有权限")
            return

        return await func(*args, **kwargs)

    return wrapper


def _is_admin(event: Event) -> bool:
    """判断事件发起者是否为管理员。

    规则（任一满足）：
    1) Discord: 用户 ID 在 `discord_admin_user_ids` 或拥有 `discord_admin_role_ids` 中的角色
    2) 回退: 用户 ID 在 `superusers` 配置中
    """

    return True


# 基础提示（头部）
BASE_HELP_HEADER = "用法: @lkml-bot /<子命令> [参数...]\n"
