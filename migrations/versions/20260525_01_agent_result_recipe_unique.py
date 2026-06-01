from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260525_01"
down_revision: Union[str, Sequence[str], None] = "20260521_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE_NAME = "agent_collection_results"
_UNIQUE_NAME = "ux_agent_collection_result"
_OLD_COLUMNS = ["namespace", "resource_key", "resource_date"]
_NEW_COLUMNS = ["namespace", "resource_key", "resource_date", "recipe_id"]


def upgrade() -> None:
    _replace_unique(_OLD_COLUMNS, _NEW_COLUMNS)


def downgrade() -> None:
    _replace_unique(_NEW_COLUMNS, _OLD_COLUMNS)


def _replace_unique(from_columns: list[str], to_columns: list[str]) -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(_TABLE_NAME):
        return
    current = _find_unique(inspector, to_columns)
    if current is not None:
        return
    current = _find_unique(inspector, from_columns)
    if current is not None:
        kind, name = current
        if kind == "index":
            op.drop_index(name, table_name=_TABLE_NAME)
        elif conn.dialect.name == "sqlite":
            with op.batch_alter_table(_TABLE_NAME) as batch_op:
                batch_op.drop_constraint(name, type_="unique")
        else:
            op.drop_constraint(name, _TABLE_NAME, type_="unique")
    if conn.dialect.name == "sqlite":
        op.create_index(_UNIQUE_NAME, _TABLE_NAME, to_columns, unique=True)
    else:
        op.create_unique_constraint(_UNIQUE_NAME, _TABLE_NAME, to_columns)


def _find_unique(
    inspector: sa.Inspector,
    columns: list[str],
) -> tuple[str, str] | None:
    for item in inspector.get_unique_constraints(_TABLE_NAME):
        name = item.get("name")
        if not name:
            continue
        column_names = list(item.get("column_names") or [])
        if column_names == columns:
            return "constraint", name
    for item in inspector.get_indexes(_TABLE_NAME):
        if not item.get("unique"):
            continue
        name = item.get("name")
        if not name:
            continue
        column_names = list(item.get("column_names") or [])
        if column_names == columns:
            return "index", name
    return None
