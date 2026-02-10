"""Thread 服务

封装 Thread 相关的数据库操作和内容处理，提供业务逻辑层接口。
包括 Thread 的 CRUD 操作、回复处理、层级树构建等功能。
Service 层通过依赖注入接受 Repository 实例。
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List

from ..db.repo import (
    FeedMessageRepository,
    PatchCardRepository,
    PatchThreadData as RepoPatchThreadData,
    PatchThreadRepository,
)
from .types import (
    PatchThread,
    PatchCard,
    ThreadOverviewData,
    ThreadNode,
    FeedMessage,
)

logger = logging.getLogger(__name__)


def _extract_message_id_from_header(in_reply_to_header: Optional[str]) -> Optional[str]:
    """从 in_reply_to_header 中提取 message_id

    处理可能包含尖括号、多个 message_id 等情况

    Args:
        in_reply_to_header: in_reply_to 头部值

    Returns:
        提取的 message_id，如果无法提取则返回 None
    """
    if not in_reply_to_header:
        return None

    # 移除尖括号
    cleaned = in_reply_to_header.strip()
    if cleaned.startswith("<") and cleaned.endswith(">"):
        cleaned = cleaned[1:-1]

    # 如果包含多个 message_id（用空格或逗号分隔），取第一个
    # 通常第一个是主要的回复目标
    parts = cleaned.split()
    if parts:
        return parts[0].strip()

    return cleaned if cleaned else None


# ========== ThreadService 类 ==========


class ThreadService:
    """Thread 服务类（业务 API 层）

    Service 层通过依赖注入接受 Repository 实例。
    Plugins 层通过 `get_thread_service()` 函数获取 Service 实例。
    """

    def __init__(
        self,
        patch_thread_repo: PatchThreadRepository,
        patch_card_repo: PatchCardRepository,
        feed_message_repo: FeedMessageRepository,
    ):
        """初始化服务

        Args:
            patch_thread_repo: PATCH Thread 仓库实例（已注入 session）
            patch_card_repo: PATCH 卡片仓库实例（已注入 session）
            feed_message_repo: Feed 消息仓库实例（已注入 session）
        """
        self.patch_thread_repo = patch_thread_repo
        self.patch_card_repo = patch_card_repo
        self.feed_message_repo = feed_message_repo

    def _repo_data_to_service_feed_message(self, repo_data) -> FeedMessage:
        """将 repo 层的 FeedMessageData 转换为 service 层的 FeedMessage

        Args:
            repo_data: repo 层的 FeedMessageData

        Returns:
            service 层的 FeedMessage
        """
        from ..db.repo import FeedMessageData

        # 如果已经是 FeedMessage，直接返回（防御性检查）
        if isinstance(repo_data, FeedMessage):
            return repo_data

        # 确保是 FeedMessageData 类型
        if not isinstance(repo_data, FeedMessageData):
            raise TypeError(
                f"Expected FeedMessageData or FeedMessage, got {type(repo_data)}"
            )

        from .helpers import extract_common_feed_message_fields

        common_fields = extract_common_feed_message_fields(repo_data)
        return FeedMessage(**common_fields)

    def _repo_data_to_service_data(self, repo_data: RepoPatchThreadData) -> PatchThread:
        """将 repo 层的 PatchThreadData 转换为 service 层的 PatchThread

        Args:
            repo_data: repo 层的 PatchThreadData

        Returns:
            service 层的 PatchThread
        """
        return PatchThread(
            patch_card_message_id_header=repo_data.patch_card_message_id_header,
            thread_id=repo_data.thread_id,
            thread_name=repo_data.thread_name,
            is_active=repo_data.is_active,
            overview_message_id=repo_data.overview_message_id,
            sub_patch_messages=repo_data.sub_patch_messages,
            created_at=repo_data.created_at,
            archived_at=repo_data.archived_at,
        )

    async def find_by_message_id_header(
        self, message_id_header: str
    ) -> Optional[PatchThread]:
        """根据 PATCH 卡片的 message_id_header 查找 Thread

        Args:
            message_id_header: PATCH 卡片的 message_id_header

        Returns:
            Thread 数据，如果不存在则返回 None
        """
        try:
            repo_data = await self.patch_thread_repo.find_by_message_id_header(
                message_id_header
            )
            return self._repo_data_to_service_data(repo_data) if repo_data else None
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                f"Failed to find thread by message_id_header: {e}", exc_info=True
            )
            return None

    async def find_by_thread_id(self, thread_id: str) -> Optional[PatchThread]:
        """根据 Thread ID 查找 Thread

        Args:
            thread_id: Thread ID

        Returns:
            Thread 数据，如果不存在则返回 None
        """
        try:
            repo_data = await self.patch_thread_repo.find_by_thread_id(thread_id)
            return self._repo_data_to_service_data(repo_data) if repo_data else None
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to find thread by thread_id: {e}", exc_info=True)
            return None

    async def create(
        self, message_id_header: str, thread_id: str, thread_name: str
    ) -> Optional[PatchThread]:
        """创建 Thread 记录

        Args:
            message_id_header: PATCH 卡片的 message_id_header
            thread_id: Thread ID
            thread_name: Thread 名称

        Returns:
            创建的 Thread 数据，失败返回 None
        """
        try:
            # 先通过 message_id_header 查找 patch_card
            repo_patch_card = await self.patch_card_repo.find_by_message_id_header(
                message_id_header
            )
            if not repo_patch_card:
                logger.error(
                    f"Cannot create thread: patch_card not found for message_id_header={message_id_header}"
                )
                return None

            repo_thread_data = RepoPatchThreadData(
                patch_card_message_id_header=message_id_header,
                thread_id=thread_id,
                thread_name=thread_name[:100],
            )
            repo_result = await self.patch_thread_repo.create(repo_thread_data)
            return self._repo_data_to_service_data(repo_result) if repo_result else None
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to create thread: {e}", exc_info=True)
            return None

    async def delete(self, thread_id: str) -> bool:
        """删除 Thread 记录

        Args:
            thread_id: Thread ID

        Returns:
            成功返回 True，失败返回 False
        """
        try:
            return await self.patch_thread_repo.delete(thread_id)
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to delete thread: {e}", exc_info=True)
            return False

    async def mark_as_inactive(self, thread_id: str) -> bool:
        """将 Thread 标记为不活跃

        Args:
            thread_id: Thread ID

        Returns:
            成功返回 True，失败返回 False
        """
        try:
            return await self.patch_thread_repo.mark_as_inactive(thread_id)
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to mark thread as inactive: {e}", exc_info=True)
            return False

    async def count_active_threads(self) -> int:
        """统计活跃的 Thread 数量

        Returns:
            活跃 Thread 的数量
        """
        try:
            return await self.patch_thread_repo.count_active_threads()
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to count active threads: {e}", exc_info=True)
            return 0

    async def update_overview_message_id(
        self, thread_id: str, overview_message_id: str
    ) -> bool:
        """更新 Thread 的 Overview 消息 ID

        Args:
            thread_id: Thread ID
            overview_message_id: Overview 消息 ID

        Returns:
            成功返回 True，失败返回 False
        """
        try:
            return await self.patch_thread_repo.update_overview_message_id(
                thread_id, overview_message_id
            )
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                f"Failed to update thread overview_message_id: {e}", exc_info=True
            )
            return False

    async def update_sub_patch_messages(
        self, thread_id: str, sub_patch_messages: dict
    ) -> bool:
        """更新 Thread 的子 PATCH 消息映射

        Args:
            thread_id: Thread ID
            sub_patch_messages: 子 PATCH 消息映射 {patch_index: message_id}

        Returns:
            是否更新成功
        """
        return await self.patch_thread_repo.update_sub_patch_messages(
            thread_id, sub_patch_messages
        )

    async def get_all_replies_for_patch(
        self, patch_message_id: str
    ) -> List[FeedMessage]:
        """获取某个 Patch 的所有 REPLY（包括 REPLY 的 REPLY）

        这个方法会递归查找所有直接和间接回复该 Patch 的消息。

        Args:
            patch_message_id: Patch 的 message_id_header

        Returns:
            该 Patch 的所有 REPLY 列表（包括 REPLY 的 REPLY）
        """
        try:
            # 使用递归方式查找所有回复（包括间接回复）
            all_replies = []
            message_ids_to_check = [patch_message_id]
            checked_message_ids = set()
            max_iterations = 20  # 防止无限循环

            iteration = 0
            while message_ids_to_check and iteration < max_iterations:
                iteration += 1
                current_message_id = message_ids_to_check.pop(0)

                # 避免重复检查
                if current_message_id in checked_message_ids:
                    continue
                checked_message_ids.add(current_message_id)

                # 查找直接回复当前消息的所有 REPLY
                direct_replies = await self.feed_message_repo.find_replies_to(
                    current_message_id, limit=100
                )

                # 转换为 Service 层的 FeedMessage
                for reply_data in direct_replies:
                    reply = self._repo_data_to_service_feed_message(reply_data)

                    # 如果这个 REPLY 还没有被添加到列表中，添加它
                    if not any(
                        r.message_id_header == reply.message_id_header
                        for r in all_replies
                    ):
                        all_replies.append(reply)
                        # 将这个 REPLY 的 message_id 加入待检查列表，以便查找回复它的 REPLY
                        if reply.message_id_header not in checked_message_ids:
                            message_ids_to_check.append(reply.message_id_header)

            return all_replies
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                f"Failed to get all replies for patch {patch_message_id}: {e}",
                exc_info=True,
            )
            return []

    async def _get_all_messages_for_series(
        self, patch_card: PatchCard
    ) -> List[FeedMessage]:
        """获取 series 的所有消息（Cover Letter、子 patches、所有回复）

        Args:
            patch_card: PatchCard 对象（包含 series_patches 信息）

        Returns:
            所有相关消息的列表
        """
        all_messages: List[FeedMessage] = []
        seen_message_ids: set = set()

        # 收集所有需要查找回复的 message_id
        message_ids_to_collect = []

        # 添加 Cover Letter / 根消息
        message_ids_to_collect.append(patch_card.message_id_header)

        # 添加所有子 patches
        if patch_card.series_patches:
            for sub_patch in patch_card.series_patches:
                if sub_patch.message_id not in seen_message_ids:
                    message_ids_to_collect.append(sub_patch.message_id)

        # 对每个消息收集其所有回复
        for msg_id in message_ids_to_collect:
            # 获取该消息本身
            msg_data = await self.feed_message_repo.find_by_message_id_header(msg_id)
            if msg_data and msg_id not in seen_message_ids:
                all_messages.append(self._repo_data_to_service_feed_message(msg_data))
                seen_message_ids.add(msg_id)

            # 获取该消息的所有回复
            replies = await self.get_all_replies_for_patch(msg_id)
            for reply in replies:
                if reply.message_id_header not in seen_message_ids:
                    all_messages.append(reply)
                    seen_message_ids.add(reply.message_id_header)

        return all_messages

    def _build_thread_tree(
        self,
        root_message: FeedMessage,
        all_messages: List[FeedMessage],
        patch_card: PatchCard,
    ) -> ThreadNode:
        """构建完整的 Thread 层级树

        Args:
            root_message: 根消息（Cover Letter 或单 Patch）
            all_messages: 所有相关消息列表
            patch_card: PatchCard 对象

        Returns:
            ThreadNode 层级树根节点
        """
        # 构建消息映射 {message_id: FeedMessage}
        message_map: Dict[str, FeedMessage] = {
            msg.message_id_header: msg for msg in all_messages
        }

        # 构建子 patch message_id 集合
        sub_patch_ids: set = set()
        if patch_card.series_patches:
            for sub_patch in patch_card.series_patches:
                sub_patch_ids.add(sub_patch.message_id)

        # 构建 {parent_id: [children]} 映射
        children_map: Dict[str, List[FeedMessage]] = {}
        for msg in all_messages:
            if msg.message_id_header == root_message.message_id_header:
                continue  # 跳过根消息

            parent_id = _extract_message_id_from_header(msg.in_reply_to_header)

            # 确定父节点
            if parent_id and parent_id in message_map:
                actual_parent = parent_id
            elif msg.message_id_header in sub_patch_ids:
                # 子 patch 直接挂在根节点下
                actual_parent = root_message.message_id_header
            else:
                # 无法确定父节点，挂在根节点下
                actual_parent = root_message.message_id_header

            if actual_parent not in children_map:
                children_map[actual_parent] = []
            children_map[actual_parent].append(msg)

        # 对每个父节点的子节点按时间排序
        for _, children in children_map.items():
            children.sort(key=lambda m: m.received_at or datetime.min)

        def _determine_node_type(msg: FeedMessage) -> str:
            """确定节点类型"""
            if msg.message_id_header == root_message.message_id_header:
                if patch_card.is_cover_letter:
                    return "cover_letter"
                return "sub_patch"  # 单 patch 作为 sub_patch 类型
            if msg.message_id_header in sub_patch_ids:
                return "sub_patch"
            return "reply"

        def _build_node(msg: FeedMessage) -> ThreadNode:
            """递归构建节点"""
            children_msgs = children_map.get(msg.message_id_header, [])
            children_nodes = [_build_node(child) for child in children_msgs]
            return ThreadNode(
                message=msg,
                children=children_nodes,
                node_type=_determine_node_type(msg),
            )

        return _build_node(root_message)

    async def prepare_thread_overview_data(
        self, message_id_header: str, patch_card_service=None
    ) -> Optional[ThreadOverviewData]:
        """准备 Thread Overview 渲染数据（供 Plugins 层使用）

        构建完整的 Thread 层级树：
        - Series Patch: Cover Letter 为根，子 patches 和回复为子节点
        - 单 Patch: 该 Patch 为根，所有回复为子节点

        Args:
            message_id_header: PATCH message_id_header（Cover Letter 或单 Patch）
            patch_card_service: 可选的 PatchCardService 实例（用于复用 session）

        Returns:
            ThreadOverviewData，如果不存在返回 None
        """
        from ..db.database import get_patch_card_service

        try:
            # 1. 获取 PatchCard（包含 series_patches）
            if patch_card_service:
                patch_card = await patch_card_service.get_patch_card_with_series_data(
                    message_id_header
                )
            else:
                async with get_patch_card_service() as service:
                    patch_card = await service.get_patch_card_with_series_data(
                        message_id_header
                    )

            if not patch_card:
                logger.warning(f"PatchCard not found: {message_id_header}")
                return None

            # 2. 获取根消息
            root_msg_data = await self.feed_message_repo.find_by_message_id_header(
                message_id_header
            )
            if not root_msg_data:
                logger.warning(f"Root message not found: {message_id_header}")
                return None
            root_message = self._repo_data_to_service_feed_message(root_msg_data)

            # 3. 获取所有相关消息
            all_messages = await self._get_all_messages_for_series(patch_card)

            # 4. 构建层级树
            root_node = self._build_thread_tree(root_message, all_messages, patch_card)

            # 5. 返回 ThreadOverviewData（使用新的 root 字段）
            return ThreadOverviewData(
                patch_card=patch_card,
                root=root_node,
            )

        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to prepare thread overview data: {e}", exc_info=True)
            return None


# 工厂函数已移至 lkml.db.database 模块以避免循环导入
# 不再在此模块导入，直接从 lkml.db.database 或 lkml.service 导入
