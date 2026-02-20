"""Feed 处理逻辑

负责从 lore.kernel.org 抓取邮件列表的 Atom feed，解析邮件内容并存储到数据库。
"""

import hashlib
import re
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple, TYPE_CHECKING
from urllib.parse import urlparse

import feedparser
from feedparser.util import FeedParserDict
import logging

logger = logging.getLogger(__name__)


from ..config import get_config
from ..db.models import Subsystem
from ..db.repo import SUBSYSTEM_REPO

if TYPE_CHECKING:
    from ..db.repo import FeedMessageData
from .types import (
    FeedEntry,
    FeedEntryContent,
    FeedEntryMetadata,
    FeedProcessResult,
)
from .feed_message_classifier import classify_message


class FeedProcessor:
    """处理单个子系统的 feed：抓取、解析、入库、统计

    负责从指定 URL 抓取 Atom feed，解析邮件条目，去重后存储到数据库。
    """

    def __init__(
        self, *, database, thread_manager=None, feed_message_service=None
    ) -> None:
        """初始化 Feed 处理器

        Args:
            database: 数据库实例
            thread_manager: Thread 管理器（可选，用于处理 PATCH 卡片和 REPLY）
            feed_message_service: Feed 消息服务（可选，用于处理 PATCH 和 REPLY）
        """
        self.database = database
        self.thread_manager = thread_manager
        self.feed_message_service = feed_message_service

        # Per-subsystem last_update_dt tracking (fixes shared-timestamp bug)
        self._last_update_dts: dict[str, datetime] = {}

        # 解析环境变量覆盖（用于调试/开发），作为所有子系统的初始值
        self._override_dt: Optional[datetime] = None
        cfg = get_config()
        override_iso = getattr(cfg, "last_update_dt_override_iso", None)
        if override_iso is not None:
            iso_str = str(override_iso).strip()
            try:
                if iso_str.endswith("Z"):
                    iso_str = iso_str[:-1] + "+00:00"
                self._override_dt = datetime.fromisoformat(iso_str)
                if self._override_dt.tzinfo is None:
                    self._override_dt = self._override_dt.replace(tzinfo=timezone.utc)
                logger.info(f"Using LKML_LAST_UPDATE_AT override: {self._override_dt}")
            except (ValueError, AttributeError, TypeError):
                logger.warning(
                    f"Invalid LKML_LAST_UPDATE_AT format: {override_iso}, "
                    "using database query"
                )

    def _handle_feed_status(self, feed_status: Optional[int], feed_url: str) -> bool:
        """处理 feed 状态码，返回是否应该继续处理"""
        if not feed_status:
            return True
        if feed_status == 404:
            logger.error(
                f"Feed not found (404) for {feed_url}. "
                "Possibly invalid subsystem or URL."
            )
            return False
        if feed_status >= 400:
            logger.error(f"HTTP error {feed_status} when fetching {feed_url}.")
            return False
        if feed_status != 200:
            logger.warning(
                f"Unexpected HTTP status {feed_status} for {feed_url}, "
                "continue parsing."
            )
        return True

    def _handle_feed_bozo(self, feed: FeedParserDict, feed_url: str) -> bool:
        """处理 feed 解析警告，返回是否应该继续处理"""
        if not feed.bozo:
            return True
        bozo_exception = feed.bozo_exception
        bozo_message = (
            str(bozo_exception) if bozo_exception else "Unknown parsing error"
        )
        logger.warning(f"Feed parsing warning for {feed_url}: {bozo_message}")
        if not feed.entries:
            logger.error(
                f"Feed parsing failed for {feed_url}: {bozo_message}. No entries."
            )
            return False
        return True

    def _filter_entries_by_date(
        self, feed_entries: List[FeedParserDict], last_update_dt: datetime
    ) -> List[FeedParserDict]:
        """根据日期筛选新条目"""
        entries: List[FeedParserDict] = []
        for entry in feed_entries:
            if hasattr(entry, "updated_parsed") and entry.updated_parsed:
                entry_dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            else:
                # 没有时间信息则认为是新条目（保守处理）
                entries.append(entry)
                continue

            if entry_dt > last_update_dt:
                entries.append(entry)
            # 不使用 break，继续检查所有条目
            # lore.kernel.org 的 feed 不保证严格按时间递减排序
        return entries

    def get_feed_entries(
        self, feed_url: str, last_update_dt: datetime
    ) -> List[FeedParserDict]:
        """拉取并筛选新条目（带指数退避重试）"""
        start_ts = time.time()
        logger.info(f"Fetching feed from {feed_url}")

        max_attempts = 3
        delay = 1.0

        for attempt in range(1, max_attempts + 1):
            try:
                feed: FeedParserDict = feedparser.parse(feed_url)
            except (OSError, ValueError, KeyError) as e:
                logger.warning(
                    f"Attempt {attempt}/{max_attempts} failed to fetch feed: "
                    f"{type(e).__name__}: {e}"
                )
                if attempt < max_attempts:
                    time.sleep(delay)
                    delay *= 2
                    continue
                logger.error(
                    f"Failed to fetch feed from {feed_url} after {max_attempts} attempts: {e}",
                    exc_info=True,
                )
                return []

            feed_status = getattr(feed, "status", None)
            if not self._handle_feed_status(feed_status, feed_url):
                return []

            if not self._handle_feed_bozo(feed, feed_url):
                return []

            entries = self._filter_entries_by_date(feed.entries, last_update_dt)

            if feed.bozo and entries:
                logger.info(
                    f"Feed parsed with warnings for {feed_url}, extracted {len(entries)} entries"
                )

            elapsed_ms = int((time.time() - start_ts) * 1000)
            logger.info(
                f"Fetched {len(entries)} entries from {feed_url} in {elapsed_ms} ms"
            )
            return entries

    def extract_email_from_author(self, author: str) -> Optional[str]:
        """从作者信息中提取邮箱地址

        Args:
            author: 作者信息字符串，可能包含姓名和邮箱

        Returns:
            提取出的邮箱地址，如果提取失败则返回 None
        """
        try:
            email_match = re.search(
                r"[<\(]([^<>\(\)]+@[^<>\(\)]+\.[^<>\(\)]+)[>\)]", author
            )
            if email_match:
                return email_match.group(1)

            email_match = re.search(
                r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", author
            )
            if email_match:
                return email_match.group(1)

            return None
        except (AttributeError, TypeError) as e:
            logger.error(f"Failed to extract email from author '{author}': {e}")
            return None

    def is_reply_message(self, title: str) -> bool:
        """判断是否为回复消息

        Args:
            title: 邮件主题

        Returns:
            如果主题以小写 "re:" 开头则返回 True，否则返回 False
        """
        return title.lower().startswith("re:")

    def is_patch_message(self, title: str) -> bool:
        """判断是否为 PATCH 邮件

        常见格式如: [PATCH], [PATCH v2], [RFC PATCH], [PATCH 0/5] 等
        """
        lowered = title.lower()
        return "[patch" in lowered or lowered.startswith("patch:")

    def _extract_received_at(self, entry: FeedParserDict) -> datetime:
        """从条目中提取接收时间"""
        try:
            if hasattr(entry, "updated_parsed") and entry.updated_parsed:
                return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            return datetime.now(timezone.utc)
        except (ValueError, TypeError, IndexError) as e:
            logger.warning(f"Failed to parse date for entry {entry.title}: {e}")
            return datetime.now(timezone.utc)

    def _generate_message_id(
        self, entry: FeedParserDict, subsystem: Subsystem, received_at: datetime
    ) -> str:
        """生成稳定的 message_id"""
        message_id = entry.get("id") or entry.link
        if not message_id:
            base = f"{subsystem.name}|{entry.title}|{int(received_at.timestamp())}"
            message_id = hashlib.sha256(base.encode("utf-8")).hexdigest()[:40]
        return message_id

    def _extract_message_id_header(self, entry: FeedParserDict) -> Optional[str]:
        """从链接中提取 message_id_header"""
        if not hasattr(entry, "link") or not entry.link:
            return None
        try:
            parsed_url = urlparse(entry.link)
            path = parsed_url.path.strip("/")
            if path:
                parts = path.split("/")
                if len(parts) >= 2:
                    return parts[-1]
        except (ValueError, AttributeError) as e:
            logger.debug(f"Failed to extract message_id from link {entry.link}: {e}")
        return None

    def _extract_in_reply_to_header(self, entry: FeedParserDict) -> Optional[str]:
        """从条目中提取 in_reply_to_header

        从 thr:in-reply-to 的 href 属性提取父邮件的 URL，
        然后解析出真正的 Message-ID。
        """
        try:
            thr = entry.get("thr_in-reply-to") or entry.get("thr:in-reply-to")
            if isinstance(thr, dict):
                # 优先从 href 提取（包含真正的邮件 URL）
                href = thr.get("href")
                if isinstance(href, str) and href:
                    # 从 URL 中提取 Message-ID
                    # 例如: https://lore.kernel.org/rust-for-linux/msg-id@domain.com/
                    parsed_url = urlparse(href)
                    path = parsed_url.path.strip("/")
                    if path:
                        parts = path.split("/")
                        if len(parts) >= 2:
                            return parts[-1]  # 返回 msg-id@domain.com

                # 如果 href 不存在或提取失败，尝试使用 ref（可能是 UUID）
                ref = thr.get("ref")
                if isinstance(ref, str):
                    # 如果是 UUID 格式，记录警告
                    if ref.startswith("urn:uuid:"):
                        logger.debug(
                            f"In-Reply-To is UUID format: {ref}, may not work correctly"
                        )
                    return ref
        except (AttributeError, TypeError, ValueError) as e:
            logger.debug(f"Failed to extract in_reply_to_header: {e}")
        return None

    def _extract_feed_message_data(
        self, entry: FeedParserDict, subsystem: Subsystem
    ) -> Tuple[str, datetime, str, str, str]:
        """提取 Feed 消息的基本数据

        Returns:
            (email, received_at, message_id, message_id_header, in_reply_to_header)
        """
        email = self.extract_email_from_author(entry.author)
        received_at = self._extract_received_at(entry)
        message_id = self._generate_message_id(entry, subsystem, received_at)
        message_id_header = self._extract_message_id_header(entry)
        in_reply_to_header = self._extract_in_reply_to_header(entry)
        return (email, received_at, message_id, message_id_header, in_reply_to_header)

    def _classify_feed_entry(
        self, entry: FeedParserDict, subsystem: Subsystem
    ) -> Tuple["FeedMessageData", object]:
        """Classify a feed entry without any DB writes.

        Returns:
            (FeedMessageData, MessageClassification) tuple
        """
        from ..db.repo import FeedMessageData as RepoFeedMessageData

        base_data = self._extract_feed_message_data(entry, subsystem)
        email, received_at, message_id, msg_id_header, in_reply_to = base_data
        classification = classify_message(entry.title, in_reply_to, msg_id_header)
        patch_info = classification.patch_info
        data = RepoFeedMessageData(
            subsystem_name=subsystem.name,
            message_id_header=msg_id_header or message_id,
            message_id=message_id,
            in_reply_to_header=in_reply_to,
            subject=entry.title,
            author=entry.author,
            author_email=email or "unknown@example.com",
            content=entry.get("summary", "") or entry.get("description", ""),
            url=entry.link,
            received_at=received_at,
            is_patch=classification.is_patch,
            is_reply=classification.is_reply,
            is_series_patch=classification.is_series_patch,
            patch_version=patch_info.version if patch_info else None,
            patch_index=patch_info.index if patch_info else None,
            patch_total=patch_info.total if patch_info else None,
            is_cover_letter=patch_info.is_cover_letter if patch_info else False,
            series_message_id=classification.series_message_id,
        )
        return data, classification

    def _create_feed_entry(self, feed_message_data) -> FeedEntry:
        """创建 FeedEntry 对象

        Args:
            feed_message_data: FeedMessageData 或 FeedMessage 对象
        """

        # 处理 received_at，可能是 datetime 对象或 None
        received_at_str = ""
        if feed_message_data.received_at:
            if isinstance(feed_message_data.received_at, datetime):
                received_at_str = feed_message_data.received_at.isoformat()
            else:
                received_at_str = str(feed_message_data.received_at)

        content = FeedEntryContent(
            summary=feed_message_data.content or "",
            received_at=received_at_str,
            is_reply=feed_message_data.is_reply,
            is_patch=feed_message_data.is_patch,
        )

        # 构建元数据
        metadata = FeedEntryMetadata(
            message_id=feed_message_data.message_id_header,
            in_reply_to=feed_message_data.in_reply_to_header,
        )

        return FeedEntry(
            id=feed_message_data.id if hasattr(feed_message_data, "id") else None,
            subject=feed_message_data.subject,
            author=feed_message_data.author,
            email=feed_message_data.author_email,
            url=feed_message_data.url,
            content=content,
            metadata=metadata,
        )

    async def _process_entries(
        self, session, entries: List[FeedParserDict], subsystem: Subsystem
    ) -> Tuple[int, int, List[FeedEntry]]:
        """处理条目并返回统计信息

        分两个阶段：
        1. 在内存中分类所有 feed entry（无 DB 写入）
        2. 由 service 层决定哪些消息需要持久化
        """
        new_count = 0
        reply_count = 0
        processed_entries: List[FeedEntry] = []

        # Phase 1: Classify all entries in-memory (NO DB writes)
        classified = []
        for entry in entries:
            data, classification = self._classify_feed_entry(entry, subsystem)
            classified.append((data, classification))

        # Phase 2: Service layer decides what to persist
        for data, classification in classified:
            if classification.is_reply:
                reply_count += 1
            else:
                new_count += 1

            if self.feed_message_service:
                try:
                    await self.feed_message_service.process_email_message(
                        session, data, classification
                    )
                except (RuntimeError, ValueError, AttributeError) as e:
                    logger.error("Failed to process feed message: %s", e, exc_info=True)

            processed_entries.append(self._create_feed_entry(data))

        return (new_count, reply_count, processed_entries)

    def _update_last_update_time(
        self, subsystem_name: str, entries: List[FeedParserDict]
    ) -> None:
        """更新指定子系统的最后更新时间"""
        if not entries:
            return
        latest_entry = entries[0]
        if hasattr(latest_entry, "updated_parsed") and latest_entry.updated_parsed:
            self._last_update_dts[subsystem_name] = datetime(
                *latest_entry.updated_parsed[:6], tzinfo=timezone.utc
            )

    async def _initialize_last_update_dt(self, subsystem_name: str) -> None:
        """从数据库初始化指定子系统的 last_update_dt

        Args:
            subsystem_name: 子系统名称
        """
        if subsystem_name in self._last_update_dts:
            return  # 该子系统已初始化

        # 环境变量覆盖优先
        if self._override_dt is not None:
            self._last_update_dts[subsystem_name] = self._override_dt
            return

        try:
            async with self.database.get_db_session() as session:
                from sqlalchemy import select, func
                from ..db.models import FeedMessageModel

                # 查询该子系统最新的 received_at
                result = await session.execute(
                    select(func.max(FeedMessageModel.received_at)).where(
                        FeedMessageModel.subsystem_name == subsystem_name
                    )
                )
                max_received_at = result.scalar()

                if max_received_at:
                    if max_received_at.tzinfo is None:
                        self._last_update_dts[subsystem_name] = max_received_at.replace(
                            tzinfo=timezone.utc
                        )
                    else:
                        self._last_update_dts[subsystem_name] = max_received_at
                    logger.info(
                        f"Initialized last_update_dt from database for {subsystem_name}: "
                        f"{self._last_update_dts[subsystem_name]}"
                    )
                else:
                    self._last_update_dts[subsystem_name] = datetime.now(timezone.utc)
                    logger.info(
                        f"No historical data for {subsystem_name}, using current time: "
                        f"{self._last_update_dts[subsystem_name]}"
                    )
        except (RuntimeError, ValueError) as e:
            logger.warning(
                f"Failed to initialize last_update_dt from database for "
                f"{subsystem_name}: {e}, using current time"
            )
            self._last_update_dts[subsystem_name] = datetime.now(timezone.utc)

    async def process_feed(
        self, subsystem_name: str, feed_url: str
    ) -> FeedProcessResult:
        """处理单个子系统 feed 并返回统计结果

        Args:
            subsystem_name: 子系统名称
            feed_url: Feed URL

        Returns:
            Feed 处理结果，包含新增数量、回复数量和条目列表
        """
        logger.info(f"Processing feed for subsystem: {subsystem_name}")

        # 初始化该子系统的 last_update_dt（如果还没有初始化）
        await self._initialize_last_update_dt(subsystem_name)

        proc_start = time.time()

        entries = self.get_feed_entries(feed_url, self._last_update_dts[subsystem_name])
        if not entries:
            logger.info(f"No new entries found for {subsystem_name}")
            return FeedProcessResult(
                subsystem=subsystem_name, new_count=0, reply_count=0, entries=[]
            )

        async with self.database.get_db_session() as session:
            subsystem = await SUBSYSTEM_REPO.get_or_create(session, subsystem_name)
            new_count, reply_count, processed_entries = await self._process_entries(
                session, entries, subsystem
            )
            await session.commit()

        self._update_last_update_time(subsystem_name, entries)

        proc_ms = int((time.time() - proc_start) * 1000)
        logger.info(
            f"Processed {len(entries)} entries for {subsystem_name}: "
            f"{new_count} new, {reply_count} replies, took {proc_ms} ms"
        )

        return FeedProcessResult(
            subsystem=subsystem_name,
            new_count=new_count,
            reply_count=reply_count,
            entries=processed_entries,
        )
