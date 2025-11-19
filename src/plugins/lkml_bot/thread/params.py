"""Thread 相关参数数据类"""

from dataclasses import dataclass
from typing import Optional


@dataclass  # pylint: disable=too-many-instance-attributes
class SeriesCardParams:
    """系列卡片参数"""

    subsystem: str
    message_id: str
    subject: str
    author: str
    url: Optional[str] = None
    series_message_id: Optional[str] = None
    patch_version: Optional[str] = None
    patch_index: Optional[int] = None
    patch_total: Optional[int] = None
    series_info: Optional[dict] = None


@dataclass  # pylint: disable=too-many-instance-attributes
class SubscriptionCardParams:
    """订阅卡片参数"""

    subsystem: str
    message_id: str
    subject: str
    author: str
    url: Optional[str] = None
    series_message_id: Optional[str] = None
    patch_version: Optional[str] = None
    patch_index: Optional[int] = None
    patch_total: Optional[int] = None
    series_info: Optional[dict] = None
