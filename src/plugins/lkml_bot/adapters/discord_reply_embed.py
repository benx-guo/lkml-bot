"""Discord REPLY Embed 构建辅助函数"""

import re
from html import unescape


def clean_subject(subject: str) -> str:
    """清理 subject（去除 Re: 前缀和 [PATCH] 标签）

    Args:
        subject: 原始 subject

    Returns:
        清理后的 subject
    """
    cleaned = re.sub(r"^Re:\s*", "", subject, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\[PATCH[^\]]*\]\s*", "", cleaned)
    return cleaned


def format_date(email_msg) -> str:
    """格式化日期

    Args:
        email_msg: EmailMessage 对象

    Returns:
        格式化后的日期字符串
    """
    if email_msg and email_msg.received_at:
        return email_msg.received_at.strftime("%b %d, %Y at %H:%M UTC")
    return "Unknown"


def extract_content(entry, email_msg) -> str | None:
    """提取邮件正文内容

    Args:
        entry: Feed 条目
        email_msg: EmailMessage 对象

    Returns:
        邮件正文内容，如果不存在则返回 None
    """
    if email_msg and email_msg.content:
        return email_msg.content

    if hasattr(entry, "content") and entry.content:
        if hasattr(entry.content, "summary"):
            return entry.content.summary

    if hasattr(entry, "summary"):
        return entry.summary

    return None


def clean_content(content: str) -> str:
    """清理 HTML 内容并提取纯文本

    Args:
        content: 原始内容

    Returns:
        清理后的内容
    """
    cleaned = content.strip()
    # 移除 HTML 标签
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    # 解码 HTML 实体
    cleaned = unescape(cleaned)
    # 移除多余的空行
    cleaned = re.sub(r"\n\s*\n\s*\n", "\n\n", cleaned)
    return cleaned


def build_description(entry, date_str: str) -> str:
    """构建描述

    Args:
        entry: Feed 条目
        date_str: 日期字符串

    Returns:
        描述字符串
    """
    description_parts = [
        f"**From:** {entry.author}",
        f"**Date:** {date_str}",
    ]
    return "\n".join(description_parts)


def build_content_fields(content_clean: str, entry_url: str) -> list:
    """构建内容字段

    Args:
        content_clean: 清理后的内容
        entry_url: 条目 URL

    Returns:
        字段列表
    """
    fields = []

    if not content_clean:
        return fields

    preview = content_clean[:1000].strip()  # 最多1000字符
    if not preview:
        return fields

    # 格式化预览内容
    lines = preview.split("\n")
    formatted_lines = ["```"]
    for line in lines[:15]:  # 最多15行
        if line.strip():
            line_text = line[:75] + ("..." if len(line) > 75 else "")
            formatted_lines.append(line_text)
    formatted_lines.append("```")
    content_preview = "\n".join(formatted_lines)

    fields.append(
        {
            "name": "💬 Reply Content",
            "value": content_preview[:1024],
            "inline": False,
        }
    )

    if len(content_clean) > 1000:
        fields.append(
            {
                "name": "📖 Full Content",
                "value": f"[Read Full Reply →]({entry_url})",
                "inline": False,
            }
        )

    return fields


def build_reply_embed(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    entry, in_reply_to: str, email_msg, subject: str, description: str, fields: list
) -> dict:
    """构建 REPLY Embed

    Args:
        entry: Feed 条目
        in_reply_to: 回复的 message_id
        email_msg: EmailMessage 对象
        subject: 清理后的 subject
        description: 描述字符串
        fields: 字段列表

    Returns:
        Discord Embed 字典
    """
    # 添加提示字段
    fields.append(
        {
            "name": "💡 Tip",
            "value": "Click the title to view this reply on lore.kernel.org",
            "inline": False,
        }
    )

    embed = {
        "title": f"🆕 💬 **{subject[:100]}**",
        "description": description,
        "fields": fields,
        "color": 0xFF5733,  # 鲜艳的橙红色表示新回复
        "footer": {
            "text": f"🆕 New Reply • In-Reply-To: {in_reply_to[:45]}...",
        },
        "url": entry.url,
    }

    if email_msg and email_msg.received_at:
        embed["timestamp"] = email_msg.received_at.isoformat()

    return embed
