from enum import Enum


class DataSourceStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class DataSourceType(str, Enum):
    DOUYIN_SHOP = "douyin_shop"
    DOUYIN_APP = "douyin_app"
    FILE_IMPORT = "file_import"


class ScrapingRuleStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class TargetType(str, Enum):
    """抖店罗盘主题类型"""

    SHOP_OVERVIEW = "shop_overview"
    TRAFFIC = "traffic"
    PRODUCT = "product"
    LIVE = "live"
    CONTENT_VIDEO = "content_video"
    ORDER_FULFILLMENT = "order_fulfillment"
    AFTERSALE_REFUND = "aftersale_refund"
    CUSTOMER = "customer"
    ADS = "ads"


class Granularity(str, Enum):
    """时间粒度"""

    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class IncrementalMode(str, Enum):
    """增量方式"""

    BY_DATE = "by_date"
    BY_CURSOR = "by_cursor"


class DataLatency(str, Enum):
    """数据延迟假设"""

    T_PLUS_1 = "T+1"
    T_PLUS_2 = "T+2"
