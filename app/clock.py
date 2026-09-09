from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.settings import TZ_NAME


def school_tz():
    try:
        return ZoneInfo(TZ_NAME)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Riyadh")


def now() -> datetime:
    return datetime.now(school_tz()).replace(tzinfo=None)


def today():
    return now().date()
