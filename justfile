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

@ci-gate:
    just arch-check
    uv run --frozen pytest -q
    just check

@migration-ci:
    uv run alembic upgrade head
    uv run alembic current --check-heads
    uv run alembic check
    uv run alembic downgrade base
    uv run alembic upgrade head
    uv run alembic current --check-heads
    uv run alembic check

@arch-check:
    uv run --frozen pytest -q tests/architecture/test_layer_boundaries.py

# Start development server with auto-reload
run port=PORT:
    uv run --frozen uvicorn src.main:app --reload --host 0.0.0.0 --port {{port}}

# Sync rules for agents
@agent-rules-sync:
    uv run scripts/agent_rules.py sync

# Run tests
@test:
    uv run --frozen pytest -xvs tests

# Start all funboost workers
@funboost-worker:
    uv run --frozen python -m src.tasks.worker

# Start a single funboost queue worker
@funboost-worker-q queue:
    uv run --frozen python -m src.tasks.worker --queue {{queue}}

# Start funboost beat scheduler
@funboost-beat:
    uv run --frozen python -m src.tasks.beat

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
