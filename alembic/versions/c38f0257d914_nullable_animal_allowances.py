"""Normalize unspecified allowances to NULL and constrain numeric limits.

Revision ID: c38f0257d914
Revises: b27e9146c803
"""
from alembic import op
import sqlalchemy as sa


revision = "c38f0257d914"
down_revision = "b27e9146c803"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT uuid, num_availible_animals FROM protocol_allowed_mice"
    )).all()
    updates = []
    for uuid, value in rows:
        if value is None:
            continue
        if isinstance(value, str) and value.strip() in ("", "-", "--"):
            updates.append({"uuid": uuid})
        elif type(value) is not int or value < 0:
            raise RuntimeError(
                f"Invalid allowance {value!r} for row {uuid!r}; "
                "resolve it before upgrading."
            )
    if updates:
        connection.execute(sa.text(
            "UPDATE protocol_allowed_mice SET num_availible_animals = NULL "
            "WHERE uuid = :uuid"
        ), updates)
    with op.batch_alter_table("protocol_allowed_mice") as batch_op:
        batch_op.create_check_constraint(
            "ck_protocol_allowed_mice_allowance",
            "num_availible_animals IS NULL OR "
            "(typeof(num_availible_animals) = 'integer' AND num_availible_animals >= 0)",
        )


def downgrade() -> None:
    # Original placeholder spellings cannot be recovered; keep NULL values.
    with op.batch_alter_table("protocol_allowed_mice") as batch_op:
        batch_op.drop_constraint("ck_protocol_allowed_mice_allowance", type_="check")
