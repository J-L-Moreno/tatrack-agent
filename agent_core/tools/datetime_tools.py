import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from config import config

_WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


@tool
def get_current_datetime() -> str:
    """Return the current date and time in UTC and in the user's local timezone.

    Call it before interpreting relative dates such as "tomorrow", "Friday" or "next week".
    """
    now_utc = datetime.now(timezone.utc)
    local = now_utc.astimezone(ZoneInfo(config.user_timezone))
    return json.dumps({
        "utc_datetime": now_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "local_datetime": local.isoformat(timespec="seconds"),
        "local_date": local.date().isoformat(),
        "weekday": _WEEKDAYS_ES[local.weekday()],
        "timezone": config.user_timezone,
    }, ensure_ascii=False)
