from datetime import datetime, timedelta
from typing import List

SOURCE_DATE_FORMAT = "%Y-%m-%d"
OUTPUT_DATE_FORMAT = "%d.%m.%y"
OUTPUT_DATE_FORMAT_2  = "%b %Y"

def strtodate(date_str: str) -> datetime: 
    return datetime.strptime(date_str, SOURCE_DATE_FORMAT)

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
