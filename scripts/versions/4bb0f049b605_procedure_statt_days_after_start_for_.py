"""'procedure' statt 'days-after-start' for viruses

Revision ID: 4bb0f049b605
Revises: 872f916e9634
Create Date: 2023-02-11 03:32:01.690531

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4bb0f049b605'
down_revision = '872f916e9634'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("virus", sa.Column("procedure", sa.String)) 
    conncection = op.get_bind()
    conncection.execute("UPDATE virus SET procedure='Viral injection'")

    op.add_column("availible_viruses", sa.Column("procedure", sa.String)) 
    conncection = op.get_bind()
    conncection.execute("UPDATE availible_viruses SET procedure='Viral injection'")

    op.add_column("protocol_viruses", sa.Column("procedure", sa.String)) 
    conncection = op.get_bind()
    conncection.execute("UPDATE protocol_viruses SET procedure='Viral injection'")


def downgrade() -> None:
    pass
