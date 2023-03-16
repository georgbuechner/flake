"""add required medication- and viruses to procedure

Revision ID: 148e358dd9f8
Revises: 5df01dab7acf
Create Date: 2023-03-16 02:24:22.008716

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base


# revision identifiers, used by Alembic.
revision = '148e358dd9f8'
down_revision = '5df01dab7acf'
branch_labels = None
depends_on = None

Base = declarative_base()

class AProcedure(Base): 
    __tablename__ = "availible_procedures"

    name = sa.Column(sa.String, primary_key=True) 
    days_after_start = sa.Column(sa.String, primary_key=False)
    duration = sa.Column(sa.String, primary_key=False)
    surgery = sa.Column(sa.Boolean, primary_key=False)
    requires_medication = sa.Column(sa.Integer, primary_key=False)
    requires_virus = sa.Column(sa.Integer, primary_key=False)


class PProcedure(Base): 
    __tablename__ = "protocol_procedures"

    uuid = sa.Column(sa.String, primary_key=True)
    protocol = sa.Column(sa.String, primary_key=False) 
    name = sa.Column(sa.String, primary_key=False) 
    days_after_start = sa.Column(sa.String, primary_key=False)
    duration = sa.Column(sa.String, primary_key=False)
    surgery = sa.Column(sa.Boolean, primary_key=False)
    optional = sa.Column(sa.Boolean, primary_key=False)
    requires_medication = sa.Column(sa.Integer, primary_key=False)
    requires_virus = sa.Column(sa.Integer, primary_key=False)


def upgrade() -> None:
    # Add new columns
    op.add_column("protocol_procedures", sa.Column("requires_medication", sa.Boolean))
    op.add_column("protocol_procedures", sa.Column("requires_virus", sa.Boolean))
    op.add_column("availible_procedures", sa.Column("requires_medication", sa.Boolean))
    op.add_column("availible_procedures", sa.Column("requires_virus", sa.Boolean))

    # Get session
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # Create default mapping
    requires_medication = {
        "Viral injection": 2, 
        "Post-surgery analgesic": 1, 
        "Sacrifice: perfusion": 1, 
        "Sacrifice decapitation": 1
    }

    # Update default values based on names:
    for Table in [AProcedure, PProcedure]:
        for table in session.query(Table):
            if table.name in requires_medication:
                table.requires_medication = requires_medication[table.name] 
            else:
                table.requires_medication = 0
            table.requires_virus = 1 if table.name == "Viral injection" else 0
    session.commit()


def downgrade() -> None:
    pass
