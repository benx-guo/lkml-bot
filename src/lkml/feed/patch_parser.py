"""PATCH 解析器

解析 PATCH 主题，提取版本号、序号、总数等信息。
"""

import re
from typing import Optional
from dataclasses import dataclass


@dataclass
class PatchInfo:
    """PATCH 信息"""

    is_patch: bool = False
    version: Optional[str] = None  # 版本号，如 "v5"
    index: Optional[int] = None  # 序号，如 1
    total: Optional[int] = None  # 总数，如 4
    is_cover_letter: bool = False  # 是否是 0/n 封面信


def parse_patch_subject(subject: str) -> PatchInfo:
    """解析 PATCH 主题

    支持的格式：
    - [PATCH] xxx
    - [PATCH v5] xxx
    - [PATCH 1/4] xxx
    - [PATCH v5 1/4] xxx
    - [RFC PATCH v2 3/5] xxx

    Args:
        subject: 邮件主题

    Returns:
        PatchInfo 对象
    """
    info = PatchInfo()

    # 检查是否是 PATCH
    subject_lower = subject.lower()
    if not ("[patch" in subject_lower or subject_lower.startswith("patch:")):
        return info

    info.is_patch = True

    # 提取方括号内的内容
    # 匹配 [xxx] 格式
    bracket_match = re.search(r"\[(.*?)\]", subject, re.IGNORECASE)
    if not bracket_match:
        return info

    bracket_content = bracket_match.group(1)

    # 提取版本号 (v1, v2, v3, ...)
    version_match = re.search(r"\bv(\d+)\b", bracket_content, re.IGNORECASE)
    if version_match:
        info.version = f"v{version_match.group(1)}"

    # 提取序号/总数 (1/4, 0/5, ...)
    index_total_match = re.search(r"\b(\d+)/(\d+)\b", bracket_content)
    if index_total_match:
        index = int(index_total_match.group(1))
        total = int(index_total_match.group(2))
        info.index = index
        info.total = total
        info.is_cover_letter = index == 0

    return info


def is_patch_series(subject: str) -> bool:
    """判断是否是 PATCH 系列（有序号）

    Args:
        subject: 邮件主题

    Returns:
        是否是系列 PATCH
    """
    info = parse_patch_subject(subject)
    return info.is_patch and info.total is not None


def get_series_identifier(subject: str, version: Optional[str] = None) -> Optional[str]:
    """从主题中提取系列标识符

    用于识别属于同一系列的 PATCH。
    例如：[PATCH v5 1/4] 和 [PATCH v5 2/4] 属于同一系列。

    Args:
        subject: 邮件主题
        version: PATCH 版本（可选）

    Returns:
        系列标识符，如果不是系列 PATCH 则返回 None
    """
    info = parse_patch_subject(subject)

    if not info.is_patch or info.total is None:
        return None

    # 提取主题中方括号后的内容作为基础标识
    bracket_match = re.search(r"\[.*?\]\s*(.+)", subject)
    if not bracket_match:
        return None

    title = bracket_match.group(1).strip()

    # 构建系列标识：版本 + 总数 + 标题前部分
    # 使用标题的前50个字符作为标识
    title_prefix = title[:50]

    version_str = version or info.version or ""
    total_str = str(info.total) if info.total else ""

    series_id = f"{version_str}_{total_str}_{title_prefix}".lower()

    # 移除特殊字符，只保留字母数字和下划线
    series_id = re.sub(r"[^a-z0-9_]", "_", series_id)
    series_id = re.sub(r"_+", "_", series_id)  # 合并连续的下划线

    return series_id


# 测试函数
def test_parse_patch_subject():
    """测试 PATCH 解析"""
    test_cases = [
        ("[PATCH] Fix bug", PatchInfo(is_patch=True)),
        ("[PATCH v5] Add feature", PatchInfo(is_patch=True, version="v5")),
        ("[PATCH 1/4] Part 1", PatchInfo(is_patch=True, index=1, total=4)),
        (
            "[PATCH v5 0/4] Cover letter",
            PatchInfo(
                is_patch=True, version="v5", index=0, total=4, is_cover_letter=True
            ),
        ),
        (
            "[RFC PATCH v2 3/5] Proposal",
            PatchInfo(is_patch=True, version="v2", index=3, total=5),
        ),
        ("Not a patch", PatchInfo(is_patch=False)),
    ]

    for subject, expected in test_cases:
        result = parse_patch_subject(subject)
        print(f"Subject: {subject}")
        print(f"  Result: {result}")
        print(f"  Expected: {expected}")
        print()


if __name__ == "__main__":
    test_parse_patch_subject()
