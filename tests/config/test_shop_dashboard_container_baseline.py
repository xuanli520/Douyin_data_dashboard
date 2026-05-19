from pathlib import Path
import json
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_has_shop_dashboard_http_dependencies():
    pyproject_data = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = pyproject_data["project"]["dependencies"]
    assert any(dep.startswith("h2") for dep in dependencies)
    assert not any(dep.startswith("playwright") for dep in dependencies)


def test_package_json_has_playwright_cli_dependency():
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package_json["dependencies"]["@playwright/cli"] == "0.1.13"


def test_dockerfile_installs_playwright_cli_browser():
    dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "npm ci" in dockerfile
    assert "PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright" in dockerfile
    assert "PLAYWRIGHT_CFT_MIRROR=https://cdn.npmmirror.com/binaries/chrome-for-testing" in dockerfile
    assert "npm config set registry https://registry.npmmirror.com" in dockerfile
    assert "npx playwright install-deps chromium" in dockerfile
    assert "chrome-linux64.zip" in dockerfile
    assert "chrome-headless-shell-linux64.zip" in dockerfile


def test_deploy_compose_has_non_sleep_worker_scheduler_default_commands():
    compose = (ROOT / "docker" / "docker-compose.deploy.yml").read_text(
        encoding="utf-8"
    )
    assert "${WORKER_COMMAND:-sleep infinity}" not in compose
    assert "${SCHEDULER_COMMAND:-sleep infinity}" not in compose
    assert "python -m src.tasks.worker" in compose
    assert "python -m src.tasks.beat" in compose
