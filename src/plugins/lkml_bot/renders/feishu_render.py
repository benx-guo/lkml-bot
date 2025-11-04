"""Feishu 平台渲染器"""

from lkml.feed import SubsystemUpdate
from .base import BaseTextRenderer


class FeishuRenderer(BaseTextRenderer):
    """Feishu 平台渲染器"""

    def render(self, subsystem: str, update_data: SubsystemUpdate) -> dict:
        """渲染为 Feishu 卡片格式

        Args:
            subsystem: 子系统名称
            update_data: 更新数据

        Returns:
            Feishu 卡片字典

        Note:
            TODO: 实现 Feishu 卡片格式
            目前返回空字典作为占位符
        """
        # TODO: 实现 Feishu 卡片格式
        # 返回空字典作为占位符，避免未实现方法导致错误
        return {}
