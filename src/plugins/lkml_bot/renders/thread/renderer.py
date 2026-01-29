"""Thread 渲染器

Plugins 层渲染器：只负责渲染 Thread Overview。
所有业务逻辑由 Service 层处理，发送由客户端处理。
"""

from typing import Dict, List

from lkml.service import FeedMessage
from lkml.service.types import (
    ReplyMapEntry,
    SubPatchOverviewData,
    ThreadNode,
    ThreadOverviewData,
)

from ..types import DiscordRenderedThreadMessage, DiscordRenderedThreadOverview


class ThreadOverviewRenderer:
    """Thread Overview 渲染器

    职责：
    1. 将 ThreadOverviewData 渲染成 Discord 格式
    2. 仅此而已

    不做：
    - 数据查询
    - 业务逻辑判断
    - 数据库操作
    - 发送消息（由客户端负责）
    """

    def __init__(self, config):
        """初始化渲染器

        Args:
            config: 配置对象（保留以便未来扩展）
        """
        self.config = config

    def render(
        self, overview_data: ThreadOverviewData
    ) -> DiscordRenderedThreadOverview:
        """渲染 Thread Overview 为 Discord 格式（不发送）

        支持两种数据格式：
        - 新版：使用 root 字段的完整层级树
        - 旧版：使用 sub_patch_overviews 字段

        Args:
            overview_data: Thread Overview 数据

        Returns:
            DiscordRenderedThreadOverview 渲染结果
        """
        messages: Dict[int, DiscordRenderedThreadMessage] = {}

        if overview_data.root:
            # 新版：使用层级树
            content = self._render_thread_tree(overview_data)
            messages[0] = DiscordRenderedThreadMessage(content=content, embed=None)
        elif overview_data.sub_patch_overviews:
            # 旧版兼容：使用 sub_patch_overviews
            content = self.render_overview_message(overview_data).content
            messages[0] = DiscordRenderedThreadMessage(content=content, embed=None)

        return DiscordRenderedThreadOverview(messages=messages)

    def render_sub_patch(
        self, sub_overview: SubPatchOverviewData
    ) -> DiscordRenderedThreadMessage:
        """渲染单个子 PATCH 消息（用于更新）

        Args:
            sub_overview: 子 PATCH 的完整 Overview 数据

        Returns:
            DiscordRenderedThreadMessage 渲染结果
        """
        content = self._render_sub_patch(sub_overview)
        return DiscordRenderedThreadMessage(content=content, embed=None)

    def render_overview_message(
        self, overview_data: ThreadOverviewData
    ) -> DiscordRenderedThreadMessage:
        """渲染 Thread Overview 为单条消息（用于更新）"""
        content = self._render_overview_content(overview_data)
        return DiscordRenderedThreadMessage(content=content, embed=None)

    def _render_sub_patch(self, sub_overview: SubPatchOverviewData) -> str:
        """渲染单个子 PATCH 消息

        格式：
        [subject](url)

        ` 时间 作者
            ` 时间 作者  # 子回复
        ` 时间 作者

        Args:
            sub_overview: 子 PATCH 的完整 Overview 数据（由 service 层准备）

        Returns:
            渲染后的子 PATCH 文本
        """
        lines = []
        patch = sub_overview.patch

        lines.append(f"[{patch.subject}]({patch.url})")
        lines.append("")  # 空行

        # 使用 service 层准备好的回复层级结构
        reply_hierarchy = sub_overview.reply_hierarchy
        reply_map = reply_hierarchy.reply_map
        root_replies = reply_hierarchy.root_replies

        if root_replies:
            # 为该 PATCH 的每个顶层回复构建层级树
            for root_reply_id in root_replies:
                if root_reply_id in reply_map:
                    root_reply = reply_map[root_reply_id].reply
                    reply_lines = self._format_reply_tree(
                        root_reply, reply_map, level=0
                    )
                    lines.extend(reply_lines)
        else:
            lines.append("_(No replies)_")

        return "\n".join(lines)

    def _render_overview_content(self, overview_data: ThreadOverviewData) -> str:
        """渲染所有子 PATCH 概览为单条消息内容"""
        if not overview_data.sub_patch_overviews:
            return ""

        blocks = [
            self._render_sub_patch(sub_overview)
            for sub_overview in overview_data.sub_patch_overviews
        ]
        return "\n".join(blocks)

    def _format_reply_tree(
        self, reply: FeedMessage, reply_map: Dict[str, ReplyMapEntry], level: int
    ) -> list:
        """递归格式化回复树

        格式：
        ` 时间 作者 (邮箱)
            ` 时间 作者 (邮箱)  # level=1
                ` 时间 作者 (邮箱)  # level=2

        Args:
            reply: 回复对象
            reply_map: 回复映射 {message_id: ReplyMapEntry}
            level: 层级深度（0 = 顶层）

        Returns:
            格式化后的行列表
        """
        lines = []

        # 缩进：使用 tab 字符
        indent = "\t" * level

        # 格式化当前回复：` 时间 作者 (邮箱)
        subject = reply.subject.split("] ", 1)[0] + "]"
        reply_time = reply.received_at.strftime("%Y-%m-%d %H:%M")
        author = reply.author.split(" (", 1)[0] if reply.author else "Unknown"

        lines.append(f"{indent}\\` {reply_time} [{subject}]({reply.url}) {author}")

        # 递归处理子回复
        message_id = reply.message_id_header
        if message_id in reply_map:
            reply_entry = reply_map[message_id]
            children_ids = reply_entry.children
            for child_id in children_ids:
                if child_id in reply_map:
                    child_reply = reply_map[child_id].reply
                    child_lines = self._format_reply_tree(
                        child_reply, reply_map, level + 1
                    )
                    lines.extend(child_lines)

        return lines

    def _render_thread_tree(self, overview_data: ThreadOverviewData) -> str:
        """渲染完整层级树

        格式：
        [Cover Letter Subject](url)

        ` 2026-01-28 12:14 [RFC PATCH v1 1/2] Author
            ` 2026-01-28 14:31 [Re: RFC PATCH v1 1/2] Reviewer
        ` 2026-01-28 12:16 [RFC PATCH v1 2/2] Author
        ` 2026-01-28 14:43 [Re: RFC PATCH v1 0/2] Reviewer

        Args:
            overview_data: Thread Overview 数据（包含 root 层级树）

        Returns:
            渲染后的文本
        """
        if not overview_data.root:
            return ""

        lines = []
        root = overview_data.root
        patch_card = overview_data.patch_card

        # 渲染根节点标题
        lines.append(f"[{patch_card.subject}]({patch_card.url})")
        lines.append("")  # 空行

        # 渲染子节点
        if root.children:
            for child in root.children:
                child_lines = self._render_tree_node(child, level=0)
                lines.extend(child_lines)
        else:
            lines.append("_(No replies)_")

        return "\n".join(lines)

    def _render_tree_node(self, node: ThreadNode, level: int) -> List[str]:
        """递归渲染树节点

        Args:
            node: ThreadNode 节点
            level: 层级深度（0 = 顶层子节点）

        Returns:
            格式化后的行列表
        """
        lines = []
        msg = node.message

        # 缩进：使用 tab 字符
        indent = "\t" * level

        # 格式化当前节点：` 时间 [subject](url) 作者
        subject = msg.subject.split("] ", 1)[0] + "]"
        msg_time = msg.received_at.strftime("%Y-%m-%d %H:%M") if msg.received_at else ""
        author = msg.author.split(" (", 1)[0] if msg.author else "Unknown"

        lines.append(f"{indent}\\` {msg_time} [{subject}]({msg.url}) {author}")

        # 递归渲染子节点
        for child in node.children:
            child_lines = self._render_tree_node(child, level + 1)
            lines.extend(child_lines)

        return lines
