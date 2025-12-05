"""PATCH 卡片过滤服务

提供过滤规则的业务逻辑层接口。
"""

import logging
import re
from typing import List, Optional

from ..db.repo import PatchCardFilterRepository, PatchCardFilterData
from .types import FeedMessage

logger = logging.getLogger(__name__)


class PatchCardFilterService:
    """PATCH 卡片过滤服务类"""

    def __init__(self, filter_repo: PatchCardFilterRepository):
        """初始化服务

        Args:
            filter_repo: 过滤规则仓储实例
        """
        self.filter_repo = filter_repo

    async def should_create_patch_card(
        self, feed_message: FeedMessage, _patch_info
    ) -> tuple[bool, list[str]]:
        """判断是否应该创建 Patch Card 并返回匹配的过滤规则

        在默认 filter（单 Patch 和 Series Patch 的 Cover Letter）基础上，
        应用所有启用的过滤规则。

        逻辑：
        - 如果有 exclusive=true 的规则匹配，则必须匹配才能创建
        - 如果有 exclusive=false 的规则匹配，则所有符合条件的都创建，但标记匹配的规则
        - 如果没有过滤规则，默认允许创建

        Args:
            feed_message: Feed 消息对象
            patch_info: PATCH 信息对象

        Returns:
            (should_create, matched_filter_names) 元组
            - should_create: True 表示应该创建，False 表示不应该创建
            - matched_filter_names: 匹配的过滤规则名称列表
        """
        # 获取所有启用的过滤规则
        filters = await self.filter_repo.find_all(enabled_only=True)

        # 如果没有过滤规则，默认允许创建（保持原有行为）
        if not filters:
            return (True, [])

        matched_filters = []
        has_exclusive_match = False

        # 检查是否满足任一规则
        for filter_data in filters:
            if self._matches_filter(feed_message, _patch_info, filter_data):
                matched_filters.append(filter_data.name)
                if filter_data.exclusive:
                    has_exclusive_match = True
                logger.debug(
                    f"Feed message matches filter '{filter_data.name}' "
                    f"(exclusive={filter_data.exclusive}): "
                    f"{feed_message.message_id_header}"
                )

        # 如果有 exclusive 规则匹配，必须匹配才能创建
        if has_exclusive_match:
            return (True, matched_filters)

        # 如果有非 exclusive 规则匹配，允许创建并标记
        if matched_filters:
            return (True, matched_filters)

        # 检查是否有任何 exclusive 规则（即使未匹配）
        has_exclusive_rules = any(f.exclusive for f in filters)

        # 如果有 exclusive 规则但未匹配，不允许创建
        if has_exclusive_rules:
            logger.debug(
                f"Feed message does not match any exclusive filter: {feed_message.message_id_header}"
            )
            return (False, [])

        # 只有非 exclusive 规则，且未匹配，默认允许创建（保持原有行为）
        return (True, [])

    def _matches_filter(
        self, feed_message: FeedMessage, _patch_info, filter_data: PatchCardFilterData
    ) -> bool:
        """检查 Feed 消息是否匹配过滤规则

        Args:
            feed_message: Feed 消息对象
            patch_info: PATCH 信息对象
            filter_data: 过滤规则数据

        Returns:
            True 表示匹配，False 表示不匹配
        """
        conditions = filter_data.filter_conditions

        def _match_value(val: str, cond) -> bool:
            if isinstance(cond, str):
                if cond.startswith("/") and cond.endswith("/"):
                    return bool(re.search(cond[1:-1], val, re.IGNORECASE))
                return cond.lower() in val.lower()
            if isinstance(cond, list):
                for c in cond:
                    if isinstance(c, str):
                        if c.startswith("/") and c.endswith("/"):
                            if re.search(c[1:-1], val, re.IGNORECASE):
                                return True
                        else:
                            if c.lower() in val.lower():
                                return True
                return False
            return True

        matched = True
        if "author" in conditions:
            matched = matched and _match_value(
                feed_message.author, conditions["author"]
            )
        if "author_email" in conditions:
            matched = matched and _match_value(
                feed_message.author_email, conditions["author_email"]
            )
        if "subject_keywords" in conditions:
            keywords = conditions["subject_keywords"]
            if isinstance(keywords, list):
                matched = matched and any(
                    k.lower() in feed_message.subject.lower() for k in keywords
                )
        if "subject_regex" in conditions:
            pattern = conditions["subject_regex"]
            matched = matched and bool(
                re.search(pattern, feed_message.subject, re.IGNORECASE)
            )
        return bool(matched)

    async def create_filter(
        self,
        name: str,
        filter_conditions: dict,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
        enabled: bool = True,
        exclusive: bool = False,
    ) -> PatchCardFilterData:
        """创建或覆盖过滤规则（同名覆盖）"""
        existing = await self.filter_repo.find_by_name(name)
        if existing:
            data = PatchCardFilterData(
                id=existing.id,
                name=name,
                enabled=enabled,
                exclusive=exclusive,
                filter_conditions=filter_conditions,
                description=(
                    description if description is not None else existing.description
                ),
                created_by=(
                    created_by if created_by is not None else existing.created_by
                ),
            )
            return await self.filter_repo.update(existing.id, data)
        data = PatchCardFilterData(
            id=0,
            name=name,
            enabled=enabled,
            exclusive=exclusive,
            filter_conditions=filter_conditions,
            description=description,
            created_by=created_by,
        )
        return await self.filter_repo.create(data)

    async def list_filters(
        self, enabled_only: bool = False
    ) -> List[PatchCardFilterData]:
        """列出所有过滤规则

        Args:
            enabled_only: 是否只返回启用的规则

        Returns:
            过滤规则列表
        """
        return await self.filter_repo.find_all(enabled_only=enabled_only)

    async def get_filter(
        self, filter_id: Optional[int] = None, name: Optional[str] = None
    ) -> Optional[PatchCardFilterData]:
        """获取过滤规则

        Args:
            filter_id: 过滤规则 ID
            name: 过滤规则名称

        Returns:
            过滤规则数据，如果不存在则返回 None
        """
        if filter_id:
            return await self.filter_repo.find_by_id(filter_id)
        if name:
            return await self.filter_repo.find_by_name(name)
        return None

    async def delete_filter(
        self, filter_id: Optional[int] = None, name: Optional[str] = None
    ) -> bool:
        """删除过滤规则

        Args:
            filter_id: 过滤规则 ID
            name: 过滤规则名称

        Returns:
            是否删除成功
        """
        if name:
            filter_data = await self.filter_repo.find_by_name(name)
            if not filter_data:
                return False
            filter_id = filter_data.id

        if filter_id:
            return await self.filter_repo.delete(filter_id)
        return False

    async def toggle_filter(
        self,
        filter_id: Optional[int] = None,
        name: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> bool:
        """切换过滤规则的启用状态

        Args:
            filter_id: 过滤规则 ID
            name: 过滤规则名称
            enabled: 是否启用（如果为 None，则切换状态）

        Returns:
            是否更新成功
        """
        filter_data = None
        if name:
            filter_data = await self.filter_repo.find_by_name(name)
        elif filter_id:
            filter_data = await self.filter_repo.find_by_id(filter_id)

        if not filter_data:
            return False

        if enabled is None:
            enabled = not filter_data.enabled

        return await self.filter_repo.toggle_enabled(filter_data.id, enabled)
