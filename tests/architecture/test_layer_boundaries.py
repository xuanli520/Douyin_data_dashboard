import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def _is_type_checking_guard(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    if isinstance(node, ast.Attribute):
        return node.attr == "TYPE_CHECKING"
    if isinstance(node, ast.BoolOp):
        return any(_is_type_checking_guard(value) for value in node.values)
    return False


class _ImportCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.modules: set[str] = set()

    def visit_If(self, node: ast.If) -> None:
        if _is_type_checking_guard(node.test):
            for child in node.orelse:
                self.visit(child)
            return
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            module = f"{'.' * node.level}{node.module}" if node.level else node.module
            self.modules.add(module)
            return
        if node.level:
            self.modules.add("." * node.level)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.modules.add(alias.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    visit_AsyncFunctionDef = visit_FunctionDef


def _imports_from_source(source: str) -> set[str]:
    collector = _ImportCollector()
    collector.visit(ast.parse(source))
    return collector.modules


def _imports(path: str) -> set[str]:
    return _imports_from_source(_read(path))


def _is_forbidden_module(module: str, prefix: str) -> bool:
    normalized = prefix.rstrip(".")
    return module == normalized or module.startswith(f"{normalized}.")


def _assert_no_forbidden_imports(
    path: str, forbidden_prefixes: tuple[str, ...]
) -> None:
    modules = _imports(path)
    forbidden = [
        module
        for module in modules
        if any(_is_forbidden_module(module, prefix) for prefix in forbidden_prefixes)
    ]
    assert not forbidden, f"{path} contains forbidden imports: {forbidden}"


def test_import_collector_ignores_type_checking_branch() -> None:
    modules = _imports_from_source(
        """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.data_source.models import DataSource
else:
    from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
"""
    )
    assert "src.domains.data_source.models" not in modules
    assert "src.scrapers.shop_dashboard.runtime" in modules


def test_data_source_model_must_not_hold_collection_target_fields() -> None:
    content = _read("src/domains/data_source/models.py")
    assert "shop_id:" not in content
    assert "account_name:" not in content


def test_beat_should_not_depend_on_data_source_models() -> None:
    _assert_no_forbidden_imports(
        "src/tasks/beat.py",
        ("src.domains.data_source.models",),
    )


def test_data_source_service_should_not_handle_rule_or_trigger_logic() -> None:
    content = _read("src/domains/data_source/services.py")
    assert "create_scraping_rule(" not in content
    assert "list_scraping_rules(" not in content
    assert "list_scraping_rules_paginated(" not in content
    assert "get_scraping_rule(" not in content
    assert "update_scraping_rule(" not in content
    assert "delete_scraping_rule(" not in content
    assert "trigger_collection(" not in content


def test_domains_task_services_must_not_import_tasks() -> None:
    _assert_no_forbidden_imports(
        "src/domains/task/services.py",
        ("src.tasks",),
    )


def test_domains_task_schemas_must_not_import_tasks() -> None:
    _assert_no_forbidden_imports(
        "src/domains/task/schemas.py",
        ("src.tasks",),
    )


def test_application_plan_builder_must_not_import_tasks() -> None:
    _assert_no_forbidden_imports(
        "src/application/collection/plan_builder.py",
        ("src.tasks",),
    )
