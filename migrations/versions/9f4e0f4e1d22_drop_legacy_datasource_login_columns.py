"""drop legacy datasource login columns

Revision ID: 9f4e0f4e1d22
Revises: 3c4d5e6f7a8b
Create Date: 2026-03-08 09:20:00.000000

"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "9f4e0f4e1d22"
down_revision: Union[str, Sequence[str], None] = "3c4d5e6f7a8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return dict(parsed)
    return {}


def _cookie_string_to_storage_state(cookie_text: str) -> dict[str, Any]:
    cookies: list[dict[str, Any]] = []
    for part in cookie_text.split(";"):
        chunk = part.strip()
        if not chunk or "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        key = name.strip()
        if not key:
            continue
        cookies.append(
            {
                "name": key,
                "value": value.strip(),
                "domain": ".jinritemai.com",
                "path": "/",
            }
        )
    return {"cookies": cookies, "origins": []}


def _parse_storage_state(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        cookies = value.get("cookies")
        origins = value.get("origins")
        if isinstance(cookies, list) and (origins is None or isinstance(origins, list)):
            return {
                "cookies": cookies,
                "origins": origins if isinstance(origins, list) else [],
            }
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return _cookie_string_to_storage_state(raw)
        return _parse_storage_state(parsed)
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        normalized = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def upgrade() -> None:
    connection = op.get_bind()
    dialect_name = connection.dialect.name
    rows = connection.execute(
        sa.text(
            """
            SELECT
                id,
                extra_config,
                cookies,
                api_key,
                api_secret,
                access_token,
                refresh_token,
                token_expires_at
            FROM data_sources
            """
        )
    ).mappings()

    for row in rows:
        extra_config = _as_dict(row.get("extra_config"))
        login_state = _as_dict(extra_config.get("shop_dashboard_login_state"))
        credentials = _as_dict(login_state.get("credentials"))

        api_key = row.get("api_key")
        api_secret = row.get("api_secret")
        access_token = row.get("access_token")
        refresh_token = row.get("refresh_token")
        token_expires_at = row.get("token_expires_at")

        if api_key:
            credentials.setdefault("api_key", str(api_key))
        if api_secret:
            credentials.setdefault("api_key_password", str(api_secret))
        if access_token:
            credentials.setdefault("access_token", str(access_token))
        if refresh_token:
            credentials.setdefault("refresh_token", str(refresh_token))
        if token_expires_at:
            credentials.setdefault(
                "token_expires_at",
                token_expires_at.isoformat()
                if isinstance(token_expires_at, datetime)
                else str(token_expires_at),
            )

        storage_state = _parse_storage_state(login_state.get("storage_state"))
        if storage_state is None:
            storage_state = _parse_storage_state(row.get("cookies"))

        next_login_state: dict[str, Any] = dict(login_state)
        if storage_state is not None:
            next_login_state["storage_state"] = storage_state
        if credentials:
            next_login_state["credentials"] = credentials
        state_version = next_login_state.get("state_version")
        next_login_state["state_version"] = (
            str(state_version).strip() if state_version else "v1"
        )

        extra_config["shop_dashboard_login_state"] = next_login_state

        if dialect_name == "postgresql":
            update_stmt = sa.text(
                """
                UPDATE data_sources
                SET extra_config = CAST(:extra_config AS JSONB)
                WHERE id = :id
                """
            )
        else:
            update_stmt = sa.text(
                "UPDATE data_sources SET extra_config = :extra_config WHERE id = :id"
            )
        connection.execute(
            update_stmt,
            {
                "id": row["id"],
                "extra_config": json.dumps(extra_config, ensure_ascii=False),
            },
        )

    op.drop_column("data_sources", "cookies")
    op.drop_column("data_sources", "proxy")
    op.drop_column("data_sources", "api_key")
    op.drop_column("data_sources", "api_secret")
    op.drop_column("data_sources", "access_token")
    op.drop_column("data_sources", "refresh_token")
    op.drop_column("data_sources", "token_expires_at")


def downgrade() -> None:
    connection = op.get_bind()

    op.add_column("data_sources", sa.Column("cookies", sa.Text(), nullable=True))
    op.add_column(
        "data_sources", sa.Column("proxy", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "data_sources", sa.Column("api_key", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "data_sources", sa.Column("api_secret", sa.String(length=255), nullable=True)
    )
    op.add_column("data_sources", sa.Column("access_token", sa.Text(), nullable=True))
    op.add_column("data_sources", sa.Column("refresh_token", sa.Text(), nullable=True))
    op.add_column(
        "data_sources",
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    rows = connection.execute(
        sa.text("SELECT id, extra_config FROM data_sources")
    ).mappings()

    for row in rows:
        extra_config = _as_dict(row.get("extra_config"))
        login_state = _as_dict(extra_config.get("shop_dashboard_login_state"))
        credentials = _as_dict(login_state.get("credentials"))

        storage_state = _parse_storage_state(login_state.get("storage_state"))
        cookies = (
            json.dumps(storage_state, ensure_ascii=False)
            if storage_state is not None
            else None
        )

        api_secret = credentials.get("api_key_password") or credentials.get(
            "api_secret"
        )
        token_expires_at = _parse_datetime(credentials.get("token_expires_at"))

        connection.execute(
            sa.text(
                """
                UPDATE data_sources
                SET
                    cookies = :cookies,
                    proxy = :proxy,
                    api_key = :api_key,
                    api_secret = :api_secret,
                    access_token = :access_token,
                    refresh_token = :refresh_token,
                    token_expires_at = :token_expires_at
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "cookies": cookies,
                "proxy": extra_config.get("proxy"),
                "api_key": credentials.get("api_key"),
                "api_secret": api_secret,
                "access_token": credentials.get("access_token")
                or login_state.get("access_token"),
                "refresh_token": credentials.get("refresh_token")
                or login_state.get("refresh_token"),
                "token_expires_at": token_expires_at,
            },
        )
