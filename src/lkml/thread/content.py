"""邮件内容处理模块

提供邮件内容的清理和提取功能。
"""

import re
from html import unescape


def clean_html_content(content: str) -> str:
    """清理 HTML 内容并保留基本格式

    Args:
        content: 原始 HTML 内容

    Returns:
        清理后的内容
    """
    # 尽量保留原始 HTML 结构，只做必要的清理
    cleaned = content.strip()
    # 将 <br>、<br/>、<p> 等转换为换行
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</p>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<p[^>]*>", "", cleaned, flags=re.IGNORECASE)
    # 移除其他 HTML 标签
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    # 解码 HTML 实体
    cleaned = unescape(cleaned)
    # 清理多余的空行（保留最多两个连续换行）
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    # 清理行首尾空白
    lines = [line.strip() for line in cleaned.split("\n")]
    return "\n".join(lines)


def extract_content_preview(email_msg, max_length: int = 500) -> str:
    """提取内容预览

    Args:
        email_msg: EmailMessage 对象
        max_length: 最大预览长度

    Returns:
        内容预览字符串
    """
    if not email_msg or not email_msg.content:
        return ""

    content = clean_html_content(email_msg.content)
    preview = content[:max_length]
    if len(content) > max_length:
        preview += "..."
    return preview
