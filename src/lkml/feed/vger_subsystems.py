"""Vger 子系统来源

提供统一函数以获取可用的 vger 子系统名称列表，至于数据从哪里来（内存、配置、数据库、
外部服务等）由实现决定，调用方无需关心。
"""

from typing import List


def get_vger_subsystems() -> List[str]:
    """获取 vger 子系统列表

    Returns:
        子系统名称列表，例如: ["lkml", "netdev", "dri-devel", ...]

    TODO:
        根据你的运行环境，从合适的数据源读取（如内存、Redis、数据库或配置文件）。
        如果暂时没有数据源，返回空列表即可。
    """
    return []
