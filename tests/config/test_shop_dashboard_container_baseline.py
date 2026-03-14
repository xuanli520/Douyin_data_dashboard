from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_has_shop_dashboard_fallback_dependencies():
    pyproject_data = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = pyproject_data["project"]["dependencies"]
    assert any(dep.startswith("h2") for dep in dependencies)
    assert any(dep.startswith("playwright") for dep in dependencies)


def test_dockerfile_installs_playwright_chromium():
    dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "playwright install --with-deps chromium" in dockerfile


def test_deploy_compose_has_non_sleep_worker_scheduler_default_commands():
    compose = (ROOT / "docker" / "docker-compose.deploy.yml").read_text(
        encoding="utf-8"
    )
    assert "${WORKER_COMMAND:-sleep infinity}" not in compose
    assert "${SCHEDULER_COMMAND:-sleep infinity}" not in compose
    assert "python -m src.tasks.worker" in compose
    assert "python -m src.tasks.beat" in compose
