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
