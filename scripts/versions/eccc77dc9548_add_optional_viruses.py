"""add optional viruses

Revision ID: eccc77dc9548
Revises: 148e358dd9f8
Create Date: 2023-03-21 03:07:02.813786

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eccc77dc9548'
down_revision = '148e358dd9f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("protocol_viruses", sa.Column("optional", sa.Boolean))
    conncection = op.get_bind()
    conncection.execute("UPDATE protocol_viruses SET optional='0'")


def downgrade() -> None:
    op.drop_column("protocol_viruses", "optional")
