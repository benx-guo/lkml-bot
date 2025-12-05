"""PATCH 卡片过滤规则仓储类"""

from typing import List, Optional
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PatchCardFilterModel


@dataclass
class PatchCardFilterData:
    """PATCH 卡片过滤规则数据类"""

    id: int
    name: str
    enabled: bool
    exclusive: bool  # 是否独占模式
    filter_conditions: dict
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[object] = None
    updated_at: Optional[object] = None


class PatchCardFilterRepository:
    """PATCH 卡片过滤规则仓储类，提供过滤规则的数据访问操作"""

    def __init__(self, session: AsyncSession):
        """初始化仓储

        Args:
            session: 数据库会话
        """
        self.session = session

    def _model_to_data(self, model: PatchCardFilterModel) -> PatchCardFilterData:
        """将模型转换为数据类

        Args:
            model: PatchCardFilterModel 实例

        Returns:
            PatchCardFilterData 实例
        """
        return PatchCardFilterData(
            id=model.id,
            name=model.name,
            enabled=model.enabled,
            exclusive=model.exclusive,
            filter_conditions=model.filter_conditions or {},
            description=model.description,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _data_to_model(self, data: PatchCardFilterData) -> PatchCardFilterModel:
        """将数据类转换为模型

        Args:
            data: PatchCardFilterData 实例

        Returns:
            PatchCardFilterModel 实例
        """
        return PatchCardFilterModel(
            id=data.id,
            name=data.name,
            enabled=data.enabled,
            filter_conditions=data.filter_conditions,
            description=data.description,
            created_by=data.created_by,
            created_at=data.created_at,
            updated_at=data.updated_at,
        )

    async def create(self, data: PatchCardFilterData) -> PatchCardFilterData:
        """创建过滤规则

        Args:
            data: 过滤规则数据

        Returns:
            创建的过滤规则数据
        """
        model = PatchCardFilterModel(
            name=data.name,
            enabled=data.enabled,
            exclusive=data.exclusive,
            filter_conditions=data.filter_conditions,
            description=data.description,
            created_by=data.created_by,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return self._model_to_data(model)

    async def find_by_id(self, filter_id: int) -> Optional[PatchCardFilterData]:
        """根据 ID 查找过滤规则

        Args:
            filter_id: 过滤规则 ID

        Returns:
            过滤规则数据，如果不存在则返回 None
        """
        result = await self.session.execute(
            select(PatchCardFilterModel).where(PatchCardFilterModel.id == filter_id)
        )
        model = result.scalar_one_or_none()
        return self._model_to_data(model) if model else None

    async def find_by_name(self, name: str) -> Optional[PatchCardFilterData]:
        """根据名称查找过滤规则

        Args:
            name: 过滤规则名称

        Returns:
            过滤规则数据，如果不存在则返回 None
        """
        result = await self.session.execute(
            select(PatchCardFilterModel).where(PatchCardFilterModel.name == name)
        )
        model = result.scalar_one_or_none()
        return self._model_to_data(model) if model else None

    async def find_all(self, enabled_only: bool = False) -> List[PatchCardFilterData]:
        """查找所有过滤规则

        Args:
            enabled_only: 是否只返回启用的规则

        Returns:
            过滤规则数据列表
        """
        query = select(PatchCardFilterModel)
        if enabled_only:
            query = query.where(PatchCardFilterModel.enabled.is_(True))
        query = query.order_by(PatchCardFilterModel.created_at.desc())

        result = await self.session.execute(query)
        models = result.scalars().all()
        return [self._model_to_data(model) for model in models]

    async def update(
        self, filter_id: int, data: PatchCardFilterData
    ) -> Optional[PatchCardFilterData]:
        """更新过滤规则

        Args:
            filter_id: 过滤规则 ID
            data: 更新的数据

        Returns:
            更新后的过滤规则数据，如果不存在则返回 None
        """
        result = await self.session.execute(
            select(PatchCardFilterModel).where(PatchCardFilterModel.id == filter_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None

        model.name = data.name
        model.enabled = data.enabled
        model.exclusive = data.exclusive
        model.filter_conditions = data.filter_conditions
        model.description = data.description

        await self.session.flush()
        await self.session.refresh(model)
        return self._model_to_data(model)

    async def delete(self, filter_id: int) -> bool:
        """删除过滤规则

        Args:
            filter_id: 过滤规则 ID

        Returns:
            是否删除成功
        """
        result = await self.session.execute(
            select(PatchCardFilterModel).where(PatchCardFilterModel.id == filter_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False

        await self.session.delete(model)
        await self.session.flush()
        return True

    async def toggle_enabled(self, filter_id: int, enabled: bool) -> bool:
        """切换过滤规则的启用状态

        Args:
            filter_id: 过滤规则 ID
            enabled: 是否启用

        Returns:
            是否更新成功
        """
        result = await self.session.execute(
            select(PatchCardFilterModel).where(PatchCardFilterModel.id == filter_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False

        model.enabled = enabled
        await self.session.flush()
        return True
