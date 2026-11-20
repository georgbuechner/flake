"""Add paw-control membership, disabled for every existing user.

Revision ID: d6f7a21b903e
Revises: e29f7b03a641
"""
from alembic import op
import sqlalchemy as sa


revision = "d6f7a21b903e"
down_revision = "e29f7b03a641"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The database default backfills existing rows and covers future inserts.
    op.add_column("user", sa.Column(
        "paw_control", sa.Boolean(), nullable=False, server_default=sa.false()
    ))


def downgrade() -> None:
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("paw_control")
