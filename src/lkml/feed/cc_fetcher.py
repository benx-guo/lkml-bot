"""CC 列表抓取模块

从 lore.kernel.org 抓取邮件的 To 和 CC 列表。
"""

import html as html_module
import logging
import re
from typing import List, Optional
import httpx

logger = logging.getLogger(__name__)


def _extract_emails_from_text(text: str) -> List[str]:
    """从文本中提取邮箱地址

    Args:
        text: 包含邮箱地址的文本

    Returns:
        邮箱地址列表
    """
    if not text:
        return []
    # 提取邮箱地址，支持格式：name <email@domain.com>, email@domain.com
    email_pattern = r"[\w\.-]+@[\w\.-]+\.\w+"
    emails = re.findall(email_pattern, text)
    return list(set(emails))  # 去重


def _clean_html_text(text: str) -> str:
    """清理 HTML 文本，移除标签和多余空白

    Args:
        text: 包含 HTML 的文本

    Returns:
        清理后的文本
    """
    if not text:
        return ""

    # 先保留形如 <email@domain> 的邮箱，避免被当成 HTML 标签移除
    email_in_brackets = r"<([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})>"
    text = re.sub(email_in_brackets, r"\1", text)

    # 移除 HTML 标签（保留标签内部文本）
    text = re.sub(r"</?\w+[^>]*>", " ", text)
    # 清理空白字符
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_field_from_pre(pre_content: str, field_name: str) -> List[str]:
    """从 <pre> 标签内容中提取指定字段的邮箱

    Args:
        pre_content: <pre> 标签的内容
        field_name: 字段名（如 "To" 或 "Cc"）

    Returns:
        邮箱地址列表
    """
    # 匹配字段后面到下一个字段之间的内容
    pattern = rf"^{field_name}:\s*(.*?)(?=\n(?:Cc:|To:|Subject:|Date:))"
    match = re.search(pattern, pre_content, re.IGNORECASE | re.MULTILINE | re.DOTALL)
    if not match:
        return []

    field_text = match.group(1)
    field_text = _clean_html_text(field_text)
    emails = _extract_emails_from_text(field_text)
    if emails:
        logger.debug(f"Found {len(emails)} {field_name} addresses: {emails[:3]}...")
    return emails


def _extract_emails_from_table_format(html_content: str, field_name: str) -> List[str]:
    """从表格格式 HTML 中提取指定字段的邮箱

    Args:
        html_content: HTML 内容
        field_name: 字段名（如 "To" 或 "CC"）

    Returns:
        邮箱地址列表
    """
    patterns = [
        rf"<th[^>]*>{field_name}:?</th>\s*<td[^>]*>([^<]+(?:<[^>]+>[^<]+)*)</td>",
        rf"<dt[^>]*>{field_name}:?</dt>\s*<dd[^>]*>([^<]+(?:<[^>]+>[^<]+)*)</dd>",
        rf"<tr[^>]*>\s*<th[^>]*>{field_name}:?</th>\s*<td[^>]*>([^<]+(?:<[^>]+>[^<]+)*)</td>\s*</tr>",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
        if matches:
            field_text = matches[0]
            field_text = _clean_html_text(field_text)
            emails = _extract_emails_from_text(field_text)
            if emails:
                logger.debug(
                    f"Found {len(emails)} {field_name} addresses: {emails[:3]}..."
                )
                return emails
    return []


async def _fetch_html_content(url: str) -> Optional[str]:
    """获取 HTML 内容

    Args:
        url: 要获取的 URL

    Returns:
        HTML 内容，如果失败则返回 None
    """
    base_url = url.rstrip("/")
    if not base_url.endswith("/"):
        base_url += "/"

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(base_url)

        if response.status_code != 200:
            logger.warning(
                f"Failed to fetch HTML page from {url} (status {response.status_code})"
            )
            return None

        html_content = response.text
        if not html_content:
            logger.warning(f"Empty HTML content from {url}")
            return None

        return html_content


async def fetch_cc_list_from_url(url: str) -> Optional[List[str]]:
    """从 lore.kernel.org URL 抓取 To 和 CC 列表

    直接从 HTML 页面提取 To 和 CC 信息，合并后返回。

    Args:
        url: lore.kernel.org 邮件 URL，例如：
            https://lore.kernel.org/rust-for-linux/20231224123456.12345-1-example@example.com/

    Returns:
        To 和 CC 邮箱列表（合并去重），如果抓取失败则返回 None
    """
    if not url:
        return None

    try:
        html_content = await _fetch_html_content(url)
        if not html_content:
            return None

        all_emails = []

        # 首先尝试从 <pre id=b> 标签提取
        pre_pattern = r'<pre[^>]*id\s*=\s*["\']?b["\']?[^>]*>(.*?)</pre>'
        pre_matches = re.findall(pre_pattern, html_content, re.IGNORECASE | re.DOTALL)

        if pre_matches:
            pre_content = html_module.unescape(pre_matches[0])
            to_emails = _extract_field_from_pre(pre_content, "To")
            cc_emails = _extract_field_from_pre(pre_content, "Cc")
            all_emails.extend(to_emails)
            all_emails.extend(cc_emails)

        # 如果 <pre id=b> 方式没找到，尝试旧的表格格式（向后兼容）
        if not all_emails:
            to_emails = _extract_emails_from_table_format(html_content, "To")
            cc_emails = _extract_emails_from_table_format(html_content, "CC")
            all_emails.extend(to_emails)
            all_emails.extend(cc_emails)

        # 合并并去重返回
        result = list(set(all_emails)) if all_emails else []
        if result:
            logger.info(
                f"Extracted {len(result)} email addresses (To+CC) from {url}: {result[:5]}..."
            )
            return result
        logger.debug(f"No To/CC addresses found in HTML page from {url}")
        return None

    except httpx.HTTPError as e:
        logger.warning(f"Failed to fetch To/CC list from {url}: {e}")
        return None
    except (ValueError, KeyError, AttributeError, re.error) as e:
        logger.error(f"Error parsing To/CC list from {url}: {e}", exc_info=True)
        return None
