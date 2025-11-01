"""LKML 业务逻辑包（独立于机器人框架）"""

from .db import Base, Subsystem, EmailMessage, OperationLog


# 使用 __getattr__ 实现延迟导入（避免循环导入）
def __getattr__(name: str):
    """延迟导入相关的内容以避免循环导入"""
    if name == "LKMLService":
        from .service import LKMLService

        return LKMLService
    elif name == "SubsystemService":
        from .service import SubsystemService

        return SubsystemService
    elif name == "MonitoringService":
        from .service import MonitoringService

        return MonitoringService
    elif name == "QueryService":
        from .service import QueryService

        return QueryService
    elif name == "LKMLFeedMonitor":
        from .feed.feed_monitor import LKMLFeedMonitor

        return LKMLFeedMonitor
    elif name == "LKMLScheduler":
        from .scheduler import LKMLScheduler

        return LKMLScheduler
    # Feed types
    elif name == "FeedEntry":
        from .feed import FeedEntry

        return FeedEntry
    elif name == "FeedProcessResult":
        from .feed import FeedProcessResult

        return FeedProcessResult
    elif name == "SubsystemUpdate":
        from .feed import SubsystemUpdate

        return SubsystemUpdate
    elif name == "SubsystemMonitoringResult":
        from .feed import SubsystemMonitoringResult

        return SubsystemMonitoringResult
    elif name == "MonitoringResult":
        from .feed import MonitoringResult

        return MonitoringResult
    elif name == "get_vger_subsystems":
        from .feed.vger_subsystems import get_vger_subsystems

        return get_vger_subsystems
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Base",
    "Subsystem",
    "EmailMessage",
    "OperationLog",
    "LKMLService",
    "SubsystemService",
    "MonitoringService",
    "QueryService",
    "LKMLFeedMonitor",
    "LKMLScheduler",
    "FeedEntry",
    "FeedProcessResult",
    "SubsystemUpdate",
    "SubsystemMonitoringResult",
    "MonitoringResult",
    "get_vger_subsystems",
]
