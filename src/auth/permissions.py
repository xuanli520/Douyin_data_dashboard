class DataSourcePermission:
    VIEW = "data_source:view"
    CREATE = "data_source:create"
    UPDATE = "data_source:update"
    DELETE = "data_source:delete"


class DataImportPermission:
    VIEW = "data_import:view"
    UPLOAD = "data_import:upload"
    PARSE = "data_import:parse"
    VALIDATE = "data_import:validate"
    CONFIRM = "data_import:confirm"
    CANCEL = "data_import:cancel"


class TaskPermission:
    VIEW = "task:view"
    CREATE = "task:create"
    EXECUTE = "task:execute"
    CANCEL = "task:cancel"


class AnalyticsPermission:
    VIEW = "analytics:view"


class ShopPermission:
    VIEW = "shop:view"
    SCORE = "shop:score"


class MetricPermission:
    VIEW = "metric:view"


class ExperiencePermission:
    VIEW = "experience:view"


class DashboardPermission:
    VIEW = "dashboard:view"


class ShopDashboardPermission:
    TRIGGER = "shop_dashboard:trigger"
    STATUS = "shop_dashboard:status"
    QUERY = "shop_dashboard:query"


class OrderPermission:
    VIEW = "order:view"


class ProductPermission:
    VIEW = "product:view"


class SalePermission:
    VIEW = "sale:view"


class AfterSalePermission:
    VIEW = "after_sale:view"


class ReportPermission:
    VIEW = "report:view"
    GENERATE = "report:generate"
    DOWNLOAD = "report:download"


class ExportPermission:
    VIEW = "export:view"
    CREATE = "export:create"
    DOWNLOAD = "export:download"


class SchedulePermission:
    VIEW = "schedule:view"
    UPDATE = "schedule:update"
    DELETE = "schedule:delete"


class AnalysisPermission:
    VIEW = "analysis:view"


class AlertPermission:
    VIEW = "alert:view"
    ASSIGN = "alert:assign"
    RESOLVE = "alert:resolve"
    IGNORE = "alert:ignore"
    RULE = "alert:rule"
    ACKNOWLEDGE = "alert:acknowledge"


class NotificationPermission:
    VIEW = "notification:view"
    TEST = "notification:test"


class SystemPermission:
    CONFIG = "system:config"
    HEALTH = "system:health"
    BACKUP = "system:backup"
    CLEANUP = "system:cleanup"
    USER_SETTINGS = "system:user_settings"


class AuditPermission:
    READ = "audit:read"
    EXPORT = "audit:export"
