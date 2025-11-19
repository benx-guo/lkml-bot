"""subscribe_patch 命令的验证和参数解析函数"""

from typing import Optional, Tuple

from nonebot.adapters import Event
from nonebot.log import logger

from ..shared import extract_command, get_user_info_or_finish, get_database
from ..thread import DiscordThreadManager


async def validate_command(
    msg_text: str, event: Event, matcher
) -> Tuple[Optional[str], Optional[Tuple[str, str]]]:
    """验证命令并提取参数

    Args:
        msg_text: 消息文本
        event: 事件对象
        matcher: NoneBot matcher

    Returns:
        (message_id, user_info) 元组，如果验证失败则返回 (None, None)
    """
    # 尝试匹配 /watch 或 /w
    cmd_text = extract_command(msg_text, "/watch")
    if not cmd_text:
        cmd_text = extract_command(msg_text, "/w")

    if not cmd_text:
        logger.debug(f"[watch] Not a watch command, ignoring. Message: '{msg_text}'")
        return None, None

    logger.info(f"[watch] Processing command: {cmd_text}")
    logger.debug(f"[watch] Original message text: '{msg_text}'")

    # 获取用户信息
    user_info = await get_user_info_or_finish(event, matcher)
    if not user_info:
        return None, None

    user_id, user_name = user_info

    # 解析命令参数
    message_id = _parse_message_id(cmd_text, matcher)
    if not message_id:
        return None, None

    logger.info(f"User {user_name} ({user_id}) subscribing to PATCH: {message_id}")

    return message_id, user_info


def _parse_message_id(cmd_text: str, matcher) -> Optional[str]:
    """解析 message_id 参数

    Args:
        cmd_text: 命令文本
        matcher: NoneBot matcher

    Returns:
        message_id，如果解析失败则返回 None
    """
    parts = cmd_text.split()
    if len(parts) < 2:
        matcher.finish(
            "❌ 用法错误\n\n"
            "使用方法: `/watch <message_id>` 或 `/w <message_id>`\n\n"
            "message_id 可以从 PATCH 卡片中复制"
        )
        return None

    return parts[1]


def get_thread_manager() -> Tuple[Optional[object], Optional[DiscordThreadManager]]:
    """获取数据库和 Thread 管理器

    Returns:
        (database, thread_manager) 元组，如果失败则返回 (None, None)
    """
    database = get_database()
    if not database:
        return None, None

    thread_manager = DiscordThreadManager(database)
    return database, thread_manager
