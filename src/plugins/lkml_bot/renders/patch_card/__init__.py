"""PatchCard 渲染模块

只包含渲染器，业务逻辑已移至 lkml.service 层。
"""

from .renderer import PatchCardRenderer

__all__ = [
    "PatchCardRenderer",
]
