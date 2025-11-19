"""LKML领域模型"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Subsystem(Base):  # pylint: disable=too-few-public-methods
    """子系统模型

    存储邮件列表子系统的信息，用于管理订阅状态。
    这是 SQLAlchemy ORM 模型，主要作为数据容器，不需要太多公共方法。
    """

    __tablename__ = "subsystems"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    subscribed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # 关系
    email_messages = relationship("EmailMessage", back_populates="subsystem")


class EmailMessage(Base):  # pylint: disable=too-few-public-methods
    """邮件消息模型

    存储从邮件列表抓取的单封邮件信息。
    这是 SQLAlchemy ORM 模型，主要作为数据容器，不需要太多公共方法。
    """

    __tablename__ = "email_messages"

    id = Column(Integer, primary_key=True, index=True)
    subsystem_id = Column(Integer, ForeignKey("subsystems.id"), nullable=False)
    message_id = Column(
        String(500), unique=True, nullable=True, index=True
    )  # 消息唯一标识
    subject = Column(String(500), nullable=False)
    sender = Column(String(200), nullable=False)
    sender_email = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    url = Column(String(1000), nullable=True)  # 消息链接
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # 原始邮件头部关键信息（若可从 feed 获取）
    message_id_header = Column(String(500), nullable=True, index=True)
    in_reply_to_header = Column(String(500), nullable=True, index=True)

    # 关系
    subsystem = relationship("Subsystem", back_populates="email_messages")


class OperationLog(Base):  # pylint: disable=too-few-public-methods
    """操作日志模型

    记录用户操作历史，如订阅、取消订阅、启动/停止监控等。
    这是 SQLAlchemy ORM 模型，主要作为数据容器，不需要太多公共方法。
    """

    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    operator_id = Column(String(100), nullable=False, index=True)
    operator_name = Column(String(200), nullable=False)
    action = Column(
        String(50), nullable=False, index=True
    )  # subscribe, unsubscribe, start_monitor, etc.
    target_name = Column(
        String(200), nullable=False
    )  # 操作目标名称（子系统名称或其他）
    subsystem_name = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class PatchSubscription(Base):  # pylint: disable=too-few-public-methods
    """PATCH 订阅卡片模型

    存储 PATCH 邮件的订阅卡片信息，用于跟踪哪些 PATCH 有人订阅。
    """

    __tablename__ = "patch_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(
        String(500), unique=True, nullable=False, index=True
    )  # PATCH 的 message_id_header
    subsystem_name = Column(String(100), nullable=False, index=True)
    discord_message_id = Column(
        String(100), nullable=False, index=True
    )  # Discord 卡片消息 ID
    discord_channel_id = Column(String(100), nullable=False)  # Discord 频道 ID
    subject = Column(String(500), nullable=False)  # PATCH 主题
    author = Column(String(200), nullable=False)  # PATCH 作者
    url = Column(String(1000), nullable=True)  # PATCH 链接
    is_subscribed = Column(Boolean, default=False, nullable=False)  # 是否有人订阅

    # PATCH 系列信息
    series_message_id = Column(
        String(500), nullable=True, index=True
    )  # 系列 PATCH 的根 message_id（通常是 0/n 的 message_id）
    patch_version = Column(String(20), nullable=True)  # PATCH 版本（如 v5）
    patch_index = Column(Integer, nullable=True)  # PATCH 序号（如 1/4 中的 1）
    patch_total = Column(Integer, nullable=True)  # PATCH 总数（如 1/4 中的 4）

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)  # 过期时间（24小时后）

    # 关系
    discord_thread = relationship(
        "DiscordThread", back_populates="patch_subscription", uselist=False
    )


class DiscordThread(Base):  # pylint: disable=too-few-public-methods
    """Discord Thread 模型

    存储 Discord Thread 的信息，用于将 REPLY 消息发送到对应的 Thread。
    """

    __tablename__ = "discord_threads"

    id = Column(Integer, primary_key=True, index=True)
    patch_subscription_id = Column(
        Integer, ForeignKey("patch_subscriptions.id"), nullable=False, unique=True
    )
    thread_id = Column(
        String(100), unique=True, nullable=False, index=True
    )  # Discord Thread ID
    thread_name = Column(String(500), nullable=False)  # Thread 名称
    is_active = Column(Boolean, default=True, nullable=False)  # Thread 是否活跃
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    archived_at = Column(DateTime, nullable=True)  # Thread 归档时间

    # 关系
    patch_subscription = relationship(
        "PatchSubscription", back_populates="discord_thread"
    )
