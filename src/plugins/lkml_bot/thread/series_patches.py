"""系列 PATCH 发送到 Thread 的辅助函数

负责将 PATCH 内容渲染为 Discord Thread 消息格式。
邮件内容处理和回复层级构建由 lkml.thread 模块提供。
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from nonebot.log import logger

from lkml.db.repo.email_message_repository import EMAIL_MESSAGE_REPO
from lkml.service.thread_content_service import thread_content_service
from lkml.feed.patch_parser import parse_patch_subject

from .discord_api import truncate_description


def build_yaml_info(patch, patch_info) -> str:
    """构建 YAML 格式的信息

    Args:
        patch: PATCH 订阅对象
        patch_info: PATCH 信息对象

    Returns:
        YAML 格式的字符串
    """
    # 如果是系列 PATCH 的子 PATCH（不是 cover letter），只显示 Message ID
    if (
        patch_info.is_patch
        and patch_info.total is not None
        and not patch_info.is_cover_letter
    ):
        return "```yaml\n" + f"Message ID: {patch.message_id}\n" + "```"

    # 如果是 Cover Letter，只显示 Message ID 和 Cover Letter 标识
    if (
        patch_info.is_patch
        and patch_info.total is not None
        and patch_info.is_cover_letter
    ):
        return (
            "```yaml\n"
            + f"Message ID: {patch.message_id}\n"
            + f"Cover Letter: 0/{patch_info.total}\n"
            + "```"
        )

    # 单个 PATCH 也只显示 Message ID
    return "```yaml\n" + f"Message ID: {patch.message_id}\n" + "```"


def build_description(
    yaml_content: str, content_preview: str, reply_fields: Optional[list] = None
) -> str:
    """构建描述

    Args:
        yaml_content: YAML 格式的内容
        content_preview: 内容预览
        reply_fields: 回复字段列表（可选）

    Returns:
        描述字符串
    """
    description_parts = [yaml_content]

    # 如果有回复，先显示回复部分（在 Content Preview 之前）
    if reply_fields:
        # 从 reply_fields 中提取回复内容
        for field in reply_fields:
            if field.get("name") == "Replies":
                description_parts.extend(
                    [
                        "",
                        f"**{field['name']}**",
                        field["value"],
                    ]
                )
                break

    if content_preview:
        description_parts.extend(
            [
                "",
                "**Content Preview:**",
                f"```\n{content_preview}\n```",
            ]
        )

    description = "\n".join(description_parts)
    return truncate_description(description)


def _format_single_reply(reply, level: int, new_indicator: str) -> str:
    """格式化单个回复行

    Args:
        reply: 回复对象
        level: 层级深度
        new_indicator: 新回复指示器（放在作者名字后面，不破坏缩进）

    Returns:
        格式化后的回复行
    """
    reply_author = thread_content_service.format_reply_author(reply)
    indent = ""
    prefix = "\u00a0\u00a0\u00a0\u00a0" * level + "\\` "

    if reply.url:
        author_link = f"[{reply_author}]({reply.url})"
        # new_indicator 放在作者名字后面，保持缩进不变
        return f"{indent}{prefix}**{author_link}**{new_indicator}"

    # new_indicator 放在作者名字后面，保持缩进不变
    return f"{indent}{prefix}**{reply_author}**{new_indicator}"


def format_reply_with_hierarchy(
    reply, reply_map: dict, level: int = 0, new_indicator: str = ""
) -> list:
    """格式化回复及其子回复

    Args:
        reply: 回复对象
        reply_map: 回复映射字典
        level: 层级深度
        new_indicator: 新回复指示器

    Returns:
        格式化后的回复行列表
    """
    lines = [_format_single_reply(reply, level, new_indicator)]

    # 递归处理子回复
    message_id = reply.message_id_header
    if message_id in reply_map:
        for child_id in reply_map[message_id]["children"]:
            if child_id in reply_map:
                child_reply = reply_map[child_id]["reply"]
                child_lines = format_reply_with_hierarchy(
                    child_reply, reply_map, level + 1, new_indicator
                )
                lines.extend(child_lines)

    return lines


def _calculate_remaining_replies(
    patch_replies: list, root_replies: list, reply_map: dict, max_display: int
) -> int:
    """计算剩余回复数量

    Args:
        patch_replies: 所有回复列表
        root_replies: 根回复 ID 列表
        reply_map: 回复映射字典
        max_display: 最大显示数量

    Returns:
        剩余回复数量
    """
    if len(root_replies) <= max_display:
        return 0

    displayed_count = sum(
        len(reply_map[rid]["children"]) + 1 for rid in root_replies[:max_display]
    )
    return len(patch_replies) - displayed_count


async def build_reply_lines(
    session, patch_replies: list, patch_message_id: str
) -> list:
    """构建回复行列表（带层级关系）

    Args:
        session: 数据库会话
        patch_replies: 回复列表
        patch_message_id: PATCH 的 message_id

    Returns:
        回复行列表
    """
    if not patch_replies:
        return []

    reply_lines = [f"**{len(patch_replies)} Replies:**"]

    # 构建层级关系
    hierarchy = await thread_content_service.build_reply_hierarchy(
        session, patch_replies, patch_message_id
    )
    reply_map = hierarchy["reply_map"]
    root_replies = hierarchy["root_replies"]

    # 计算多久算"新"REPLY（24小时内）
    new_threshold = datetime.utcnow() - timedelta(hours=24)

    # 显示所有根回复及其子回复
    for root_id in root_replies:
        if root_id in reply_map:
            reply = reply_map[root_id]["reply"]
            new_indicator = (
                "🆕 "
                if thread_content_service.is_new_reply(reply, new_threshold)
                else ""
            )
            formatted_lines = format_reply_with_hierarchy(
                reply, reply_map, level=0, new_indicator=new_indicator
            )
            reply_lines.extend(formatted_lines)

    return reply_lines


async def build_reply_fields(
    session, patch_replies: list, patch_message_id: str
) -> Optional[list]:
    """构建回复字段（带层级关系）

    Args:
        session: 数据库会话
        patch_replies: 回复列表
        patch_message_id: PATCH 的 message_id

    Returns:
        字段列表，如果没有回复则返回 None
    """
    if not patch_replies:
        return None

    reply_lines = await build_reply_lines(session, patch_replies, patch_message_id)

    return [
        {
            "name": "Replies",
            "value": "\n".join(reply_lines),
            "inline": False,
        }
    ]


def build_patch_embed(
    patch, _patch_info, description: str, fields: Optional[list]
) -> dict:
    """构建 PATCH Embed

    Args:
        patch: PATCH 订阅对象
        _patch_info: PATCH 信息对象（未使用，保留用于未来扩展）
        description: 描述字符串
        fields: 字段列表

    Returns:
        Discord Embed 字典
    """
    title = f"📨 {patch.subject[:200]}"
    embed = {
        "title": title,
        "description": description,
        "color": 0x00D166 if patch.patch_index == 0 else 0x5865F2,
        "footer": {
            "text": f"💬 Replies to this patch will appear below • {patch.message_id[:50]}...",
        },
    }

    if patch.url:
        embed["url"] = patch.url

    if fields:
        embed["fields"] = fields

    return embed


async def process_and_send_patch(
    session, thread_id: str, patch, send_func
) -> None:  # pylint: disable=too-many-locals
    """处理并发送单个 PATCH

    Args:
        session: 数据库会话
        thread_id: Thread ID
        patch: PATCH 订阅对象
        send_func: 发送函数
    """
    logger.info(
        f"[process_and_send_patch] Processing PATCH: message_id={patch.message_id}, "
        f"patch_index={patch.patch_index}, subject={patch.subject[:50]}"
    )

    # 查询 EmailMessage 获取完整信息
    email_msg = await EMAIL_MESSAGE_REPO.find_by_message_id_header(
        session, patch.message_id
    )

    if not email_msg:
        logger.warning(
            f"[process_and_send_patch] EmailMessage not found for message_id={patch.message_id}"
        )

    # 提取内容预览
    content_preview = thread_content_service.extract_content_preview(email_msg)

    # 构建 YAML 信息
    patch_info = parse_patch_subject(patch.subject)
    yaml_content = build_yaml_info(patch, patch_info)

    # 查询该 PATCH 的所有回复（包括直接回复和间接回复）
    logger.info(
        f"[process_and_send_patch] Searching for replies to message_id={patch.message_id}"
    )
    patch_replies = await thread_content_service.find_all_replies_to_patch(
        session, patch.message_id
    )

    logger.info(
        f"[process_and_send_patch] Found {len(patch_replies)} total replies for PATCH "
        f"{patch.message_id} (patch_index={patch.patch_index})"
    )

    # 打印所有找到的回复的详细信息
    for i, reply in enumerate(patch_replies):
        logger.info(
            f"[process_and_send_patch] Reply {i+1}/{len(patch_replies)}: "
            f"message_id_header={reply.message_id_header}, "
            f"in_reply_to_header={reply.in_reply_to_header}, "
            f"subject={reply.subject[:50]}"
        )

    # 如果是子 PATCH（不是 cover letter），需要过滤回复
    # 只保留那些实际回复这个子 PATCH 的回复（通过 in_reply_to 链判断）
    if patch.patch_index is not None and patch.patch_index != 0:
        logger.info(
            f"[process_and_send_patch] Filtering replies for sub-PATCH "
            f"(patch_index={patch.patch_index})"
        )
        filtered_replies = []
        for reply in patch_replies:
            # 如果回复直接回复这个子 PATCH，直接接受
            if reply.in_reply_to_header == patch.message_id:
                logger.info(
                    f"[process_and_send_patch] Reply {reply.message_id_header} directly "
                    f"replies to PATCH {patch.message_id}"
                )
                filtered_replies.append(reply)
                continue

            # 检查 in_reply_to_header 是否包含 patch.message_id（处理带尖括号等情况）
            if (
                reply.in_reply_to_header
                and patch.message_id in reply.in_reply_to_header
            ):
                logger.info(
                    f"[process_and_send_patch] Reply {reply.message_id_header} "
                    f"in_reply_to_header contains PATCH message_id: "
                    f"in_reply_to={reply.in_reply_to_header}, "
                    f"patch.message_id={patch.message_id}"
                )
                filtered_replies.append(reply)
                continue

            # 如果回复的 in_reply_to 指向其他消息，通过查找 in_reply_to 链来判断
            # 是否最终指向这个子 PATCH
            if reply.in_reply_to_header:
                actual_patch = await thread_content_service.find_actual_patch_for_reply(
                    session, reply.in_reply_to_header
                )
                if actual_patch and actual_patch.message_id == patch.message_id:
                    logger.info(
                        f"[process_and_send_patch] Reply {reply.message_id_header} "
                        f"indirectly replies to PATCH {patch.message_id} via chain"
                    )
                    filtered_replies.append(reply)
                else:
                    logger.info(
                        f"[process_and_send_patch] Reply {reply.message_id_header} "
                        f"(in_reply_to={reply.in_reply_to_header}) does not target "
                        f"PATCH {patch.message_id}"
                    )
        patch_replies = filtered_replies
        logger.info(
            f"[process_and_send_patch] Filtered to {len(patch_replies)} replies for "
            f"sub-PATCH {patch.message_id}"
        )
    else:
        logger.info(
            f"[process_and_send_patch] Not filtering replies (patch_index={patch.patch_index}), "
            f"using all {len(patch_replies)} replies"
        )

    # 构建回复字段（带层级关系）
    fields = await build_reply_fields(session, patch_replies, patch.message_id)

    # 构建描述（将回复部分包含在描述中，放在 Content Preview 之前）
    description = build_description(yaml_content, content_preview, fields)

    # Thread 内只发送内容，不发送卡片格式
    # 直接发送 description 作为纯文本内容
    await send_func(thread_id, description)

    # 添加延迟以避免速率限制
    await asyncio.sleep(0.5)
