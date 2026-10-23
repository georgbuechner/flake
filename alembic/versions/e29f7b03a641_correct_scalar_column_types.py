"""Correct scalar types and normalize unset scheduling values.

Revision ID: e29f7b03a641
Revises: 1bee5f4aa677
"""
import re

from alembic import op
import sqlalchemy as sa


revision = "e29f7b03a641"
down_revision = "1bee5f4aa677"
branch_labels = None
depends_on = None

SCHEDULE_COLUMNS = (
    ("availible_procedures", "days_after_start"),
    ("availible_procedures", "duration"),
    ("protocol_procedures", "days_after_start"),
    ("protocol_procedures", "duration"),
    ("protocol_watercontrol", "days_after_start"),
    ("protocol_watercontrol", "duration"),
)
COUNT_COLUMNS = tuple(
    (table, column)
    for table in ("availible_procedures", "protocol_procedures")
    for column in ("requires_medication", "requires_virus")
)
INTEGER_COLUMNS = (("availible_procedures", "days_after_start"),) + COUNT_COLUMNS


def upgrade() -> None:
    connection = op.get_bind()
    placeholders = []
    # Validate every scalar before issuing any UPDATE or rebuilding a table.
    # SQLite casts would otherwise silently truncate ranges or invalid text.
    for table, column in SCHEDULE_COLUMNS + COUNT_COLUMNS:
        values = connection.execute(sa.text(
            f'SELECT DISTINCT "{column}" FROM "{table}"'
        )).scalars()
        for value in values:
            if value is None:
                continue
            if isinstance(value, str) and value.strip() in ("", "-", "--", "---"):
                placeholders.append((table, column, value))
                continue
            if (table, column) not in INTEGER_COLUMNS:
                continue
            if type(value) is not int and not (
                isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value.strip())
            ):
                raise RuntimeError(f"Invalid integer in {table}.{column}: {value!r}")
            number = int(value)
            if not -(2**63) <= number < 2**63 or (
                (table, column) in COUNT_COLUMNS and number < 0
            ):
                raise RuntimeError(f"Invalid integer in {table}.{column}: {value!r}")

    for table, column, value in placeholders:
        connection.execute(sa.text(
            f'UPDATE "{table}" SET "{column}" = NULL WHERE "{column}" = :value'
        ), {"value": value})

    for table in ("availible_procedures", "protocol_procedures"):
        with op.batch_alter_table(table) as batch_op:
            if table == "availible_procedures":
                batch_op.alter_column(
                    "days_after_start", existing_type=sa.String(),
                    type_=sa.Integer(), existing_nullable=True,
                )
            for column in ("requires_medication", "requires_virus"):
                batch_op.alter_column(
                    column, existing_type=sa.Boolean(),
                    type_=sa.Integer(), existing_nullable=True,
                )

    for table, column in (
        ("protocol_allowed_mice", "name"), ("medication", "procedure"),
    ):
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                column, existing_type=sa.Integer(),
                type_=sa.String(), existing_nullable=True,
            )


def downgrade() -> None:
    raise RuntimeError(
        "Scalar type corrections cannot be safely downgraded: casting labels "
        "back to INTEGER loses text, and original placeholders cannot be recovered. "
        "Restore the pre-upgrade database backup instead."
    )
