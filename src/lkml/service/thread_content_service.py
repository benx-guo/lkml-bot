"""Thread 内容服务

封装 Thread 相关的业务逻辑，包括内容处理、回复层级构建、PATCH 分类等。
这些功能原本在 lkml.thread 模块中，现在通过 service 层对外暴露。
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..db.models import EmailMessage, PatchSubscription
from ..feed.patch_parser import PatchInfo
from ..thread import content as thread_content
from ..thread import patch_categorizer as thread_patch_categorizer
from ..thread import reply as thread_reply
from ..thread import series_queries as thread_series_queries
from ..thread import subscription_helpers as thread_subscription_helpers

logger = logging.getLogger(__name__)


class ThreadContentService:
    """Thread 内容服务类"""

    # ========== 内容处理相关 ==========

    def clean_html_content(self, content: str) -> str:
        """清理 HTML 内容并保留基本格式

        Args:
            content: 原始 HTML 内容

        Returns:
            清理后的内容
        """
        return thread_content.clean_html_content(content)

    def extract_content_preview(self, email_msg, max_length: int = 500) -> str:
        """提取内容预览

        Args:
            email_msg: EmailMessage 对象
            max_length: 最大预览长度

        Returns:
            内容预览字符串
        """
        return thread_content.extract_content_preview(email_msg, max_length)

    # ========== 回复处理相关 ==========

    def format_reply_author(self, reply) -> str:
        """格式化回复作者

        Args:
            reply: EmailMessage 对象

        Returns:
            格式化后的作者字符串
        """
        return thread_reply.format_reply_author(reply)

    def format_reply_subject(self, reply) -> str:
        """格式化回复主题

        Args:
            reply: EmailMessage 对象

        Returns:
            格式化后的主题字符串
        """
        return thread_reply.format_reply_subject(reply)

    def is_new_reply(self, reply, new_threshold: datetime) -> bool:
        """检查是否是新的回复

        Args:
            reply: EmailMessage 对象
            new_threshold: 新回复的时间阈值

        Returns:
            如果是新回复返回 True，否则返回 False
        """
        return thread_reply.is_new_reply(reply, new_threshold)

    def parse_reply_time(self, reply) -> Optional[datetime]:
        """解析回复时间

        Args:
            reply: EmailMessage 对象

        Returns:
            datetime 对象，如果解析失败则返回 None
        """
        return thread_reply.parse_reply_time(reply)

    async def build_reply_hierarchy(
        self, session, patch_replies: list, patch_message_id: str
    ) -> dict:
        """构建回复层级关系

        Args:
            session: 数据库会话
            patch_replies: 回复列表（应该已经按时间正序排序）
            patch_message_id: PATCH 的 message_id

        Returns:
            层级字典：{message_id: {'reply': reply, 'children': [...]}}
        """
        return await thread_reply.build_reply_hierarchy(
            session, patch_replies, patch_message_id
        )

    async def find_actual_patch_for_reply(
        self, session, in_reply_to: str, max_depth: int = 5
    ) -> Optional[PatchSubscription]:
        """查找回复实际对应的 PATCH

        Args:
            session: 数据库会话
            in_reply_to: 回复的 message_id
            max_depth: 最大递归深度

        Returns:
            PATCH 订阅对象，如果不存在则返回 None
        """
        return await thread_reply.find_actual_patch_for_reply(
            session, in_reply_to, max_depth
        )

    async def find_all_replies_to_patch(
        self, session, patch_message_id: str, max_depth: int = 10
    ) -> list:
        """查找 PATCH 的所有回复（包括直接回复和间接回复）

        Args:
            session: 数据库会话
            patch_message_id: PATCH 的 message_id
            max_depth: 最大递归深度

        Returns:
            所有回复列表
        """
        return await thread_reply.find_all_replies_to_patch(
            session, patch_message_id, max_depth
        )

    # ========== PATCH 分类相关 ==========

    def scan_recent_patch_emails(
        self, session: Session, hours: int
    ) -> List[EmailMessage]:
        """扫描最近的 PATCH 邮件

        Args:
            session: 数据库会话
            hours: 扫描最近多少小时

        Returns:
            PATCH 邮件列表
        """
        return thread_patch_categorizer.scan_recent_patch_emails(session, hours)

    def categorize_patches(self, emails: List[EmailMessage]) -> Tuple[
        List[Tuple[EmailMessage, PatchInfo]],
        Dict[str, List[Tuple[EmailMessage, PatchInfo]]],
    ]:
        """将邮件分类为单个 PATCH 和系列 PATCH

        Args:
            emails: 邮件列表

        Returns:
            (单个 PATCH 列表, 系列 PATCH 字典)
        """
        return thread_patch_categorizer.categorize_patches(emails)

    def validate_cover_letter(
        self, session: Session, series_id: str
    ) -> Tuple[EmailMessage, PatchInfo] | None:
        """验证并获取 Cover Letter

        Args:
            session: 数据库会话
            series_id: 系列 ID

        Returns:
            (Cover Letter 邮件, PATCH 信息)，如果无效则返回 None
        """
        return thread_patch_categorizer.validate_cover_letter(session, series_id)

    # ========== 系列查询相关 ==========

    def query_series_emails(
        self, session: Session, series_id: str
    ) -> List[EmailMessage]:
        """查询系列的所有邮件

        Args:
            session: 数据库会话
            series_id: 系列 ID

        Returns:
            系列邮件列表
        """
        return thread_series_queries.query_series_emails(session, series_id)

    def build_series_patches_info(
        self, series_emails: List[EmailMessage]
    ) -> List[dict]:
        """构建系列 PATCH 信息列表

        Args:
            series_emails: 系列邮件列表

        Returns:
            系列 PATCH 信息列表
        """
        return thread_series_queries.build_series_patches_info(series_emails)

    def check_existing_card(
        self, session: Session, cover_letter_email
    ) -> Optional[PatchSubscription]:
        """检查是否已存在 Cover Letter 的订阅卡片

        Args:
            session: 数据库会话
            cover_letter_email: Cover Letter 邮件对象

        Returns:
            已存在的卡片，如果不存在则返回 None
        """
        return thread_series_queries.check_existing_card(session, cover_letter_email)

    # ========== 订阅辅助相关 ==========

    async def check_existing_subscription(
        self, message_id: str
    ) -> Optional[PatchSubscription]:
        """检查是否已存在订阅

        Args:
            message_id: PATCH message_id

        Returns:
            已存在的订阅对象，如果不存在则返回 None
        """
        return await thread_subscription_helpers.check_existing_subscription(message_id)

    def build_subscription_data(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        message_id: str,
        subsystem: str,
        platform_message_id: str,
        platform_channel_id: str,
        subject: str,
        author: str,
        url: Optional[str],
        expires_at: datetime,
        series_message_id: Optional[str],
        patch_version: Optional[str],
        patch_index: Optional[int],
        patch_total: Optional[int],
    ):
        """构建订阅数据

        Args:
            message_id: PATCH message_id
            subsystem: 子系统名称
            platform_message_id: 平台消息 ID
            platform_channel_id: 平台频道 ID
            subject: PATCH 主题
            author: PATCH 作者
            url: PATCH 链接
            expires_at: 过期时间
            series_message_id: 系列 message_id
            patch_version: PATCH 版本
            patch_index: PATCH 索引
            patch_total: PATCH 总数

        Returns:
            订阅数据对象
        """
        return thread_subscription_helpers.build_subscription_data(
            message_id,
            subsystem,
            platform_message_id,
            platform_channel_id,
            subject,
            author,
            url,
            expires_at,
            series_message_id,
            patch_version,
            patch_index,
            patch_total,
        )

    def calculate_expires_at(self, timeout_hours: int) -> datetime:
        """计算过期时间

        Args:
            timeout_hours: 超时小时数

        Returns:
            过期时间
        """
        return thread_subscription_helpers.calculate_expires_at(timeout_hours)

    def log_subscription_created(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        subject: str,
        series_message_id: Optional[str],
        patch_version: Optional[str],
        patch_index: Optional[int],
        patch_total: Optional[int],
    ) -> None:
        """记录订阅创建日志

        Args:
            subject: PATCH 主题
            series_message_id: 系列 message_id
            patch_version: PATCH 版本
            patch_index: PATCH 索引
            patch_total: PATCH 总数
        """
        thread_subscription_helpers.log_subscription_created(
            subject, series_message_id, patch_version, patch_index, patch_total
        )


# 全局服务实例
thread_content_service = ThreadContentService()
