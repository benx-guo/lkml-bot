"""邮件回复处理模块

提供回复层级构建、查找、格式化等功能。
这些功能是 lkml 域的核心功能，不依赖于任何特定的渲染平台。
"""

from datetime import datetime
from typing import Optional

import logging

logger = logging.getLogger(__name__)

from lkml.db.repo.email_message_repository import EMAIL_MESSAGE_REPO
from lkml.db.repo.patch_subscription_repository import PATCH_SUBSCRIPTION_REPO


def format_reply_author(reply) -> str:
    """格式化回复作者

    Args:
        reply: EmailMessage 对象

    Returns:
        格式化后的作者字符串
    """
    if not reply.sender:
        return "Unknown"
    return reply.sender


def format_reply_subject(reply) -> str:
    """格式化回复主题

    Args:
        reply: EmailMessage 对象

    Returns:
        格式化后的主题字符串
    """
    subject = reply.subject
    if len(subject) > 40:
        return subject[:40] + "..."
    return subject


def is_new_reply(reply, new_threshold: datetime) -> bool:
    """检查是否是新的回复

    Args:
        reply: EmailMessage 对象
        new_threshold: 新回复的时间阈值

    Returns:
        如果是新回复返回 True，否则返回 False
    """
    if not reply.received_at:
        return False

    try:
        reply_time = datetime.fromisoformat(reply.received_at.replace("Z", "+00:00"))
        if reply_time.tzinfo:
            reply_time = reply_time.astimezone(datetime.now().astimezone().tzinfo)
        else:
            reply_time = reply_time.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return reply_time > new_threshold
    except (ValueError, TypeError) as e:
        logger.debug(f"Error parsing reply time: {e}")
        return False


def parse_reply_time(reply) -> Optional[datetime]:
    """解析回复时间

    Args:
        reply: EmailMessage 对象

    Returns:
        datetime 对象，如果解析失败则返回 None
    """
    if not reply.received_at:
        return None

    try:
        reply_time = datetime.fromisoformat(reply.received_at.replace("Z", "+00:00"))
        if reply_time.tzinfo:
            reply_time = reply_time.astimezone(datetime.now().astimezone().tzinfo)
        else:
            reply_time = reply_time.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return reply_time
    except (ValueError, TypeError):
        return None


def _extract_message_id_from_header(in_reply_to_header: Optional[str]) -> Optional[str]:
    """从 in_reply_to_header 中提取 message_id

    处理可能包含尖括号、多个 message_id 等情况

    Args:
        in_reply_to_header: in_reply_to 头部值

    Returns:
        提取的 message_id，如果无法提取则返回 None
    """
    if not in_reply_to_header:
        return None

    # 移除尖括号
    cleaned = in_reply_to_header.strip()
    if cleaned.startswith("<") and cleaned.endswith(">"):
        cleaned = cleaned[1:-1]

    # 如果包含多个 message_id（用空格或逗号分隔），取第一个
    # 通常第一个是主要的回复目标
    parts = cleaned.split()
    if parts:
        return parts[0].strip()

    return cleaned if cleaned else None


async def _find_parent_reply_in_list(  # pylint: disable=too-many-return-statements
    session,
    in_reply_to: str,
    reply_map: dict,
    patch_message_id: str,
    max_depth: int = 5,
) -> Optional[str]:
    """在回复列表中查找父回复

    递归查找 in_reply_to 链，直到找到在回复列表中的父回复

    Args:
        session: 数据库会话
        in_reply_to: 回复的 in_reply_to_header
        reply_map: 回复映射字典
        patch_message_id: PATCH 的 message_id
        max_depth: 最大递归深度

    Returns:
        父回复的 message_id_header，如果找不到则返回 None
    """
    if max_depth <= 0 or not in_reply_to:
        return None

    # 提取 message_id（处理尖括号、多个 message_id 等情况）
    extracted_id = _extract_message_id_from_header(in_reply_to)
    if not extracted_id:
        return None

    # 检查是否是直接回复 PATCH
    if extracted_id == patch_message_id or patch_message_id in extracted_id:
        return None  # 对 PATCH 的直接回复，没有父回复

    # 在回复列表中查找
    if extracted_id in reply_map:
        return extracted_id

    # 尝试模糊匹配（处理带尖括号等情况）
    for reply_id in reply_map:
        if extracted_id in reply_id or reply_id in extracted_id:
            return reply_id

    # 如果找不到，递归查找 in_reply_to 链
    email_msg = await EMAIL_MESSAGE_REPO.find_by_message_id_header(
        session, extracted_id
    )
    if email_msg and email_msg.in_reply_to_header:
        return await _find_parent_reply_in_list(
            session,
            email_msg.in_reply_to_header,
            reply_map,
            patch_message_id,
            max_depth - 1,
        )

    return None


