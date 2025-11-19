"""系列 PATCH 查询和信息构建

提供系列邮件的查询和信息构建功能。
这是 lkml 域的核心功能，不依赖于任何特定的渲染平台。
"""

import logging
from typing import List

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from lkml.db.models import EmailMessage, PatchSubscription
from lkml.feed.patch_parser import parse_patch_subject

logger = logging.getLogger(__name__)


def query_series_emails(session: Session, series_id: str) -> List[EmailMessage]:
    """查询系列的所有邮件

    Args:
        session: 数据库会话
        series_id: 系列 ID

    Returns:
        系列邮件列表
    """
    series_emails_result = session.execute(
        select(EmailMessage)
        .where(
            or_(
                EmailMessage.message_id_header == series_id,
                EmailMessage.in_reply_to_header == series_id,
            )
        )
        .order_by(EmailMessage.received_at)
    )
    return list(series_emails_result.scalars().all())


def build_series_patches_info(
    series_emails: List[EmailMessage],
) -> List[dict]:
    """构建系列 PATCH 信息列表

    Args:
        series_emails: 系列邮件列表

    Returns:
        系列 PATCH 信息列表
    """
    series_patches_info = []
    for email in series_emails:
        email_patch_info = parse_patch_subject(email.subject)
        if (
            email_patch_info
            and email_patch_info.is_patch
            and email_patch_info.index is not None
        ):
            series_patches_info.append(
                {
                    "subject": email.subject,
                    "patch_index": email_patch_info.index,
                    "patch_total": email_patch_info.total,
                    "message_id": email.message_id_header,
                    "url": email.url,
                }
            )

    # 按 patch_index 排序
    series_patches_info.sort(key=lambda x: x["patch_index"])
    return series_patches_info


def check_existing_card(
    session: Session, cover_letter_email
) -> PatchSubscription | None:
    """检查是否已存在 Cover Letter 的订阅卡片

    Args:
        session: 数据库会话
        cover_letter_email: Cover Letter 邮件对象

    Returns:
        已存在的卡片，如果不存在则返回 None
    """
    return session.execute(
        select(PatchSubscription).where(
            PatchSubscription.message_id == cover_letter_email.message_id_header
        )
    ).scalar_one_or_none()
