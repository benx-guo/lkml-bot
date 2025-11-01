"""Repository layer to centralize database access.

This improves testability and keeps business logic free from direct ORM calls.
"""

from __future__ import annotations

from typing import Optional, Iterable
from sqlalchemy import select
from .models import Subsystem, EmailMessage


class SubsystemRepository:
    """子系统仓储类，提供子系统的数据访问操作"""

    async def get_or_create(self, session, name: str) -> Subsystem:
        """获取或创建子系统

        Args:
            session: 数据库会话
            name: 子系统名称

        Returns:
            子系统对象
        """
        result = await session.execute(select(Subsystem).where(Subsystem.name == name))
        subsystem = result.scalar_one_or_none()
        if subsystem is None:
            subsystem = Subsystem(name=name, subscribed=True)
            session.add(subsystem)
            await session.flush()
        return subsystem

    async def list_names(self, session) -> list[str]:
        """列出所有子系统名称

        Args:
            session: 数据库会话

        Returns:
            子系统名称列表
        """
        result = await session.execute(select(Subsystem.name))
        return [row[0] for row in result.all()]


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

    async def create(
        self,
        session,
        *,
        subsystem: Subsystem,
        message_id: Optional[str],
        subject: str,
        sender: str,
        sender_email: str,
        content: Optional[str],
        url: Optional[str],
        received_at,
        message_id_header: Optional[str] = None,
        in_reply_to_header: Optional[str] = None,
    ) -> EmailMessage:
        """创建邮件消息

        Args:
            session: 数据库会话
            subsystem: 子系统对象
            message_id: 消息唯一标识
            subject: 邮件主题
            sender: 发送者名称
            sender_email: 发送者邮箱
            content: 邮件内容
            url: 邮件链接
            received_at: 接收时间

        Returns:
            创建的邮件消息对象
        """
        entity = EmailMessage(
            message_id=message_id,
            subject=subject,
            sender=sender,
            sender_email=sender_email,
            content=content,
            url=url,
            subsystem_id=subsystem.id,
            received_at=received_at,
            message_id_header=message_id_header,
            in_reply_to_header=in_reply_to_header,
        )
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


SubsystemRepo = SubsystemRepository()
EmailMessageRepo = EmailMessageRepository()
