from datetime import datetime, timedelta
from typing import List

SOURCE_DATE_FORMAT = "%Y-%m-%d"
SOURCE_DATE_FORMAT_2 = "%d/%m/%Y"
SOURCE_DATE_FORMAT_3 = "%d.%m.%Y"
OUTPUT_DATE_FORMAT = "%d.%m.%y"
OUTPUT_DATE_FORMAT_2  = "%b %Y"

DATE_TIME = "%Y-%m-%d_%H-%M"

def strtodate(date_str: str) -> datetime: 
    try:
        return datetime.strptime(date_str, SOURCE_DATE_FORMAT)
    except: 
        try:
            return datetime.strptime(date_str, SOURCE_DATE_FORMAT_2)
        except: 
            return datetime.strptime(date_str, SOURCE_DATE_FORMAT_3)

def datetostr(date: datetime, date_format: str = OUTPUT_DATE_FORMAT) -> str: 
    return datetime.strftime(date, date_format)

def convert_source_2_to_1(date_str) -> str: 
    try:
        date = strtodate(date_str) 
        date_str = datetostr(date, SOURCE_DATE_FORMAT)
        return date_str
    except Exception as err: 
        print(f"Failed parsing date: {date_str}: {repr(err)}")
        return ""

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
