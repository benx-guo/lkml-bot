"""Repository 模块

提供数据库访问的仓储层实现。
"""

from .subsystem_repository import SUBSYSTEM_REPO, SubsystemRepository
from .email_message_repository import (
    EMAIL_MESSAGE_REPO,
    EmailMessageData,
    EmailMessageRepository,
)
from .feed_message_repository import (
    FEED_MESSAGE_REPO,
    FeedMessageData,
    FeedMessageRepository,
)

# Repository 导出名称列表（避免与 db/__init__.py 中的重复定义）
_REPO_EXPORT_NAMES = [
    "SubsystemRepository",
    "SUBSYSTEM_REPO",
    "EmailMessageRepository",
    "EmailMessageData",
    "EMAIL_MESSAGE_REPO",
    "FeedMessageRepository",
    "FeedMessageData",
    "FEED_MESSAGE_REPO",
]

__all__ = _REPO_EXPORT_NAMES
