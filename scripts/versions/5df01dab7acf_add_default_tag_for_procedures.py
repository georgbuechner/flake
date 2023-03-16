"""add default-tag for procedures

Revision ID: 5df01dab7acf
Revises: 6776816ec28c
Create Date: 2023-03-16 01:06:22.227287

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5df01dab7acf'
down_revision = '6776816ec28c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("protocol_procedures", sa.Column("optional", sa.Boolean))
    conncection = op.get_bind()
    conncection.execute("UPDATE protocol_procedures SET optional='0'")

def downgrade() -> None:
    op.drop_column("protocol_procedures", "optional")
