"""PATCH 卡片过滤规则命令模块"""

from nonebot import on_message
from nonebot.adapters import Event, Message
from nonebot.exception import FinishedException
from nonebot.log import logger
from nonebot.params import EventMessage
from nonebot.rule import to_me

from lkml.db.repo import PatchCardFilterRepository
from lkml.service.patch_card_filter_service import PatchCardFilterService
from ..shared import (
    extract_command,
    get_user_info_or_finish,
    register_command,
    check_admin,
    get_database,
)

# 仅当消息 @ 到机器人，并且以 "/filter" 开头时处理
FilterCmd = on_message(rule=to_me(), priority=50, block=False)


def _convert_scalar(s: str):
    try:
        return int(s)
    except ValueError:
        return s


def _parse_condition_tokens(tokens: list) -> dict:
    result = {}
    for t in tokens:
        if "=" not in t:
            continue
        k, v = t.split("=", 1)
        if "," in v:
            result[k] = [_convert_scalar(x) for x in [i for i in v.split(",") if i]]
        else:
            result[k] = _convert_scalar(v)
    return result


def _format_conditions(conditions: dict) -> str:
    lines = []
    for k, v in conditions.items():
        if isinstance(v, list):
            val = ", ".join(str(x) for x in v)
        else:
            val = str(v)
        lines.append(f"{k}: {val}")
    return "\n".join(lines)


@FilterCmd.handle()
async def handle_filter(event: Event, message: Message = EventMessage()):
    """处理过滤规则命令

    支持的子命令：
    - /filter add <name> <conditions> [description] - 添加过滤规则
    - /filter list [--enabled-only] - 列出所有过滤规则
    - /filter show <name|id> - 显示过滤规则详情
    - /filter remove <name|id> - 删除过滤规则
    - /filter enable <name|id> - 启用过滤规则
    - /filter disable <name|id> - 禁用过滤规则
    """
    try:
        if not check_admin(event):
            await FilterCmd.finish("❌ 此命令仅管理员可用")
            return

        text = message.extract_plain_text().strip()
        logger.info(f"Filter command handler triggered, text: '{text}'")

        command_text = extract_command(text, "/filter")
        if command_text is None:
            return

        parts = command_text.split()
        if len(parts) < 2:
            await FilterCmd.finish(
                "filter: 缺少子命令\n"
                "用法:\n"
                "  /filter add <name> <conditions> [--exclusive] [description] - 添加过滤规则\n"
                "  /filter list [--enabled-only] - 列出所有过滤规则\n"
                "  /filter show <name|id> - 显示过滤规则详情\n"
                "  /filter remove <name|id> - 删除过滤规则\n"
                "  /filter enable <name|id> - 启用过滤规则\n"
                "  /filter disable <name|id> - 禁用过滤规则\n"
                "\n"
                "模式说明:\n"
                "  --exclusive: 独占模式，只允许匹配此规则的 Patch Card 创建\n"
                "  默认（无 --exclusive）: 高亮模式，所有 Patch Card 都创建，但匹配的会高亮显示\n"
                "\n"
                "条件格式（key=value，逗号分隔列表）：\n"
                "  示例: subsystem=rust-for-linux subject_keywords=Rust,driver min_patch_total=3\n"
            )
            return

        subcommand = parts[1].lower()
        database = get_database()
        if not database:
            await FilterCmd.finish("❌ 数据库未初始化")
            return

        async with database.get_db_session() as session:
            filter_repo = PatchCardFilterRepository(session)
            filter_service = PatchCardFilterService(filter_repo)

            async def call_add():
                user_id, user_name = await get_user_info_or_finish(event, FilterCmd)
                return await _handle_add(filter_service, parts, user_id, user_name)

            handlers = {
                "add": call_add,
                "list": lambda: _handle_list(filter_service, parts),
                "show": lambda: _handle_show(filter_service, parts),
                "remove": lambda: _handle_remove(filter_service, parts),
                "enable": lambda: _handle_toggle(filter_service, parts, True),
                "disable": lambda: _handle_toggle(filter_service, parts, False),
            }

            func = handlers.get(subcommand)
            resp_msg = await func() if func else f"❌ 未知子命令: {subcommand}"

        if resp_msg:
            await FilterCmd.finish(resp_msg)

    except FinishedException:
        raise
    except (ValueError, RuntimeError, AttributeError) as e:
        logger.error(f"Error in filter command: {e}", exc_info=True)
        await FilterCmd.finish(f"❌ 处理命令时发生错误: {str(e)}")


