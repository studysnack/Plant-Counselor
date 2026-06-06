"""Runtime settings — in-memory overrides for hardcoded defaults.

These are NOT persisted across restarts by default, but can be
saved/loaded via JSON snapshot (admin controller page).
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SNAPSHOT_PATH = Path(__file__).parent.parent / "runtime_settings.json"

# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    # LLM
    "llm_default_model": "gemini-3-flash-preview",
    "llm_max_steps": 10,
    "llm_temperature": None,       # None = use Gemini default

    # Scheduler
    "scheduler_interval_minutes": 10,

    # Transition defaults (apply when user has no custom garden_rules)
    "default_wilting_days": 7,
    "default_rot_disappear_days": 14,
    "default_deadline_warn_days": 3,
    "default_auto_transition": True,

    # Plant-level wilting: the whole plant wilts once at least N of its buds are
    # wilting AND M days have passed since that Nth bud started wilting.
    "default_plant_wilt_bud_threshold": 2,   # N
    "default_plant_wilt_days": 3,            # M

    # System
    "system_log_level": "INFO",
    "system_max_log_files": 500,

    # App timezone — what the app considers "now"/"today". Korea = UTC+9 (KST).
    # All user-facing dates (calendar, deadlines, "오늘") are computed in this zone
    # so they match the dates the (KST) frontend stores.
    "app_timezone_offset_hours": 9,

    # Time travel (demo only) — offset in seconds added to all datetime checks
    "time_offset_seconds": 0,
}

# Available Gemini models (listed for the admin UI dropdowns).
# Ordered newest/most-capable first. IDs verified against Google AI docs
# (2026-06): the 3.x series uses the `-preview` suffix; `gemini-3-pro-preview`
# was discontinued (2026-03) in favor of `gemini-3.1-pro-preview`. A non-served
# ID surfaces as a "모델 없음 (404)" error in the admin AI logs page.
AVAILABLE_MODELS = [
    # Gemini 3.x (최신 — preview 계열)
    "gemini-3.5-flash",            # 3.5 Flash (최신 플래시)
    "gemini-3.1-pro-preview",      # 3.1 Pro (고성능 플래그십)
    "gemini-3-flash-preview",      # 3 Flash Preview (기본값 — 빠르고 저비용)
    "gemini-3.1-flash-lite",       # 3.1 Flash-Lite (최저비용·고할당량)
    # Gemini 2.5 (멀티모달 Pro + 일상 Flash 계열)
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    # Legacy (하위 호환용)
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

# ── Live store ────────────────────────────────────────────────────────────────

_store: dict[str, Any] = dict(DEFAULTS)


def get(key: str, default: Any = None) -> Any:
    return _store.get(key, DEFAULTS.get(key, default))


def get_all() -> dict[str, Any]:
    return dict(_store)


def set(key: str, value: Any) -> None:  # noqa: A001
    if key not in DEFAULTS:
        raise KeyError(f"Unknown runtime setting: {key!r}")
    _store[key] = value
    logger.info("Runtime setting changed: %s = %r", key, value)


def set_many(updates: dict[str, Any]) -> list[str]:
    """Update multiple settings. Returns list of unknown keys that were skipped."""
    skipped = []
    for k, v in updates.items():
        if k not in DEFAULTS:
            skipped.append(k)
            continue
        _store[k] = v
    return skipped


def reset(key: str) -> None:
    _store[key] = DEFAULTS[key]


def reset_all() -> None:
    _store.clear()
    _store.update(DEFAULTS)


def save_snapshot() -> None:
    """Persist current settings to disk so they survive restarts."""
    try:
        with open(_SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(_store, f, ensure_ascii=False, indent=2, default=str)
        logger.info("Runtime settings snapshot saved.")
    except Exception as e:
        logger.warning("Could not save runtime settings: %s", e)


def load_snapshot() -> None:
    """Load persisted settings if snapshot exists."""
    if not _SNAPSHOT_PATH.exists():
        return
    try:
        with open(_SNAPSHOT_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        for k, v in saved.items():
            if k in DEFAULTS:
                _store[k] = v
        logger.info("Runtime settings loaded from snapshot.")
    except Exception as e:
        logger.warning("Could not load runtime settings snapshot: %s", e)


# ── Time helpers ─────────────────────────────────────────────────────────────

def _tz_offset_hours() -> int:
    return int(_store.get("app_timezone_offset_hours", 9) or 0)


def app_timezone() -> timezone:
    """Timezone object for the app's user-facing clock. Default is KST (UTC+9)."""
    return timezone(timedelta(hours=_tz_offset_hours()))


def real_now() -> datetime:
    """Wall-clock 'now' in the app's local timezone (KST by default), WITHOUT
    the time-travel offset. Used as the baseline for the admin time-travel view."""
    return datetime.now(app_timezone())


def now() -> datetime:
    """App 'now' = local wall-clock (timezone-adjusted) + time-travel offset."""
    offset = _store.get("time_offset_seconds", 0) or 0
    return real_now() + timedelta(seconds=int(offset))


def today() -> date:
    """The app's current local date (timezone + time-travel adjusted)."""
    return now().date()


def time_offset_seconds() -> int:
    return int(_store.get("time_offset_seconds", 0) or 0)


# Load snapshot on module import
load_snapshot()
