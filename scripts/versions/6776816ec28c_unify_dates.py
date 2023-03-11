"""unify dates

Revision ID: 6776816ec28c
Revises: 4bb0f049b605
Create Date: 2023-03-11 02:52:27.552321

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timedelta


# revision identifiers, used by Alembic.
revision = '6776816ec28c'
down_revision = '4bb0f049b605'
branch_labels = None
depends_on = None

SOURCE_DATE_FORMAT = "%Y-%m-%d"

def upgrade() -> None:
    def datetostr(date: datetime, date_format: str) -> str: 
        return datetime.strftime(date, date_format)

    def unify_date(date_str: str) -> str: 
        # If date is not yet set, return placeholder
        if date_str in ["", "---"] or date_str.isnumeric():
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

    op.execute("UPDATE animal_data SET dob = unify_date(dob)")
    op.execute("UPDATE animal_data SET death_date = unify_date(death_date)")
    op.execute("UPDATE procedures SET start_date = unify_date(start_date)")
    op.execute("UPDATE procedures SET end_date = unify_date(end_date)")


def downgrade() -> None:
    pass
