"""Require one allowance per protocol and animal line.

Revision ID: b27e9146c803
Revises: 7e3c1a9f42b6
"""
from alembic import op
import sqlalchemy as sa


revision = "b27e9146c803"
down_revision = "7e3c1a9f42b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicate = connection.execute(sa.text(
        "SELECT protocol, name FROM protocol_allowed_mice "
        "GROUP BY protocol, name HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate is not None:
        raise RuntimeError(
            f"Duplicate allowances for protocol {duplicate.protocol!r}, "
            f"line {duplicate.name!r}; resolve them before upgrading."
        )
    with op.batch_alter_table("protocol_allowed_mice") as batch_op:
        batch_op.create_unique_constraint(
            "uq_protocol_allowed_mice_protocol_name", ["protocol", "name"]
        )


def downgrade() -> None:
    with op.batch_alter_table("protocol_allowed_mice") as batch_op:
        batch_op.drop_constraint(
            "uq_protocol_allowed_mice_protocol_name", type_="unique"
        )
