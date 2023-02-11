"""merge procedures and post-procedures

Revision ID: 872f916e9634
Revises: f5dd53535549
Create Date: 2023-02-11 02:36:32.616745

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '872f916e9634'
down_revision = 'f5dd53535549'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("INSERT INTO procedures (animal_id, name, start_date, end_date, experimenter, protocol_entry_uuid) SELECT * FROM post_procedures")
    op.drop_table("post_procedures")

def downgrade() -> None:
    pass
