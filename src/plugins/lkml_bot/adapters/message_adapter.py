"""消息适配器基类"""

from nonebot.log import logger
from abc import ABC, abstractmethod

from lkml.feed import SubsystemUpdate

logger = logger


class MessageAdapter(ABC):
    """消息适配器抽象基类"""

    @abstractmethod
    async def send_subsystem_update(
        self, subsystem: str, update_data: SubsystemUpdate
    ) -> None:
        """发送子系统更新到对应平台

        Args:
            subsystem: 子系统名称
            update_data: 更新数据
        """
        pass
