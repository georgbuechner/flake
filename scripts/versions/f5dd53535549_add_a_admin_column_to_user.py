"""Add a admin-column to user

Revision ID: f5dd53535549
Revises: 
Create Date: 2023-02-08 23:35:40.545876

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f5dd53535549'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("admin", sa.Boolean))

def downgrade() -> None:
    op.drop_column("user", "admin")
