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


class ReportPermission:
    VIEW = "report:view"


class SchedulePermission:
    VIEW = "schedule:view"


class AnalysisPermission:
    VIEW = "analysis:view"


class AlertPermission:
    VIEW = "alert:view"
