"""unify dates

Revision ID: 6776816ec28c
Revises: 4bb0f049b605
Create Date: 2023-03-11 02:52:27.552321

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '6776816ec28c'
down_revision = '4bb0f049b605'
branch_labels = None
depends_on = None

SOURCE_DATE_FORMAT = "%Y-%m-%d"

Base = declarative_base()

# Define used models
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

class Procedure(Base): 
    __tablename__ = "procedures"

    uuid = sa.Column(sa.String, primary_key=True) 
    animal_id = sa.Column(sa.String, primary_key=False) 
    name = sa.Column(sa.String, primary_key=False) 
    start_date = sa.Column(sa.String, primary_key=False) 
    end_date = sa.Column(sa.String, primary_key=False) 
    experimenter = sa.Column(sa.String, primary_key=False) 
    protocol_entry_uuid = sa.Column(sa.String, primary_key=False)

# Define functions to unify dates

def datetostr(date: datetime, date_format: str) -> str: 
    return datetime.strftime(date, date_format)


def unify_date(date_str: str) -> str: 
    # If date is not yet set, return placeholder
    if date_str in ["", "---"] or date_str.isnumeric() or date_str[1:].isnumeric():
        return date_str
    if date_str in ["nan"]:
        return "---"
    # Try to parse date from availible formats, then convert to SOURCE_DATE_FORMAT
    date_formats = [SOURCE_DATE_FORMAT, "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%m.%d.%Y"]
    for df in date_formats: 
        try: 
            date = datetime.strptime(date_str, df)
            return datetostr(date, SOURCE_DATE_FORMAT) 
        except:
            pass 
    # If date did not match any formats, raise error
    raise TypeError(f"date {date_str} not in {', '.join(date_formats)}")


def upgrade() -> None:
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    for table in session.query(AnimalData):
        table.dob = unify_date(table.dob)
        table.death_date = unify_date(table.death_date)
    for table in session.query(Procedure):
        table.start_date = unify_date(table.start_date)
        table.end_date = unify_date(table.end_date)

    session.commit()

def downgrade() -> None:
    pass
