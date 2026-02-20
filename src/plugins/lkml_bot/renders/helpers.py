"""渲染辅助函数

提供 Discord / Feishu 渲染器共用的内容处理工具函数。
"""

import re
from html.parser import HTMLParser

# 需要跳过的 commit trailer 前缀（纯元数据，非正文内容）
_SKIP_TRAILER_PREFIXES = (
    "Signed-off-by:",
    "Cc:",
    "Link:",
    "Message-Id:",
    "Message-ID:",
    "Fixes:",
    "Co-developed-by:",
)

# diff 相关行前缀
_DIFF_PREFIXES = ("diff --git ", "index ", "--- a/", "+++ b/", "@@ ")


class _HTMLStripper(HTMLParser):
    """HTML 标签剥离器"""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        """收集纯文本内容"""
        self.parts.append(data)

    def get_text(self):
        """返回拼接后的纯文本"""
        return "".join(self.parts)


def strip_html_tags(html: str) -> str:
    """去除 HTML 标签，保留纯文本内容"""
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


def clean_email_content(content: str) -> str:
    """清洗邮件原始内容，提炼出人写的描述部分

    过滤规则（按行）：
    - 去掉引用行（> ...）
    - 去掉 diff / diffstat / 代码 hunk
    - 遇到 "---" 分隔线即停止（后续是 diffstat / diff）
    - 去掉 commit trailer（Signed-off-by 等元数据）
    - 去掉 "On ... wrote:" 邮件引用头
    - 折叠连续空行
    """
    content = strip_html_tags(content)
    lines = content.split("\n")
    cleaned: list[str] = []

    for line in lines:
        stripped = line.strip()

        # "---" 独立行是 patch 正文和 diffstat 的分隔线，后续全是代码
        if stripped == "---":
            break

        # 跳过引用行
        if stripped.startswith(">"):
            continue

        # 跳过 diff 头 / hunk 头
        if stripped.startswith(_DIFF_PREFIXES):
            continue

        # 跳过 diff hunk 内容行（+/- 开头，但不是 "---" 或 "+++" 已处理）
        if re.match(r"^[+-][^+-]", stripped):
            continue

        # 跳过 diffstat 行：  file.c | 10 ++++---
        if re.match(r"^\s*\S+\s+\|\s+\d+", stripped):
            continue

        # 跳过 diffstat 汇总行：  3 files changed, 10 insertions(+)
        if re.match(r"^\s*\d+ files? changed", stripped):
            continue

        # 跳过 commit trailer
        if stripped.startswith(_SKIP_TRAILER_PREFIXES):
            continue

        # 跳过邮件引用头 "On Mon, Jan 28 ... wrote:"
        if re.match(r"^On .+ wrote:\s*$", stripped):
            continue

        cleaned.append(line)

    # 折叠连续空行
    result = "\n".join(cleaned)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def build_author_display(name: str, email: str = "") -> str:
    """构建 Author 显示：Name <email>，相同则只显示一个

    自动处理 lore.kernel.org 常见的 "Name (email)" 格式，
    避免与单独传入的 email 参数产生重复。
    """
    # lore.kernel.org 格式: "Name (email@example.com)" → 拆分
    if " (" in name and name.endswith(")"):
        paren_content = name.rsplit(" (", 1)[1][:-1]
        name = name.rsplit(" (", 1)[0]
        if not email and "@" in paren_content:
            email = paren_content
    if email and email != name:
        return f"{name} <{email}>"
    return name or email or "Unknown"


def build_content_excerpt(
    content: str,
    max_length: int = 200,
    max_lines: int = 4,
    max_line_len: int = 80,
    quote_prefix: str = "> ",
) -> str:
    """清洗内容并构建摘要（引用块格式）

    先清洗噪音，再按行截断 + 总长截断。

    Args:
        content: 原始邮件正文
        max_length: 总字符上限
        max_lines: 最大行数
        max_line_len: 单行字符上限
        quote_prefix: 每行前缀（引用标记）
    """
    text = clean_email_content(content)
    if not text:
        return ""

    raw_lines = text.split("\n")[:max_lines]
    trimmed_lines: list[str] = []
    total = 0

    for line in raw_lines:
        if total >= max_length:
            break
        if len(line) > max_line_len:
            line = line[:max_line_len] + "..."
        remaining = max_length - total
        if len(line) > remaining:
            line = line[:remaining].rsplit(" ", 1)[0] + "..."
        trimmed_lines.append(line)
        total += len(line)

    if not trimmed_lines:
        return ""

    # 内容被截断时追加省略号
    if total >= max_length or len(raw_lines) < len(text.split("\n")):
        last = trimmed_lines[-1]
        if not last.endswith("..."):
            trimmed_lines[-1] = last + "..."

    return "\n".join(f"{quote_prefix}{line}" for line in trimmed_lines)


def build_cc_summary(
    cc_list: list[str], max_show: int = 3, max_total_len: int = 120
) -> str:
    """构建 CC 列表缩略显示

    限制展示数量和总长度，避免 CC 列表过长。
    """
    if not cc_list:
        return ""

    shown: list[str] = []
    total_len = 0

    for addr in cc_list[:max_show]:
        if len(addr) > 40:
            addr = addr[:37] + "..."
        if total_len + len(addr) > max_total_len:
            break
        shown.append(addr)
        total_len += len(addr) + 2  # ", " separator

    if not shown:
        first = cc_list[0]
        shown.append(first[:37] + "..." if len(first) > 40 else first)

    remaining = len(cc_list) - len(shown)
    result = "**CC:** " + ", ".join(shown)
    if remaining > 0:
        result += f" (+{remaining} more)"
    return result
