from datetime import datetime, timedelta
from typing import List
from exceptions.exceptions import InvalidDateException, ParserException

SOURCE_DATE_FORMAT = "%Y-%m-%d"
OUTPUT_DATE_FORMAT = "%d.%m.%y"
OUTPUT_DATE_FORMAT_2  = "%b %Y"

DATE_TIME = "%Y-%m-%d_%H-%M"

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
    raise InvalidDateException(date_str, ', '.join(date_formats))

def strtodate(date_str: str) -> datetime: 
    try: 
        return datetime.strptime(date_str, SOURCE_DATE_FORMAT)
    except: 
        raise ParserException(f"Date {date_str} seems not to have been unified!", 409)

def datetostr(date: datetime, date_format: str = OUTPUT_DATE_FORMAT) -> str: 
    return datetime.strftime(date, date_format)

def datetostr_month(date: datetime) -> str: 
    return datetime.strftime(date, OUTPUT_DATE_FORMAT_2)

def incdate(date: datetime, days: int) -> datetime: 
    return date + timedelta(days=days) 

def daterange(date1: datetime, date2: datetime) -> List[datetime]:
    return [date1 + timedelta(days=x) for x in range((date2-date1).days+1)]

def daterange_str(date1: str, date2: str) -> List[str]:
    d1 = strtodate(date1)
    d2 = strtodate(date2)
    return [datetostr(d1 + timedelta(days=x), SOURCE_DATE_FORMAT) for x in range((d2-d1).days+1)]

def is_date(date_str: str) -> bool:
    return isinstance(date_str, datetime)

def convert(
    date_str: str, out_format: str = OUTPUT_DATE_FORMAT
) -> str:
    return datetostr(strtodate(date_str), out_format)

def today() -> datetime:
    return datetime.now()

def date_filled(date_str: str) -> bool: 
    return date_str and len(date_str) == 10
