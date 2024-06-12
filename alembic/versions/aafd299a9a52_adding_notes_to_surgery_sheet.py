"""Adding notes to Surgery Sheet

Revision ID: aafd299a9a52
Revises: 044675535232
Create Date: 2024-06-09 22:42:43.628716

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aafd299a9a52'
down_revision: Union[str, None] = '044675535232'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notes", sa.Column("surgery_sheet", sa.Boolean))
    conncection = op.get_bind()
    conncection.execute(sa.text("UPDATE notes SET surgery_sheet=0"))


def downgrade() -> None:
    op.drop_column("notes", "surgery_sheet")
