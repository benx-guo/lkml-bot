"""邮件消息仓储类"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import select, or_
from ..models import EmailMessage, Subsystem


@dataclass
class EmailMessageData:  # pylint: disable=too-many-instance-attributes
    """邮件消息数据对象（减少函数参数数量）"""

    subsystem: Subsystem
    message_id: Optional[str]
    subject: str
    sender: str
    sender_email: str
    content: Optional[str]
    url: Optional[str]
    received_at: object
    message_id_header: Optional[str] = None
    in_reply_to_header: Optional[str] = None


class EmailMessageRepository:
    """邮件消息仓储类，提供邮件消息的数据访问操作"""

    async def find_by_message_id(
        self, session, message_id: str
    ) -> Optional[EmailMessage]:
        """根据消息ID查找邮件消息

        Args:
            session: 数据库会话
            message_id: 消息唯一标识

        Returns:
            邮件消息对象，如果不存在则返回 None
        """
        result = await session.execute(
            select(EmailMessage).where(EmailMessage.message_id == message_id)
        )
        return result.scalar_one_or_none()

    async def find_by_message_id_header(
        self, session, message_id_header: str
    ) -> Optional[EmailMessage]:
        """根据 Message-ID Header 查找邮件消息

        Args:
            session: 数据库会话
            message_id_header: Message-ID 头部

        Returns:
            邮件消息对象，如果不存在则返回 None
        """
        result = await session.execute(
            select(EmailMessage).where(
                EmailMessage.message_id_header == message_id_header
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        session,
        *,
        data: EmailMessageData,
    ) -> EmailMessage:
        """创建邮件消息

        Args:
            session: 数据库会话
            data: 邮件消息数据对象

        Returns:
            创建的邮件消息对象
        """
        message_data = {
            "message_id": data.message_id,
            "subject": data.subject,
            "sender": data.sender,
            "sender_email": data.sender_email,
            "content": data.content,
            "url": data.url,
            "subsystem_id": data.subsystem.id,
            "received_at": data.received_at,
            "message_id_header": data.message_id_header,
            "in_reply_to_header": data.in_reply_to_header,
        }
        entity = EmailMessage(**message_data)
        session.add(entity)
        await session.flush()
        return entity

    async def bulk_create(self, session, entities: Iterable[EmailMessage]) -> None:
        """批量创建邮件消息

        Args:
            session: 数据库会话
            entities: 邮件消息对象集合
        """
        session.add_all(list(entities))
        await session.flush()

    async def find_replies_to(
        self, session, message_id_header: str, limit: int = 10
    ) -> list[EmailMessage]:
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
        # 使用 LIKE 查询，匹配包含该 message_id 的所有回复
        # 这样可以处理带尖括号、多个 message_id 等情况
        result = await session.execute(
            select(EmailMessage)
            .where(
                or_(
                    EmailMessage.in_reply_to_header == message_id_header,  # 精确匹配
                    EmailMessage.in_reply_to_header.like(
                        f"%{message_id_header}%"
                    ),  # 模糊匹配
                )
            )
            .order_by(EmailMessage.received_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())


# 单例实例（全局实例，用于方便访问）
EMAIL_MESSAGE_REPO = EmailMessageRepository()
