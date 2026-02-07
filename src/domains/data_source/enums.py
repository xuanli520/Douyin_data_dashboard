from enum import Enum


class DataSourceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ERROR = "ERROR"


class DataSourceType(str, Enum):
    DOUYIN_SHOP = "DOUYIN_SHOP"
    DOUYIN_APP = "DOUYIN_APP"
    FILE_IMPORT = "FILE_IMPORT"
    SELF_HOSTED = "SELF_HOSTED"


class ScrapingRuleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class TargetType(str, Enum):
    """抖店罗盘主题类型"""

    SHOP_OVERVIEW = "SHOP_OVERVIEW"
    TRAFFIC = "TRAFFIC"
    PRODUCT = "PRODUCT"
    LIVE = "LIVE"
    CONTENT_VIDEO = "CONTENT_VIDEO"
    ORDER_FULFILLMENT = "ORDER_FULFILLMENT"
    AFTERSALE_REFUND = "AFTERSALE_REFUND"
    CUSTOMER = "CUSTOMER"
    ADS = "ADS"


class Granularity(str, Enum):
    """时间粒度"""

    HOUR = "HOUR"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"


class IncrementalMode(str, Enum):
    """增量方式"""

    BY_DATE = "BY_DATE"
    BY_CURSOR = "BY_CURSOR"


class DataLatency(str, Enum):
    """数据延迟假设"""

    REALTIME = "REALTIME"
    T_PLUS_1 = "T+1"
    T_PLUS_2 = "T+2"
    T_PLUS_3 = "T+3"
