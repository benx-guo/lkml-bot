"""Thread 渲染器

Plugins 层渲染器：只负责渲染 Thread Overview。
所有业务逻辑由 Service 层处理，发送由客户端处理。
"""

from typing import Dict, List

from lkml.service.types import (
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

        Args:
            overview_data: Thread Overview 数据

        Returns:
            DiscordRenderedThreadOverview 渲染结果
        """
        messages: Dict[int, DiscordRenderedThreadMessage] = {}

        if overview_data.root:
            content = self._render_thread_tree(overview_data)
            messages[0] = DiscordRenderedThreadMessage(content=content, embed=None)

        return DiscordRenderedThreadOverview(messages=messages)

    def render_overview_message(
        self, overview_data: ThreadOverviewData
    ) -> DiscordRenderedThreadMessage:
        """渲染 Thread Overview 为单条消息（用于更新）"""
        content = self._render_thread_tree(overview_data)
        return DiscordRenderedThreadMessage(content=content, embed=None)

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
        msg_time = (
            msg.received_at.strftime("%Y-%m-%d %H:%M UTC") if msg.received_at else ""
        )
        author = msg.author.split(" (", 1)[0] if msg.author else "Unknown"

        lines.append(f"{indent}\\` {msg_time} [{subject}]({msg.url}) {author}")

        # 递归渲染子节点
        for child in node.children:
            child_lines = self._render_tree_node(child, level + 1)
            lines.extend(child_lines)

        return lines