async def build_reply_hierarchy(
    session, patch_replies: list, patch_message_id: str
) -> dict:
    """构建回复层级关系

    通过递归查找 in_reply_to 链来确定真正的父回复

    Args:
        session: 数据库会话
        patch_replies: 回复列表（应该已经按时间正序排序）
        patch_message_id: PATCH 的 message_id

    Returns:
        层级字典：{message_id: {'reply': reply, 'children': [...]}}
    """
    # 构建回复映射
    reply_map = {}
    root_replies = []

    for reply in patch_replies:
        reply_map[reply.message_id_header] = {"reply": reply, "children": []}

    # 构建层级关系
    for reply in patch_replies:
        in_reply_to_raw = reply.in_reply_to_header
        if not in_reply_to_raw:
            # 没有 in_reply_to，作为根回复
            root_replies.append(reply.message_id_header)
            continue

        # 提取 message_id（处理尖括号、多个 message_id 等情况）
        in_reply_to = _extract_message_id_from_header(in_reply_to_raw)

        if not in_reply_to:
            # 无法提取 message_id，作为根回复
            root_replies.append(reply.message_id_header)
            continue

        # 检查是否是直接回复 PATCH
        if in_reply_to == patch_message_id or patch_message_id in in_reply_to:
            root_replies.append(reply.message_id_header)
            continue

        # 查找父回复（递归查找 in_reply_to 链）
        parent_id = await _find_parent_reply_in_list(
            session, in_reply_to_raw, reply_map, patch_message_id
        )

        if parent_id:
            # 找到父回复，作为子回复
            reply_map[parent_id]["children"].append(reply.message_id_header)
        else:
            # 找不到父回复，作为根回复处理
            root_replies.append(reply.message_id_header)

    # 对根回复按时间正序排序
    root_replies.sort(
        key=lambda rid: parse_reply_time(reply_map[rid]["reply"]) or datetime.min
    )

    # 对每个回复的子回复也按时间正序排序
    for reply_data in reply_map.values():
        reply_data["children"].sort(
            key=lambda cid: parse_reply_time(reply_map[cid]["reply"]) or datetime.min
        )

    return {"reply_map": reply_map, "root_replies": root_replies}


async def find_actual_patch_for_reply(
    session, in_reply_to: str, max_depth: int = 5
) -> Optional[object]:
    """查找回复实际对应的 PATCH

    递归查找 in_reply_to 链，直到找到实际的 PATCH（不是 cover letter）

    Args:
        session: 数据库会话
        in_reply_to: 回复的 message_id
        max_depth: 最大递归深度

    Returns:
        PATCH 订阅对象，如果不存在则返回 None
    """
    if max_depth <= 0 or not in_reply_to:
        return None

    # 查找这个 message_id 对应的 PATCH
    patch_sub = await PATCH_SUBSCRIPTION_REPO.find_by_message_id(session, in_reply_to)
    if patch_sub:
        # 如果找到的 PATCH 不是 cover letter，返回它
        if patch_sub.patch_index != 0:
            return patch_sub
        # 如果是 cover letter，返回 None（表示这个回复是针对 cover letter 的）
        return None

    # 如果这个 message_id 不是 PATCH，查找对应的邮件，继续查找它的 in_reply_to
    email_msg = await EMAIL_MESSAGE_REPO.find_by_message_id_header(session, in_reply_to)
    if email_msg and email_msg.in_reply_to_header:
        return await find_actual_patch_for_reply(
            session, email_msg.in_reply_to_header, max_depth - 1
        )

    return None


async def find_all_replies_to_patch(
    session, patch_message_id: str, max_depth: int = 10
) -> list:
    """查找 PATCH 的所有回复（包括直接回复和间接回复）

    递归查找所有回复，包括：
    - 直接回复 PATCH 的回复
    - 回复的回复（间接回复）

    Args:
        session: 数据库会话
        patch_message_id: PATCH 的 message_id
        max_depth: 最大递归深度

    Returns:
        所有回复列表
    """
    logger.info(
        f"[find_all_replies_to_patch] Starting search for replies to "
        f"patch_message_id={patch_message_id}"
    )
    all_replies = []
    visited = set()  # 避免重复处理
    to_process = [patch_message_id]  # 待处理的消息 ID 列表

    for depth in range(max_depth):
        if not to_process:
            logger.info(
                f"[find_all_replies_to_patch] No more messages to process at depth {depth}"
            )
            break

        current_batch = to_process
        to_process = []

        logger.info(
            f"[find_all_replies_to_patch] Processing {len(current_batch)} messages at depth {depth}"
        )

        for message_id in current_batch:
            if message_id in visited:
                continue
            visited.add(message_id)

            # 查找直接回复这个消息的所有回复
            logger.debug(
                f"[find_all_replies_to_patch] Searching for replies to message_id={message_id}"
            )
            direct_replies = await EMAIL_MESSAGE_REPO.find_replies_to(
                session, message_id, limit=100
            )

            logger.info(
                f"[find_all_replies_to_patch] Found {len(direct_replies)} direct replies "
                f"to message_id={message_id}"
            )

            for reply in direct_replies:
                if reply.message_id_header not in visited:
                    logger.debug(
                        f"[find_all_replies_to_patch] Adding reply: "
                        f"message_id_header={reply.message_id_header}, "
                        f"in_reply_to_header={reply.in_reply_to_header}"
                    )
                    all_replies.append(reply)
                    # 将这个回复的 message_id 加入待处理列表，以便查找它的回复
                    to_process.append(reply.message_id_header)

    logger.info(
        f"[find_all_replies_to_patch] Total replies found: {len(all_replies)} "
        f"for patch_message_id={patch_message_id}"
    )
    return all_replies
