"""
Schedule generator.

Compiles the DAK's 7 schedule groups (31 items) and computes due dates from the
ISO-8601 duration formulas the DAK uses, e.g. `service_due_date_formula = "trigger_date + P12M"`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

try:
    from dateutil.relativedelta import relativedelta
    _HAVE_DATEUTIL = True
except ImportError:  # pragma: no cover
    _HAVE_DATEUTIL = False

# ISO-8601 duration: PnYnMnWnD.
_DUR_RE = re.compile(
    r"P(?:(?P<y>\d+)Y)?(?:(?P<m>\d+)M)?(?:(?P<w>\d+)W)?(?:(?P<d>\d+)D)?"
)


def _parse(dur: str):
    m = _DUR_RE.fullmatch(dur.strip())
    if not m or not any(m.groupdict().values()):
        return None
    return {k: int(v or 0) for k, v in m.groupdict().items()}


def add_iso_duration(start: date, dur: str) -> date | None:
    """Calendar-aware: 'P12M' from 2026-06-30 lands on 2027-06-30, not +360 days.
    Falls back to an approximation only if python-dateutil is unavailable."""
    parts = _parse(dur)
    if parts is None:
        return None
    if _HAVE_DATEUTIL:
        return start + relativedelta(years=parts["y"], months=parts["m"],
                                     weeks=parts["w"], days=parts["d"])
    days = parts["y"] * 365 + parts["m"] * 30 + parts["w"] * 7 + parts["d"]
    return start + timedelta(days=days)


def parse_iso_duration_to_days(dur: str) -> int | None:
    parts = _parse(dur)
    if parts is None:
        return None
    return parts["y"] * 365 + parts["m"] * 30 + parts["w"] * 7 + parts["d"]


@dataclass
class ScheduledService:
    schedule_item_id: str
    service_name: str
    due_date: str | None
    overdue_after: str | None
    responsible_actor: str | None
    trigger_event: str
    needs_review: bool
    source_formula: str


def generate_schedule(item: dict, trigger_date: date) -> ScheduledService:
    formula = item.get("service_due_date_formula") or ""
    due = None
    mm = re.search(r"trigger_date\s*\+\s*(P[\dYMWD]+)", formula)
    if mm:
        d = add_iso_duration(trigger_date, mm.group(1))
        if d is not None:
            due = d.isoformat()
    return ScheduledService(
        schedule_item_id=item.get("schedule_item_id", ""),
        service_name=item.get("service_name", ""),
        due_date=due,
        overdue_after=item.get("service_overdue"),
        responsible_actor=item.get("responsible_actor"),
        trigger_event=item.get("trigger_event", ""),
        needs_review=bool(item.get("_needs_clinical_review")) or due is None,
        source_formula=formula,
    )