def _parse_conditions_and_description(parts: list, start_idx: int):
    exclusive = False
    description_parts = []
    conditions = {}
    i = start_idx
    flags = {"--exclusive", "-e"}
    while i < len(parts):
        part = parts[i]
        if part in flags:
            exclusive = True
            i += 1
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            acc = [v]
            j = i + 1
            while j < len(parts) and ("=" not in parts[j]) and (parts[j] not in flags):
                acc.append(parts[j])
                j += 1
            joined = " ".join(acc)
            if "," in joined:
                items = [s.strip() for s in joined.split(",") if s.strip()]
                conditions[k] = [_convert_scalar(x) for x in items]
            else:
                conditions[k] = _convert_scalar(joined.strip())
            i = j
            continue
        description_parts.append(part)
        i += 1
    description = " ".join(description_parts) if description_parts else None
    return conditions, exclusive, description


async def _handle_add(
    filter_service: PatchCardFilterService, parts: list, user_id: str, user_name: str
) -> str:
    """处理添加过滤规则命令（返回文本，避免在 DB 会话内 finish 导致回滚）"""
    if len(parts) < 4:
        return (
            "❌ 用法: /filter add <name> <conditions> [--exclusive] [description]\n"
            "示例: /filter add rust-filter subsystem=rust-for-linux subject_keywords=Rust,driver min_patch_total=3\n"
            "示例（独占模式）: /filter add rust-filter subsystem=rust-for-linux --exclusive 'Only Rust patches'"
        )

    name = parts[2]

    conditions, exclusive, description = _parse_conditions_and_description(parts, 3)

    if not conditions:
        return "❌ 条件缺失，使用 key=value 形式，例如 subsystem=rust-for-linux"

    try:
        filter_data = await filter_service.create_filter(
            name=name,
            filter_conditions=conditions,
            description=description,
            created_by=f"{user_name} ({user_id})",
            enabled=True,
            exclusive=exclusive,
        )
        return (
            f"✅ 已添加过滤规则: {filter_data.name}\n"
            f"ID: {filter_data.id}\n"
            f"状态: {'启用' if filter_data.enabled else '禁用'}\n"
            f"模式: {'独占模式（只允许匹配的创建）' if exclusive else '高亮模式（所有都创建但高亮匹配的）'}"
        )
    except (RuntimeError, ValueError, AttributeError) as e:
        logger.error(f"Failed to create filter: {e}", exc_info=True)
        return f"❌ 创建过滤规则失败: {str(e)}"


async def _handle_list(filter_service: PatchCardFilterService, parts: list) -> str:
    """处理列出过滤规则命令（返回文本）"""
    enabled_only = "--enabled-only" in parts or "-e" in parts

    try:
        filters = await filter_service.list_filters(enabled_only=enabled_only)
        if not filters:
            return "📋 没有找到过滤规则"

        lines = ["📋 过滤规则列表:\n"]
        for f in filters:
            status = "✅ 启用" if f.enabled else "❌ 禁用"
            mode = "🔒 独占" if f.exclusive else "⭐ 高亮"
            lines.append(f"{f.id}. {f.name} - {status} - {mode}")
            if f.description:
                lines.append(f"   描述: {f.description}")
            lines.append("")

        return "\n".join(lines)
    except (RuntimeError, ValueError, AttributeError) as e:
        logger.error(f"Failed to list filters: {e}", exc_info=True)
        return f"❌ 列出过滤规则失败: {str(e)}"


