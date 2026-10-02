"""Clean up protocol configuration and enforce singleton rows.

Revision ID: 7e3c1a9f42b6
Revises: aafd299a9a52
Create Date: 2026-09-12

"""
from typing import Any, Callable, Dict, Iterable, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7e3c1a9f42b6"
down_revision: Union[str, None] = "aafd299a9a52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PROTOCOL_DATA_TABLES = (
    "protocol_general",
    "protocol_watercontrol",
    "protocol_allowed_mice",
    "protocol_medication",
    "protocol_procedures",
    "protocol_viruses",
)


def _valid_full_protocols(connection: sa.Connection) -> set[str]:
    rows = connection.execute(
        sa.text("SELECT escaped, subprotocols FROM protocols")
    ).mappings()
    return {
        f"{row['escaped']}/{subprotocol}"
        for row in rows
        for subprotocol in (row["subprotocols"] or "").split(";")
        if subprotocol
    }


def _delete_orphans(
    connection: sa.Connection,
    metadata: sa.MetaData,
    valid_protocols: set[str],
) -> None:
    for table_name in PROTOCOL_DATA_TABLES:
        table = sa.Table(table_name, metadata, autoload_with=connection)
        condition = table.c.protocol.is_(None)
        if valid_protocols:
            condition = sa.or_(
                condition,
                table.c.protocol.not_in(sorted(valid_protocols)),
            )
        else:
            condition = sa.true()
        connection.execute(table.delete().where(condition))


def _resolve_duplicates(
    connection: sa.Connection,
    table: sa.Table,
    is_configured: Callable[[Dict[str, Any]], bool],
    value_columns: Iterable[str],
) -> None:
    duplicate_protocols = connection.execute(
        sa.select(table.c.protocol)
        .group_by(table.c.protocol)
        .having(sa.func.count() > 1)
    ).scalars()

    for protocol in duplicate_protocols:
        rows = list(
            connection.execute(
                sa.select(table)
                .where(table.c.protocol == protocol)
                .order_by(table.c.uuid)
            ).mappings()
        )
        configured = [row for row in rows if is_configured(dict(row))]

        if configured:
            configurations = {
                tuple(row[column] for column in value_columns)
                for row in configured
            }
            if len(configurations) > 1:
                raise RuntimeError(
                    f"Conflicting configured rows in {table.name} for "
                    f"protocol {protocol!r}; resolve them manually before upgrading."
                )
            keep_uuid = configured[0]["uuid"]
        else:
            keep_uuid = rows[0]["uuid"]

        connection.execute(
            table.delete().where(
                table.c.protocol == protocol,
                table.c.uuid != keep_uuid,
            )
        )


def _general_is_configured(row: Dict[str, Any]) -> bool:
    return bool((row["allowed_users"] or "").strip()) or row["suffering"] not in (
        None,
        "",
        "Leicht",
    )


def _watercontrol_is_configured(row: Dict[str, Any]) -> bool:
    return bool(row["allowed"]) or str(row["days_after_start"] or "") not in (
        "",
        "0",
    ) or str(row["duration"] or "") not in ("", "0")


def upgrade() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()

    valid_protocols = _valid_full_protocols(connection)
    _delete_orphans(connection, metadata, valid_protocols)

    general = sa.Table(
        "protocol_general", metadata, autoload_with=connection
    )
    watercontrol = sa.Table(
        "protocol_watercontrol", metadata, autoload_with=connection
    )

    _resolve_duplicates(
        connection,
        general,
        _general_is_configured,
        ("num_availible_animals", "allowed_users", "suffering"),
    )
    _resolve_duplicates(
        connection,
        watercontrol,
        _watercontrol_is_configured,
        ("allowed", "days_after_start", "duration"),
    )

    with op.batch_alter_table("protocol_general") as batch_op:
        batch_op.create_unique_constraint(
            "uq_protocol_general_protocol", ["protocol"]
        )
    with op.batch_alter_table("protocol_watercontrol") as batch_op:
        batch_op.create_unique_constraint(
            "uq_protocol_watercontrol_protocol", ["protocol"]
        )


def downgrade() -> None:
    # Deleted duplicate and orphan rows cannot be reconstructed on downgrade.
    with op.batch_alter_table("protocol_watercontrol") as batch_op:
        batch_op.drop_constraint(
            "uq_protocol_watercontrol_protocol", type_="unique"
        )
    with op.batch_alter_table("protocol_general") as batch_op:
        batch_op.drop_constraint(
            "uq_protocol_general_protocol", type_="unique"
        )
