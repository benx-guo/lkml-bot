"""配置模块（配置接口和实现）"""

from typing import List, Optional, Protocol, Callable
from nonebot.log import logger
from pydantic import BaseModel

__all__ = ["Config", "LKMLConfig", "set_config", "get_config"]


class Config(Protocol):
    """配置接口（使用 Protocol 避免与 Pydantic 字段冲突）"""

    @property
    def database_url(self) -> str:
        """数据库连接URL"""
        ...

    def get_supported_subsystems(self) -> List[str]:
        """获取支持的子系统列表（动态合并 vger 缓存和手动配置）"""
        ...

    @property
    def max_news_count(self) -> int:
        """最大新闻数量"""
        ...

    @property
    def monitoring_interval(self) -> int:
        """监控任务执行周期（秒）"""
        ...


# 全局配置实例（由插件层注入）
_config: Optional[Config] = None


def set_config(config: Config) -> None:
    """设置配置实例"""
    global _config
    _config = config


def get_config() -> Config:
    """获取配置实例"""
    if _config is None:
        raise RuntimeError("Config not initialized. Call set_config() first.")
    # 验证配置对象的完整性
    config = _config
    # 注意：使用 getattr 安全获取属性，避免属性不存在时的错误
    database_url = getattr(config, "database_url", None)
    max_news_count = getattr(config, "max_news_count", None)
    monitoring_interval = getattr(config, "monitoring_interval", None)

    if database_url is None:
        raise RuntimeError(
            "Config.database_url is None. Configuration may not be properly initialized."
        )
    if max_news_count is None:
        raise RuntimeError(
            "Config.max_news_count is None. Configuration may not be properly initialized."
        )
    if monitoring_interval is None:
        raise RuntimeError(
            "Config.monitoring_interval is None. Configuration may not be properly initialized."
        )
    return config


