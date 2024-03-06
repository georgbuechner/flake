"""add error-infos to animal-data

Revision ID: 044675535232
Revises: 
Create Date: 2024-03-04 21:58:47.710948

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
from typing import List, Tuple
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '044675535232'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UNEXPECTED_DEATH = "Death: unexpected"

Base = declarative_base()
Base.query = orm.scoped_session(orm.sessionmaker()).query_property()

class AnimalData(Base): 
    __tablename__ = "animal_data" 

    mla_num = sa.Column(sa.String, primary_key=True)
    sex = sa.Column(sa.String, primary_key=False)
    line = sa.Column(sa.String, primary_key=False)
    dob = sa.Column(sa.String, primary_key=False)
    death_date = sa.Column(sa.String, primary_key=False)
    user = sa.Column(sa.String, primary_key=False)
    protocol_pyrat = sa.Column(sa.String, primary_key=False)
    protocol = sa.Column(sa.String, primary_key=False)
    protocol_escaped = sa.Column(sa.String, primary_key=False)
    supplier = sa.Column(sa.String, primary_key=False)
    subprotocol = sa.Column(sa.String, primary_key=False)
    stored = sa.Column(sa.Boolean, primary_key=False)
    procedures_after_death = sa.Column(sa.Integer, primary_key=False)
    missing_sacrifice = sa.Column(sa.Boolean, primary_key=False)

class Procedure(Base): 
    __tablename__ = "procedures"

    uuid = sa.Column(sa.String, primary_key=True) 
    animal_id = sa.Column(sa.String, primary_key=False) 
    name = sa.Column(sa.String, primary_key=False) 
    start_date = sa.Column(sa.String, primary_key=False) 
    end_date = sa.Column(sa.String, primary_key=False) 
    experimenter = sa.Column(sa.String, primary_key=False) 
    protocol_entry_uuid = sa.Column(sa.String, primary_key=False)


class General(Base):
    __tablename__ = "general"

    animal_id = sa.Column(sa.String, primary_key=True) 
    start = sa.Column(sa.String, primary_key=False) 
    end = sa.Column(sa.String, primary_key=False)
    experiment = sa.Column(sa.String, primary_key=False)
    start_weight = sa.Column(sa.Integer, primary_key=False) 
    watercontrol = sa.Column(sa.Boolean, primary_key=False) 
    weights = sa.Column(sa.String, primary_key=False)
    watercontrol_mask = sa.Column(sa.String, primary_key=False)
    suffering = sa.Column(sa.String, primary_key=False)

def remove_procedures_after_death(
    procedures: List[Procedure], sacrifice_date: str
) -> Tuple[List[Procedure], List[Procedure]]: 
    filtered_procedures = []
    removed_procedures = []
    # Removes all procedures *after* death-date
    for p in procedures: 
        if p.start_date <= sacrifice_date:
            filtered_procedures.append(p)
        else:
            removed_procedures.append({
                "name": p.name, 
                "start_date": p.start_date, 
                "end_date": p.end_date
            })
    return filtered_procedures, removed_procedures

def procedures_contains(procedures: List[Procedure], name: str) -> bool: 
    for p in procedures: 
        if name in p.name: 
            return True 
    return False

def update_stored(animal_data: AnimalData, session): 
    if animal_data.stored == True: 
        procedures = session.query(Procedure).filter(Procedure.animal_id == animal_data.mla_num)
        # procedures = Procedure.query.filter(Procedure.animal_id == animal_data.mla_num)
        procedures, filtered_procedures = remove_procedures_after_death(
            procedures, animal_data.death_date
        )
        animal_data.procedures_after_death = len(filtered_procedures)
        animal_data.missing_sacrifice = (
            not procedures_contains(procedures, UNEXPECTED_DEATH) and 
            not procedures_contains(procedures, "Sacrifice")
        )

def upgrade() -> None:
    # Add a new column to the table
    op.add_column('animal_data', sa.Column('procedures_after_death', sa.Integer))
    op.add_column('animal_data', sa.Column('missing_sacrifice', sa.Boolean))
    conncection = op.get_bind()
    conncection.execute("UPDATE animal_data SET procedures_after_death=0")
    conncection.execute("UPDATE animal_data SET missing_sacrifice=0")
    bind = op.get_bind()
    session = orm.Session(bind=bind)
    for table in session.query(AnimalData):
        update_stored(table, session)

    pass


def downgrade() -> None:
    op.drop_column('animal_data', 'procedures_after_death')
    op.drop_column('animal_data', 'missing_sacrifice')
    pass
