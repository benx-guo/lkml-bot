"""立即执行监控命令模块"""

from nonebot.log import logger
from nonebot import on_message
from nonebot.rule import to_me
from nonebot.adapters import Event, Message
from nonebot.params import EventMessage
from nonebot.exception import FinishedException
from ..shared import register_command, check_admin

# 仅当消息 @ 到机器人，并且以 "/run-monitor" 开头时处理
# 优先级设为 50，高于 help (40)，确保优先匹配
run_monitor_cmd = on_message(rule=to_me(), priority=50, block=False)


@run_monitor_cmd.handle()
async def handle_run_monitor(event: Event, message: Message = EventMessage()):
    """处理立即执行监控命令"""
    try:
        # 获取消息纯文本
        text = message.extract_plain_text().strip()

        logger.info(f"Run monitor command handler triggered, text: '{text}'")

        # 处理文本：去除前导空格，查找命令
        text = text.strip()

        # 如果文本以 "/run-monitor" 开头
        if not text.startswith("/run-monitor"):
            # 尝试查找 "/run-monitor" 在文本中的位置
            idx = text.find("/run-monitor")
            if idx >= 0:
                text = text[idx:].strip()  # 从 "/run-monitor" 开始
            else:
                # 不匹配 run-monitor 命令，直接返回（让其他处理器处理）
                logger.debug(
                    f"Text does not match '/run-monitor', returning. Text: '{text}'"
                )
                return

        # 检查权限
        if not check_admin(event):
            await run_monitor_cmd.finish("❌ 权限不足：此命令仅限管理员使用")
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
            await run_monitor_cmd.finish("❌ 无法获取用户信息")

        # 立即执行监控任务
        try:
            from .. import scheduler

            logger.info(f"Operator {user_name} triggered run-once monitoring")

            # 运行一次监控任务
            monitoring_result = await scheduler.run_once()

            # 构建响应消息
            lines = [
                "✅ 监控任务执行完成！",
                f"处理了 {monitoring_result.processed_subsystems}/{monitoring_result.total_subsystems} 个子系统",
            ]

            if monitoring_result.total_new_count > 0:
                lines.append(f"发现 {monitoring_result.total_new_count} 条新邮件")

            if monitoring_result.total_reply_count > 0:
                lines.append(f"发现 {monitoring_result.total_reply_count} 条回复")

            if (
                monitoring_result.total_new_count == 0
                and monitoring_result.total_reply_count == 0
            ):
                lines.append("没有发现新的邮件更新")

            await run_monitor_cmd.finish("\n".join(lines))

        except FinishedException:
            raise  # 重新抛出 FinishedException，这是正常流程
        except Exception as e:
            logger.error(f"Error in run_once monitoring: {e}", exc_info=True)
            await run_monitor_cmd.finish(f"❌ 执行监控任务时发生错误: {str(e)}")
    except FinishedException:
        raise  # 重新抛出 FinishedException，这是正常流程
    except Exception as e:
        logger.error(f"Unexpected error in handle_run_monitor: {e}", exc_info=True)
        await run_monitor_cmd.finish(f"❌ 处理命令时发生错误: {str(e)}")


# 在导入时注册命令元信息（管理员命令）
register_command(
    name="run-monitor",
    usage="/run-monitor",
    description="立即执行一次邮件列表监控任务",
    admin_only=True,
)
