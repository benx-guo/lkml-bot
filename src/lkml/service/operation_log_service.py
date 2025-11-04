"""操作日志辅助模块"""

from nonebot.log import logger
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import OperationLog

logger = logger


async def log_operation(
    session: AsyncSession,
    operator_id: str,
    operator_name: str,
    action: str,
    subsystem_name: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """记录操作日志

    Args:
        session: 数据库会话
        operator_id: 操作者ID
        operator_name: 操作者名称
        action: 操作类型（subscribe, unsubscribe, start_monitor等）
        subsystem_name: 子系统名称（可选）
        details: 详细信息（可选）
    """
    # 如果 subsystem_name 为 None，使用默认名称
    target_name = subsystem_name if subsystem_name is not None else "lkml"

    log = OperationLog(
        operator_id=operator_id,
        operator_name=operator_name,
        action=action,
        target_name=target_name,
        details=details,
    )
    session.add(log)
    await session.flush()
