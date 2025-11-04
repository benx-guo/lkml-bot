"""LKML Bot NoneBot plugin

说明：本插件负责装配 LKML 领域层依赖（配置、数据库、监控器、调度器）并注册命令。
命令均基于 @ 提及(to_me) 触发：
  - `.commands.help`
  - `.commands.subscribe`
  - `.commands.unsubscribe`
  - `.commands.start_monitor`
  - `.commands.stop_monitor`
  - `.commands.run_monitor`
"""

from nonebot.log import logger
import sys
from pathlib import Path

# 1) 环境与路径
# 加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # dotenv 未安装，跳过
    pass

# 将 src 目录添加到 Python 路径，以便导入 lkml
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

logger = logger

# 2) 基础设施装配（配置、数据库）
# 注意：这些导入在 sys.path 修改之后，是必要的，因此忽略 E402
from lkml.config import set_config  # noqa: E402
from lkml.db import set_database, LKMLDatabase, Base  # noqa: E402
from .config import get_config  # noqa: E402

# 初始化数据库
plugin_config = get_config()
database = LKMLDatabase(plugin_config.database_url, Base)

# 设置基础设施（PluginConfig 已经实现了 Config 接口）
set_config(plugin_config)
set_database(database)

# 3) 注册子系统来源（数据来源由实现决定）
try:
    from lkml.feed.vger_subsystems import get_vger_subsystems  # noqa: E402

    plugin_config.set_vger_subsystems_getter(get_vger_subsystems)
except ImportError:
    logger.warning(
        "lkml.vger_cache module not available, vger subsystems will not be provided"
    )
except Exception as e:
    logger.warning(f"Failed to register vger subsystems getter: {e}")

# 4) 创建监控与调度实例（使用适配器的消息发送器）
from lkml.feed.feed import FeedProcessor  # noqa: E402
from lkml.feed.feed_monitor import LKMLFeedMonitor  # noqa: E402
from lkml.scheduler import LKMLScheduler  # noqa: E402
from .message_sender import MessageSender  # noqa: E402

message_sender = MessageSender()


async def send_update_callback(subsystem: str, update_data):
    """消息发送回调"""
    await message_sender.send_subsystem_update(subsystem, update_data)


# 使用依赖注入创建监控器与调度器
processor = FeedProcessor(database=database)
monitor = LKMLFeedMonitor(config=plugin_config, processor=processor, database=database)
scheduler = LKMLScheduler(message_sender=send_update_callback)
scheduler.monitor = monitor

# 5) 导入命令模块，确保处理器在导入时完成注册
from .commands import help  # noqa: F401, E402
from .commands import subscribe  # noqa: F401, E402
from .commands import unsubscribe  # noqa: F401, E402
from .commands import start_monitor  # noqa: F401, E402
from .commands import stop_monitor  # noqa: F401, E402
from .commands import run_monitor  # noqa: F401, E402

__all__ = [
    "help",
    "subscribe",
    "unsubscribe",
    "start_monitor",
    "stop_monitor",
    "run_monitor",
]


# 6) 机器人生命周期：启动/停止钩子
from nonebot import get_driver  # noqa: E402

driver = get_driver()


@driver.on_startup
async def auto_start_monitoring():
    """在 bot 启动时自动启动监控任务"""
    try:
        if not scheduler.is_running:
            logger.info("Auto-starting LKML monitoring scheduler on bot startup")
            await scheduler.start()
        else:
            logger.info("LKML monitoring scheduler is already running")
    except Exception as e:
        logger.error(f"Failed to auto-start monitoring scheduler: {e}", exc_info=True)


@driver.on_shutdown
async def auto_stop_monitoring():
    """在 bot 关闭时停止监控任务"""
    try:
        if scheduler.is_running:
            logger.info("Stopping LKML monitoring scheduler on bot shutdown")
            await scheduler.stop()
    except Exception as e:
        logger.error(f"Failed to stop monitoring scheduler: {e}", exc_info=True)
