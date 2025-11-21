"""Feed 消息仓储类"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Iterable

from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from ..models import FeedMessage

logger = logging.getLogger(__name__)


@dataclass
class FeedMessageData:
    """Feed 消息数据对象"""

    subsystem_id: int
    message_id_header: str
    subject: str
    author: str
    author_email: str
    message_id: Optional[str] = None
    in_reply_to_header: Optional[str] = None
    content: Optional[str] = None
    url: Optional[str] = None
    received_at: Optional[object] = None
    is_patch: bool = False
    is_reply: bool = False
    is_series_patch: bool = False
    patch_version: Optional[str] = None
    patch_index: Optional[int] = None
    patch_total: Optional[int] = None
    is_cover_letter: bool = False
    series_message_id: Optional[str] = None


class FeedMessageRepository:
    """Feed 消息仓储类，提供 Feed 消息的数据访问操作"""

    async def find_by_message_id_header(
        self, session, message_id_header: str
    ) -> Optional[FeedMessage]:
        """根据 Message-ID Header 查找 Feed 消息

        Args:
            session: 数据库会话
            message_id_header: Message-ID 头部

        Returns:
            Feed 消息对象，如果不存在则返回 None
        """
        result = await session.execute(
            select(FeedMessage).where(
                FeedMessage.message_id_header == message_id_header
            )
        )
        return result.scalar_one_or_none()

    async def find_by_message_id(
        self, session, message_id: str
    ) -> Optional[FeedMessage]:
        """根据消息ID查找 Feed 消息

        Args:
            session: 数据库会话
            message_id: 消息唯一标识

        Returns:
            Feed 消息对象，如果不存在则返回 None
        """
        result = await session.execute(
            select(FeedMessage).where(FeedMessage.message_id == message_id)
        )
        return result.scalar_one_or_none()

    async def find_by_email_message_id(
        self, session, email_message_id: int
    ) -> Optional[FeedMessage]:
        """根据 EmailMessage ID 查找 Feed 消息（已废弃，保留兼容性）

        Args:
            session: 数据库会话
            email_message_id: EmailMessage ID

        Returns:
            Feed 消息对象，如果不存在则返回 None
        """
        # 这个方法已废弃，因为 FeedMessage 不再关联 EmailMessage
        return None

    async def create(
        self,
        session,
        *,
        data: FeedMessageData,
    ) -> FeedMessage:
        """创建 Feed 消息

        Args:
            session: 数据库会话
            data: Feed 消息数据对象

        Returns:
            创建的 Feed 消息对象
        """
        feed_message_data = {
            "subsystem_id": data.subsystem_id,
            "message_id": data.message_id,
            "message_id_header": data.message_id_header,
            "in_reply_to_header": data.in_reply_to_header,
            "subject": data.subject,
            "author": data.author,
            "author_email": data.author_email,
            "content": data.content,
            "url": data.url,
            "received_at": data.received_at,
            "is_patch": data.is_patch,
            "is_reply": data.is_reply,
            "is_series_patch": data.is_series_patch,
            "patch_version": data.patch_version,
            "patch_index": data.patch_index,
            "patch_total": data.patch_total,
            "is_cover_letter": data.is_cover_letter,
            "series_message_id": data.series_message_id,
        }
        entity = FeedMessage(**feed_message_data)
        session.add(entity)
        await session.flush()
        return entity

    async def create_or_update(
        self,
        session,
        *,
        data: FeedMessageData,
    ) -> FeedMessage:
        """创建或更新 Feed 消息

        Args:
            session: 数据库会话
            data: Feed 消息数据对象

        Returns:
            创建或更新的 Feed 消息对象
        """
        existing = await self.find_by_message_id_header(session, data.message_id_header)
        if existing:
            # 更新现有记录
            existing.subsystem_id = data.subsystem_id
            existing.message_id = data.message_id
            existing.in_reply_to_header = data.in_reply_to_header
            existing.subject = data.subject
            existing.author = data.author
            existing.author_email = data.author_email
            existing.content = data.content
            existing.url = data.url
            if data.received_at:
                existing.received_at = data.received_at
            existing.is_patch = data.is_patch
            existing.is_reply = data.is_reply
            existing.is_series_patch = data.is_series_patch
            existing.patch_version = data.patch_version
            existing.patch_index = data.patch_index
            existing.patch_total = data.patch_total
            existing.is_cover_letter = data.is_cover_letter
            existing.series_message_id = data.series_message_id
            await session.flush()
            return existing

        # 创建新记录
        # 在并发情况下，可能多个请求同时检查记录不存在，然后都尝试插入
        # 捕获 IntegrityError 并重试查询
        try:
            return await self.create(session, data=data)
        except IntegrityError as e:
            # 如果是 UNIQUE 约束错误，说明记录在检查后、插入前被其他请求创建了
            # 重新查询并返回现有记录
            if "UNIQUE constraint failed" in str(e) and "message_id_header" in str(e):
                logger.debug(
                    f"Concurrent insert detected for message_id_header={data.message_id_header}, "
                    f"retrying query"
                )
                existing = await self.find_by_message_id_header(
                    session, data.message_id_header
                )
                if existing:
                    # 更新现有记录（可能其他请求只创建了部分数据）
                    existing.subsystem_id = data.subsystem_id
                    existing.message_id = data.message_id
                    existing.in_reply_to_header = data.in_reply_to_header
                    existing.subject = data.subject
                    existing.author = data.author
                    existing.author_email = data.author_email
                    existing.content = data.content
                    existing.url = data.url
                    if data.received_at:
                        existing.received_at = data.received_at
                    existing.is_patch = data.is_patch
                    existing.is_reply = data.is_reply
                    existing.is_series_patch = data.is_series_patch
                    existing.patch_version = data.patch_version
                    existing.patch_index = data.patch_index
                    existing.patch_total = data.patch_total
                    existing.is_cover_letter = data.is_cover_letter
                    existing.series_message_id = data.series_message_id
                    await session.flush()
                    return existing
            # 如果是其他 IntegrityError，重新抛出
            raise

    async def find_replies_to(
        self, session, message_id_header: str, limit: int = 10
    ) -> list[FeedMessage]:
        """查找回复某个消息的所有 REPLY

        使用 LIKE 查询，因为 in_reply_to_header 可能包含：
        - 尖括号：<message_id>
        - 多个 message_id（邮件头可能包含多个 In-Reply-To）

        Args:
            session: 数据库会话
            message_id_header: 被回复的消息 ID
            limit: 最多返回的 REPLY 数量

        Returns:
            REPLY 消息列表，按时间正序排序（最早的在前）
        """
        result = await session.execute(
            select(FeedMessage)
            .where(
                or_(
                    FeedMessage.in_reply_to_header == message_id_header,  # 精确匹配
                    FeedMessage.in_reply_to_header.like(
                        f"%{message_id_header}%"
                    ),  # 模糊匹配
                )
            )
            .order_by(FeedMessage.received_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())


# 单例实例（全局实例，用于方便访问）
FEED_MESSAGE_REPO = FeedMessageRepository()