class LKMLConfig(BaseModel):
    """LKML 配置实现（与机器人框架无关，实现 Config Protocol）

    支持的子系统由两部分组成：
    1. 从 vger 服务器缓存自动获取的内核子系统（存储在缓存中）
    2. 手动配置的额外子系统（通过 LKML_MANUAL_SUBSYSTEMS 环境变量）
    """

    database_url: str = "sqlite+aiosqlite:///./lkml_bot.db"
    manual_subsystems: List[str] = []  # 手动配置的额外子系统
    max_news_count: int = 20
    monitoring_interval: int = 300  # 监控任务执行周期（秒），默认 5 分钟
    # Debug/开发辅助：ISO8601 字符串覆盖 last_update_dt（如 2025-11-03T12:00:00Z）
    last_update_dt_override_iso: Optional[str] = None
    _vger_subsystems_getter: Optional[Callable[[], List[str]]] = (
        None  # 用于获取 vger 缓存中的子系统
    )

    class Config:
        arbitrary_types_allowed = True

    def set_vger_subsystems_getter(self, getter: Callable[[], List[str]]) -> None:
        """设置用于获取 vger 子系统缓存的函数

        Bot 的服务器缓存会存储所有从 vger 获取的内核子系统信息（键值对格式）。
        通过此方法注册获取函数，函数应返回从服务器缓存中读取的子系统名称列表。

        Args:
            getter: 返回 vger 子系统列表的函数。函数应该从服务器缓存读取数据并返回子系统名称列表
                   例如: ["lkml", "netdev", "dri-devel", ...]

        示例:
            def get_vger_subsystems_from_cache() -> List[str]:
                # 从服务器缓存获取子系统列表
                # 实现从缓存读取逻辑
                return ["lkml", "netdev", "dri-devel"]

            config.set_vger_subsystems_getter(get_vger_subsystems_from_cache)
        """
        self._vger_subsystems_getter = getter

    def get_supported_subsystems(self) -> List[str]:
        """获取支持的子系统列表（动态合并 vger 缓存和手动配置）

        Returns:
            合并后的子系统列表（去重并排序）
        """
        # 从 vger 缓存获取内核子系统
        vger_subsystems = []
        if self._vger_subsystems_getter:
            try:
                result = self._vger_subsystems_getter()
                # 确保返回的是列表，如果返回 None 则使用空列表
                if result is not None:
                    vger_subsystems = result if isinstance(result, list) else []
            except Exception as e:
                logger.warning(f"Failed to get vger subsystems: {e}")

        # 确保 manual_subsystems 不为 None
        manual_subsystems = (
            self.manual_subsystems if self.manual_subsystems is not None else []
        )

        # 合并并去重
        all_subsystems = list(set(vger_subsystems + manual_subsystems))
        return sorted(all_subsystems)

    @classmethod
    def from_env(cls, database_url: Optional[str] = None) -> "LKMLConfig":
        """从环境变量创建配置

        注意：如果没有提供环境变量，将使用类字段的默认值。
        这样可以通过设置环境变量来测试不同的配置值。
        """
        import os

        # 处理手动配置的子系统（LKML_MANUAL_SUBSYSTEMS）
        manual_subsystems_env = os.getenv("LKML_MANUAL_SUBSYSTEMS")
        if manual_subsystems_env and manual_subsystems_env.strip():
            manual_subsystems = [
                s.strip() for s in manual_subsystems_env.split(",") if s.strip()
            ]
        else:
            manual_subsystems = []

        # 获取 database_url（优先使用参数，其次环境变量，最后使用类默认值）
        if database_url and database_url.strip():
            final_database_url = database_url
        else:
            database_url_env = os.getenv("LKML_DATABASE_URL")
            if database_url_env and database_url_env.strip():
                final_database_url = database_url_env
            else:
                # 使用类定义的默认值
                final_database_url = None  # 将使用类字段的默认值

        # 获取 max_news_count（从环境变量读取，如果没有则使用类默认值）
        max_news_count = None
        max_news_count_env = os.getenv("LKML_MAX_NEWS_COUNT")
        if max_news_count_env and max_news_count_env.strip():
            try:
                max_news_count = int(max_news_count_env)
            except ValueError:
                max_news_count = None  # 使用类默认值

        # 获取 monitoring_interval（从环境变量读取，如果没有则使用类默认值）
        monitoring_interval = None
        monitoring_interval_env = os.getenv("LKML_MONITORING_INTERVAL")
        if monitoring_interval_env and monitoring_interval_env.strip():
            try:
                monitoring_interval = int(monitoring_interval_env)
                # 最小周期为 60 秒（1 分钟），避免过于频繁的请求
                if monitoring_interval < 60:
                    monitoring_interval = 60
            except ValueError:
                monitoring_interval = None  # 使用类默认值

        # Debug: 显式覆盖 last_update_dt（ISO8601 字符串，例如 2025-11-03T12:00:00Z）
        last_update_dt_override_iso_env = os.getenv("LKML_LAST_UPDATE_AT")
        last_update_dt_override_iso: Optional[str] = None
        if last_update_dt_override_iso_env and last_update_dt_override_iso_env.strip():
            last_update_dt_override_iso = last_update_dt_override_iso_env.strip()

        # 构建配置对象
        # 只传递明确设置的值，未设置的将使用类字段的默认值
        config_dict = {
            "manual_subsystems": manual_subsystems,
        }

        # 如果提供了 database_url，使用提供的值；否则使用类默认值
        if final_database_url:
            config_dict["database_url"] = final_database_url

        # 如果环境变量提供了值，使用环境变量的值；否则使用类默认值
        if max_news_count is not None:
            config_dict["max_news_count"] = max_news_count

        if monitoring_interval is not None:
            config_dict["monitoring_interval"] = monitoring_interval

        if last_update_dt_override_iso is not None:
            config_dict["last_update_dt_override_iso"] = last_update_dt_override_iso

        return cls(**config_dict)
