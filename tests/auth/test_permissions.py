from src.auth.permissions import (
    DataSourcePermission,
    DataImportPermission,
    TaskPermission,
)


def test_data_source_permissions_exist():
    assert hasattr(DataSourcePermission, "VIEW")
    assert hasattr(DataSourcePermission, "CREATE")
    assert hasattr(DataSourcePermission, "UPDATE")
    assert hasattr(DataSourcePermission, "DELETE")


def test_data_source_permission_codes():
    assert DataSourcePermission.VIEW == "data_source:view"
    assert DataSourcePermission.CREATE == "data_source:create"
    assert DataSourcePermission.UPDATE == "data_source:update"
    assert DataSourcePermission.DELETE == "data_source:delete"


def test_data_import_permissions_exist():
    assert hasattr(DataImportPermission, "VIEW")
    assert hasattr(DataImportPermission, "UPLOAD")
    assert hasattr(DataImportPermission, "PARSE")
    assert hasattr(DataImportPermission, "VALIDATE")
    assert hasattr(DataImportPermission, "CONFIRM")


def test_data_import_permission_codes():
    assert DataImportPermission.VIEW == "data_import:view"
    assert DataImportPermission.UPLOAD == "data_import:upload"
    assert DataImportPermission.PARSE == "data_import:parse"
    assert DataImportPermission.VALIDATE == "data_import:validate"
    assert DataImportPermission.CONFIRM == "data_import:confirm"


def test_task_permissions_exist():
    assert hasattr(TaskPermission, "VIEW")
    assert hasattr(TaskPermission, "CREATE")
    assert hasattr(TaskPermission, "EXECUTE")
    assert hasattr(TaskPermission, "CANCEL")


def test_task_permission_codes():
    assert TaskPermission.VIEW == "task:view"
    assert TaskPermission.CREATE == "task:create"
    assert TaskPermission.EXECUTE == "task:execute"
    assert TaskPermission.CANCEL == "task:cancel"
