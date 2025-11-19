"""PATCH 邮件分类和扫描

提供 PATCH 邮件的扫描、分类和验证功能。
这是 lkml 域的核心功能，不依赖于任何特定的渲染平台。
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from lkml.db.models import EmailMessage
from lkml.feed.patch_parser import parse_patch_subject, PatchInfo

logger = logging.getLogger(__name__)


def scan_recent_patch_emails(session: Session, hours: int) -> List[EmailMessage]:
    """扫描最近的 PATCH 邮件

    Args:
        session: 数据库会话
        hours: 扫描最近多少小时

    Returns:
        PATCH 邮件列表
    """
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)

    emails = (
        session.execute(
            select(EmailMessage)
            .where(
                and_(
                    EmailMessage.received_at >= cutoff_time,
                    EmailMessage.subject.like("%PATCH%"),
                    ~EmailMessage.subject.like("Re:%"),  # 排除回复邮件
                )
            )
            .order_by(EmailMessage.received_at)
        )
        .scalars()
        .all()
    )

    return list(emails)


def categorize_patches(
    emails: List[EmailMessage],
) -> Tuple[
    List[Tuple[EmailMessage, PatchInfo]],
    Dict[str, List[Tuple[EmailMessage, PatchInfo]]],
]:
    """将邮件分类为单个 PATCH 和系列 PATCH

    Args:
        emails: 邮件列表

    Returns:
        (单个 PATCH 列表, 系列 PATCH 字典)
    """
    single_patches = []
    series_groups: Dict[str, List[Tuple[EmailMessage, PatchInfo]]] = {}

    for email in emails:
        patch_info = parse_patch_subject(email.subject)

        # 跳过非 PATCH 邮件
        if not patch_info or not patch_info.is_patch:
            continue

        if patch_info.total is None:
            # 单个 PATCH
            single_patches.append((email, patch_info))
        else:
            # 系列 PATCH
            series_id = _get_series_id(email, patch_info)
            if series_id:
                if series_id not in series_groups:
                    series_groups[series_id] = []
                series_groups[series_id].append((email, patch_info))
            else:
                # 无法确定系列 ID，当作单个 PATCH 处理
                single_patches.append((email, patch_info))

    return single_patches, series_groups


def _get_series_id(email: EmailMessage, patch_info: PatchInfo) -> str | None:
    """获取系列 ID

    Args:
        email: 邮件对象
        patch_info: PATCH 信息

    Returns:
        系列 ID，如果无法确定则返回 None
    """
    if patch_info.is_cover_letter:
        return email.message_id_header
    if email.in_reply_to_header:
        return email.in_reply_to_header
    return None


def validate_cover_letter(
    session: Session, series_id: str
) -> Tuple[EmailMessage, PatchInfo] | None:
    """验证并获取 Cover Letter

    Args:
        session: 数据库会话
        series_id: 系列 ID

    Returns:
        (Cover Letter 邮件, PATCH 信息)，如果无效则返回 None
    """
    cover_letter = session.execute(
        select(EmailMessage).where(EmailMessage.message_id_header == series_id)
    ).scalar_one_or_none()

    if not cover_letter:
        return None

    cover_patch_info = parse_patch_subject(cover_letter.subject)
    if not cover_patch_info or not cover_patch_info.is_patch:
        return None

    # 只处理有 Cover Letter (0/n) 的系列
    if not cover_patch_info.is_cover_letter:
        return None

    return cover_letter, cover_patch_info
