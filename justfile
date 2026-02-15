set shell := ["cmd", "/c"]

PORT := "8000"

default:
   just --list

# Install all dependencies including dev tools
@dev:
    uv sync

# Install pre-commit hooks
@hooks:
    uvx pre-commit install

# Run formatting and linting checks
@check:
    uvx pre-commit run --all-files

# Start development server with auto-reload
run port=PORT:
    uv run --frozen uvicorn src.main:app --reload --host 0.0.0.0 --port {{port}}

# Sync rules for agents
@agent-rules-sync:
    uv run scripts/agent_rules.py sync

# Run tests
@test:
    uv run --frozen pytest -xvs tests

# Generate database migration
@db-migrate message:
    uv run alembic revision --autogenerate -m "{{message}}"

# Apply database migrations
@db-upgrade:
    uv run alembic upgrade head

# Rollback last migration
@db-downgrade:
    uv run alembic downgrade -1

# Show current migration version
@db-current:
    uv run alembic current

# Show migration history
@db-history:
    uv run alembic history

alias r := run
alias t := test
alias c := check

# Start Celery worker (prefork pool, default concurrency 4)
@celery-worker:
    uv run celery -A src.tasks worker -l info -c 4

# Start Celery worker with specific queue
@celery-worker-q queue:
    uv run celery -A src.tasks worker -l info -c 4 -Q {{queue}}

# Start Celery beat scheduler
@celery-beat:
    uv run celery -A src.tasks beat -l info

# Start Celery flower monitoring UI
@celery-flower:
    uv run celery -A src.tasks flower --port=5555
