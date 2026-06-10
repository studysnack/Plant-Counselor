"""Allowed colors for standalone calendar events."""
from __future__ import annotations

from typing import Literal

CalendarEventColor = Literal["olive", "blue", "yellow", "red", "pink", "purple"]

CALENDAR_EVENT_COLORS: tuple[CalendarEventColor, ...] = (
    "olive",
    "blue",
    "yellow",
    "red",
    "pink",
    "purple",
)
DEFAULT_CALENDAR_EVENT_COLOR: CalendarEventColor = "olive"

_COLOR_ALIASES: dict[str, CalendarEventColor] = {
    "olive": "olive",
    "green": "olive",
    "graygreen": "olive",
    "greygreen": "olive",
    "sage": "olive",
    "올리브": "olive",
    "초록": "olive",
    "초록색": "olive",
    "녹색": "olive",
    "연두": "olive",
    "연두색": "olive",
    "카키": "olive",
    "파랑": "blue",
    "파란색": "blue",
    "파란": "blue",
    "블루": "blue",
    "blue": "blue",
    "navy": "blue",
    "남색": "blue",
    "노랑": "yellow",
    "노란색": "yellow",
    "노란": "yellow",
    "옐로우": "yellow",
    "yellow": "yellow",
    "gold": "yellow",
    "골드": "yellow",
    "빨강": "red",
    "빨간색": "red",
    "빨간": "red",
    "레드": "red",
    "red": "red",
    "분홍": "pink",
    "분홍색": "pink",
    "핑크": "pink",
    "pink": "pink",
    "보라": "purple",
    "보라색": "purple",
    "퍼플": "purple",
    "purple": "purple",
    "violet": "purple",
    "자주": "purple",
    "자주색": "purple",
}


def normalize_calendar_event_color(value: str) -> CalendarEventColor:
    key = str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    if key in _COLOR_ALIASES:
        return _COLOR_ALIASES[key]
    raise ValueError(f"지원하지 않는 일정 색상입니다: {value}")


def validate_calendar_event_color(value: str) -> CalendarEventColor:
    return normalize_calendar_event_color(value)
