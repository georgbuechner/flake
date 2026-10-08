"""Changes start-weight from int to float

Revision ID: 1bee5f4aa677
Revises: c38f0257d914
Create Date: 2026-10-03 00:25:36.791561

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1bee5f4aa677'
down_revision: Union[str, Sequence[str], None] = 'c38f0257d914'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Change only the start-weight column, using SQLite's table-copy workflow."""
    with op.batch_alter_table("general") as batch_op:
        batch_op.alter_column(
            "start_weight",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=True,
        )


def downgrade() -> None:
    """Refuse to truncate fractional weights when restoring the integer type."""
    fractional_weight = op.get_bind().execute(sa.text(
        "SELECT animal_id FROM general "
        "WHERE start_weight != CAST(start_weight AS INTEGER) LIMIT 1"
    )).first()
    if fractional_weight is not None:
        raise RuntimeError(
            "Cannot downgrade start_weight to INTEGER while fractional weights exist."
        )
    with op.batch_alter_table("general") as batch_op:
        batch_op.alter_column(
            "start_weight",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
