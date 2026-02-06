from src.auth.role_permissions import ROLE_PERMISSIONS


def test_role_permissions_structure():
    assert "super_admin" in ROLE_PERMISSIONS
    assert "admin" in ROLE_PERMISSIONS
    assert "user" in ROLE_PERMISSIONS


def test_super_admin_has_all_permissions():
    perms = ROLE_PERMISSIONS["super_admin"]
    assert "data_source:view" in perms
    assert "data_source:create" in perms
    assert "data_source:update" in perms
    assert "data_source:delete" in perms
    assert "data_import:view" in perms
    assert "data_import:upload" in perms
    assert "data_import:parse" in perms
    assert "data_import:validate" in perms
    assert "data_import:confirm" in perms
    assert "task:view" in perms
    assert "task:create" in perms
    assert "task:execute" in perms
    assert "task:cancel" in perms


def test_admin_permissions():
    perms = ROLE_PERMISSIONS["admin"]
    assert "data_source:view" in perms
    assert "data_source:create" in perms
    assert "data_source:update" not in perms
    assert "data_source:delete" not in perms


def test_user_permissions():
    perms = ROLE_PERMISSIONS["user"]
    assert "data_import:view" in perms
    assert "task:view" in perms
    assert "data_source:create" not in perms
    assert "data_import:upload" not in perms
