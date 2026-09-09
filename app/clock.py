import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def school_tz():
    name = (os.environ.get("SAHAL_TZ") or os.environ.get("TZ") or "").strip()
    if name:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            pass
    return datetime.now().astimezone().tzinfo or ZoneInfo("Asia/Dubai")


def now() -> datetime:
    stamp = datetime.now(school_tz())
    return stamp.replace(tzinfo=None)


def today():
    return now().date()
