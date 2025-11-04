"""启动监控命令模块"""

from nonebot.log import logger
from nonebot import on_message
from nonebot.rule import to_me
from nonebot.adapters import Event, Message
from nonebot.params import EventMessage
from nonebot.exception import FinishedException
from ..shared import register_command, check_admin
from lkml import LKMLService
from .. import scheduler

lkml_service = LKMLService()

logger = logger

# 仅当消息 @ 到机器人，并且以 "/start-monitor" 开头时处理
# 优先级设为 50，高于 help (40)，确保优先匹配
start_monitor_cmd = on_message(rule=to_me(), priority=50, block=False)


@start_monitor_cmd.handle()
async def handle_start_monitor(event: Event, message: Message = EventMessage()):
    """处理启动监控命令"""
    try:
        # 获取消息纯文本
        text = message.extract_plain_text().strip()

        logger.info(f"Start monitor command handler triggered, text: '{text}'")

        # 处理文本：去除前导空格，查找命令
        text = text.strip()

        # 如果文本以 "/start-monitor" 开头
        if not text.startswith("/start-monitor"):
            # 尝试查找 "/start-monitor" 在文本中的位置
            idx = text.find("/start-monitor")
            if idx >= 0:
                text = text[idx:].strip()  # 从 "/start-monitor" 开始
            else:
                # 不匹配 start-monitor 命令，直接返回（让其他处理器处理）
                logger.debug(
                    f"Text does not match '/start-monitor', returning. Text: '{text}'"
                )
                return

        # 检查权限
        if not check_admin(event):
            await start_monitor_cmd.finish("❌ 权限不足：此命令仅限管理员使用")
            return

        # 获取用户信息
        try:
            user_id = event.get_user_id()
            user_name = user_id
            if hasattr(event, "author"):
                author = getattr(event, "author", {})
                if isinstance(author, dict):
                    user_name = author.get("username", user_id)
                elif hasattr(author, "username"):
                    user_name = author.username
                elif hasattr(author, "global_name"):
                    user_name = author.global_name or user_id
            logger.debug(f"Operator: {user_id} ({user_name})")
        except FinishedException:
            raise  # 重新抛出 FinishedException，这是正常流程
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            await start_monitor_cmd.finish("❌ 无法获取用户信息")

        # 调用服务启动监控
        try:
            success = await lkml_service.start_monitoring(
                operator_id=str(user_id),
                operator_name=str(user_name),
                scheduler=scheduler,
            )

            if success:
                await start_monitor_cmd.finish("✅ 成功启动邮件列表监控！")
            else:
                await start_monitor_cmd.finish(
                    "❌ 启动监控失败。监控可能已经在运行中。"
                )
        except FinishedException:
            raise  # 重新抛出 FinishedException，这是正常流程
        except Exception as e:
            logger.error(f"Error in start_monitoring: {e}", exc_info=True)
            await start_monitor_cmd.finish(f"❌ 启动监控时发生错误: {str(e)}")
    except FinishedException:
        raise  # 重新抛出 FinishedException，这是正常流程
    except Exception as e:
        logger.error(f"Unexpected error in handle_start_monitor: {e}", exc_info=True)
        await start_monitor_cmd.finish(f"❌ 处理命令时发生错误: {str(e)}")


# 在导入时注册命令元信息（管理员命令）
register_command(
    name="start-monitor",
    usage="/start-monitor",
    description="启动邮件列表监控",
    admin_only=True,
)
