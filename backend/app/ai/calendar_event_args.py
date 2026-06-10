from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.services.calendar_service import CalendarService


def has_value(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def infer_all_day(args: dict, default: bool = True) -> bool:
    if args.get("all_day") is not None:
        return bool(args["all_day"])
    return not (has_value(args.get("time")) or has_value(args.get("end_time"))) if default else False


def default_end_time(start_date: date, start_time: str) -> tuple[date, str]:
    normalized = CalendarService.normalize_time(start_time)
    if normalized is None:
        raise ValueError("시간을 선택하거나 하루 종일 일정을 켜주세요.")
    hour, minute = [int(part) for part in normalized.split(":")]
    total = hour * 60 + minute + 60
    day_delta, minute_of_day = divmod(total, 24 * 60)
    end_date = start_date + timedelta(days=day_delta)
    return end_date, f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def normalize_create_time_args(
    args: dict,
    event_date: date,
    end_date: date | None,
) -> tuple[str | None, date | None, str | None, bool]:
    all_day = infer_all_day(args)
    if all_day:
        return None, end_date, None, True

    event_time = CalendarService.normalize_time(args.get("time"))
    if event_time is None:
        raise ValueError("시간을 선택하거나 하루 종일 일정을 켜주세요.")

    if has_value(args.get("end_time")):
        end_time = CalendarService.normalize_time(args.get("end_time"))
        return event_time, end_date, end_time, False

    inferred_end_date, end_time = default_end_time(event_date, event_time)
    return event_time, end_date or inferred_end_date, end_time, False


def normalize_update_time_fields(fields: dict, current: Any) -> tuple[date, date, str | None, str | None, bool]:
    event_date = fields.get("event_date") or date.fromisoformat(str(current.event_date)[:10])
    end_date = fields.get("end_date") or date.fromisoformat(str(getattr(current, "end_date", current.event_date))[:10])

    touches_time = (
        "all_day" in fields
        or "event_time" in fields
        or "end_time" in fields
        or "event_date" in fields
        or "end_date" in fields
    )

    if "all_day" in fields:
        all_day = bool(fields["all_day"])
    elif has_value(fields.get("event_time")) or has_value(fields.get("end_time")):
        all_day = False
        fields["all_day"] = False
    else:
        all_day = bool(getattr(current, "all_day", True))

    if all_day:
        if touches_time:
            fields["all_day"] = True
            fields["event_time"] = None
            fields["end_time"] = None
        return event_date, end_date, None, None, True

    event_time = fields.get("event_time") if "event_time" in fields else (
        str(getattr(current, "event_time", ""))[:5] if getattr(current, "event_time", None) else None
    )
    event_time = CalendarService.normalize_time(event_time)
    if event_time is None:
        raise ValueError("시간을 선택하거나 하루 종일 일정을 켜주세요.")

    if "end_time" in fields:
        end_time = CalendarService.normalize_time(fields.get("end_time"))
    elif "event_time" in fields:
        inferred_end_date, end_time = default_end_time(event_date, event_time)
        if "end_date" not in fields:
            end_date = inferred_end_date
            fields["end_date"] = end_date
    else:
        end_time = str(getattr(current, "end_time", ""))[:5] if getattr(current, "end_time", None) else None
        end_time = CalendarService.normalize_time(end_time)

    if end_time is None:
        inferred_end_date, end_time = default_end_time(event_date, event_time)
        if "end_date" not in fields:
            end_date = inferred_end_date
            fields["end_date"] = end_date

    if touches_time:
        fields["all_day"] = False
        fields["event_time"] = event_time
        fields["end_time"] = end_time

    return event_date, end_date, event_time, end_time, False