async def _handle_show(filter_service: PatchCardFilterService, parts: list) -> str:
    """处理显示过滤规则详情命令（返回文本）"""
    if len(parts) < 3:
        return "❌ 用法: /filter show <name|id>"

    identifier = parts[2]

    try:
        # 尝试作为 ID 解析
        filter_id = None
        try:
            filter_id = int(identifier)
        except ValueError:
            pass

        filter_data = await filter_service.get_filter(
            filter_id=filter_id, name=identifier if not filter_id else None
        )

        if not filter_data:
            return f"❌ 未找到过滤规则: {identifier}"

        status = "✅ 启用" if filter_data.enabled else "❌ 禁用"
        mode = (
            "🔒 独占模式（只允许匹配的创建）"
            if filter_data.exclusive
            else "⭐ 高亮模式（所有都创建但高亮匹配的）"
        )
        lines = [
            f"📋 过滤规则详情: {filter_data.name}",
            f"ID: {filter_data.id}",
            f"状态: {status}",
            f"模式: {mode}",
        ]

        if filter_data.description:
            lines.append(f"描述: {filter_data.description}")

        if filter_data.created_by:
            lines.append(f"创建者: {filter_data.created_by}")

        lines.append("\n过滤条件:")
        lines.append(_format_conditions(filter_data.filter_conditions))

        return "\n".join(lines)
    except (RuntimeError, ValueError, AttributeError) as e:
        logger.error(f"Failed to show filter: {e}", exc_info=True)
        return f"❌ 显示过滤规则失败: {str(e)}"


async def _handle_remove(filter_service: PatchCardFilterService, parts: list) -> str:
    """处理删除过滤规则命令（返回文本，避免事务回滚）"""
    if len(parts) < 3:
        return "❌ 用法: /filter remove <name|id>"

    identifier = parts[2]

    try:
        filter_id = None
        try:
            filter_id = int(identifier)
        except ValueError:
            pass

        success = await filter_service.delete_filter(
            filter_id=filter_id, name=identifier if not filter_id else None
        )

        if success:
            return f"✅ 已删除过滤规则: {identifier}"
        return f"❌ 未找到过滤规则: {identifier}"
    except (RuntimeError, ValueError, AttributeError) as e:
        logger.error(f"Failed to remove filter: {e}", exc_info=True)
        return f"❌ 删除过滤规则失败: {str(e)}"


async def _handle_toggle(
    filter_service: PatchCardFilterService, parts: list, enabled: bool
) -> str:
    """处理启用/禁用过滤规则命令（返回文本，避免事务回滚）"""
    if len(parts) < 3:
        return f"❌ 用法: /filter {'enable' if enabled else 'disable'} <name|id>"

    identifier = parts[2]

    try:
        filter_id = None
        try:
            filter_id = int(identifier)
        except ValueError:
            pass

        success = await filter_service.toggle_filter(
            filter_id=filter_id,
            name=identifier if not filter_id else None,
            enabled=enabled,
        )

        if success:
            action = "启用" if enabled else "禁用"
            return f"✅ 已{action}过滤规则: {identifier}"
        return f"❌ 未找到过滤规则: {identifier}"
    except (RuntimeError, ValueError, AttributeError) as e:
        logger.error(f"Failed to toggle filter: {e}", exc_info=True)
        action = "启用" if enabled else "禁用"
        return f"❌ {action}过滤规则失败: {str(e)}"


# 在导入时注册命令元信息（管理员命令）
register_command(
    name="filter",
    usage="/filter <add|list|show|remove|enable|disable> [参数...]",
    description="管理 PATCH 卡片过滤规则（仅管理员）",
    admin_only=True,
)
