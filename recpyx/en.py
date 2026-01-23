# en.py
"""
EN -> IR (parser only)

Public API:
  - parse_schedule(text, default_tz="Europe/Paris") -> IRSchedule
  - parse_rule(text) -> IRRule

Notes:
- Parser EN best-effort (pragmatic).
- Composed rules split ONLY on ", and" (to avoid breaking "monday and thursday").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time, date
from typing import Optional, List

_TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", re.I)
_DATE_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")

WEEKDAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
WEEKDAYS = set(WEEKDAY_MAP.keys())

ORDINAL = {
    "first": 1, "1st": 1,
    "second": 2, "2nd": 2,
    "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4,
    "fifth": 5, "5th": 5,
    "last": -1,
}

def parse_time(s: str) -> time:
    m = _TIME_RE.match(s.strip())
    if not m:
        raise ValueError(f"Invalid time: {s!r}")
    h = int(m.group(1))
    mi = int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()

    if not (0 <= mi <= 59):
        raise ValueError(f"Invalid minute: {s!r}")

    if ampm:
        if not (1 <= h <= 12):
            raise ValueError(f"Invalid hour for am/pm: {s!r}")
        if h == 12:
            h = 0
        if ampm == "pm":
            h += 12
    else:
        if not (0 <= h <= 23):
            raise ValueError(f"Invalid hour for 24h: {s!r}")

    return time(h, mi)

def parse_date(s: str) -> date:
    m = _DATE_RE.match(s.strip())
    if not m:
        raise ValueError(f"Invalid date: {s!r} (expected YYYY-MM-DD)")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

def parse_weekday_list(text: str) -> List[str]:
    t = text.strip().lower().replace(",", " ")
    words = [w for w in t.split() if w not in {"and"}]
    return [w for w in words if w in WEEKDAYS]

def _normalize_tz(tz: str) -> str:
    tz = tz.strip().replace("\\", "/")
    tz = re.sub(r"\s+", "", tz)
    return tz

# ------------------ IR dataclasses (v1) ------------------

@dataclass
class IRHolidaySpec:
    enabled: bool = False
    country: Optional[str] = None  # e.g. "FR"

@dataclass
class IRExcept:
    weekdays: List[int] = field(default_factory=list)  # 0..6
    dates: List[date] = field(default_factory=list)
    holidays: IRHolidaySpec = field(default_factory=IRHolidaySpec)

@dataclass
class IRWindowDate:
    start: Optional[date] = None
    end: Optional[date] = None
    until: Optional[date] = None

@dataclass
class IRBetweenTime:
    start: time
    end: time

@dataclass
class IRStep:
    minutes: Optional[int] = None
    hours: Optional[int] = None

@dataclass
class IRRule:
    type: str  # "rrule" | "oneshot"

    # oneshot local datetime (tz-naive; localized by engine)
    at: Optional[datetime] = None

    # rrule fields
    freq: Optional[str] = None               # minutely|hourly|daily|weekly|monthly|yearly
    interval: int = 1
    bymonth: Optional[List[int]] = None
    byweekday: Optional[List[int]] = None     # 0..6
    bymonthday: Optional[List[int]] = None    # 1..31 or -1
    bysetpos: Optional[List[int]] = None      # 1..5 or -1
    times: List[time] = field(default_factory=list)

    between_time: Optional[IRBetweenTime] = None
    step: Optional[IRStep] = None

    window_date: Optional[IRWindowDate] = None
    except_: IRExcept = field(default_factory=IRExcept)
    weekend_shift: str = "none"  # none|next_monday|next_business_day

@dataclass
class IRSchedule:
    tz: str = "Europe/Paris"
    rules: List[IRRule] = field(default_factory=list)
    version: str = "1"

# ------------------ EN -> IR parsing ------------------

def parse_schedule(text: str, default_tz: str = "Europe/Paris") -> IRSchedule:
    raw = " ".join(text.strip().split())

    tz = default_tz
    m = re.search(r"\s+in\s+([A-Za-z_]+/[A-Za-z_]+)\s*$", raw)
    if m:
        tz = _normalize_tz(m.group(1))
        raw = raw[: m.start()].strip()

    # IMPORTANT: split composed rules ONLY on ", and"
    rule_texts = re.split(r"\s*,\s*and\s+", raw, flags=re.I)
    rules = [parse_rule(rt.strip()) for rt in rule_texts if rt.strip()]
    return IRSchedule(tz=tz, rules=rules)

def parse_rule(text: str) -> IRRule:
    s_lower = " ".join(text.strip().split()).lower()

    weekend_shift = "none"
    window = IRWindowDate()
    ex = IRExcept()

    def apply_except(ex_text: str) -> None:
        ex_text = ex_text.strip().lower()

        if ex_text in {"on public holidays", "public holidays"}:
            ex.holidays.enabled = True
            return

        for w in parse_weekday_list(ex_text):
            idx = WEEKDAY_MAP[w]
            if idx not in ex.weekdays:
                ex.weekdays.append(idx)

        for token in re.split(r"[,\s]+", ex_text):
            if _DATE_RE.match(token):
                d = parse_date(token)
                if d not in ex.dates:
                    ex.dates.append(d)

    # ---- strip suffixes in ANY order (loop until nothing changes) ----
    while True:
        changed = False

        m = re.search(r"\s+if\s+weekend\s+then\s+next\s+(monday|business day)\s*$", s_lower)
        if m:
            weekend_shift = "next_monday" if m.group(1) == "monday" else "next_business_day"
            s_lower = s_lower[: m.start()].strip()
            changed = True

        m = re.search(r"\s+between\s+(\d{4}-\d{2}-\d{2})\s+and\s+(\d{4}-\d{2}-\d{2})\s*$", s_lower)
        if m:
            window.start = parse_date(m.group(1))
            window.end = parse_date(m.group(2))
            s_lower = s_lower[: m.start()].strip()
            changed = True

        m = re.search(r"\s+until\s+(\d{4}-\d{2}-\d{2})\s*$", s_lower)
        if m:
            window.until = parse_date(m.group(1))
            s_lower = s_lower[: m.start()].strip()
            changed = True

        m = re.search(r"\s+except\s+(.+)$", s_lower)
        if m:
            ex_text = m.group(1).strip()
            # if it contains " at ", it's likely mid-except ("... except X at Y")
            if re.search(r"\s+at\s+", ex_text):
                pass
            else:
                apply_except(ex_text)
                s_lower = s_lower[: m.start()].strip()
                changed = True

        if not changed:
            break

    # ---- mid-except: "... except XXX at ..." ----
    m = re.search(r"\s+except\s+(.+?)\s+at\s+", s_lower)
    if m:
        apply_except(m.group(1))
        s_lower = s_lower[: m.start()] + " at " + s_lower[m.end():]
        s_lower = " ".join(s_lower.split())

    # ---- oneshot: YYYY-MM-DD at TIME ----
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s+at\s+(.+)", s_lower)
    if m:
        d = parse_date(m.group(1))
        t = parse_time(m.group(2))
        r = IRRule(type="oneshot", at=datetime(d.year, d.month, d.day, t.hour, t.minute, 0, 0))
        r.window_date = IRWindowDate(start=d, end=d)
        r.except_ = ex
        r.weekend_shift = weekend_shift
        return r

    # ---- every year on MM-DD at T ----
    m = re.fullmatch(r"every\s+year\s+on\s+(\d{2})-(\d{2})\s+at\s+(.+)", s_lower)
    if m:
        mm = int(m.group(1))
        dd = int(m.group(2))
        at = parse_time(m.group(3))
        r = IRRule(type="rrule", freq="yearly", interval=1, bymonth=[mm], bymonthday=[dd], times=[at])
        r.window_date = window if (window.start or window.end or window.until) else None
        r.except_ = ex
        r.weekend_shift = weekend_shift
        return r

    # ---- step within day: every day/weekday every N hours/minutes between t1 and t2 ----
    m = re.fullmatch(
        r"every\s+(day|weekday)\s+every\s+(\d+)\s+(hours|minutes)\s+between\s+(.+?)\s+and\s+(.+)",
        s_lower,
    )
    if m:
        base = m.group(1)
        n = int(m.group(2))
        unit = m.group(3)
        t1 = parse_time(m.group(4))
        t2 = parse_time(m.group(5))
        bywd = [0, 1, 2, 3, 4] if base == "weekday" else None
        step = IRStep(hours=n) if unit == "hours" else IRStep(minutes=n)
        r = IRRule(type="rrule", freq="daily", interval=1, byweekday=bywd,
                   between_time=IRBetweenTime(t1, t2), step=step)
        r.window_date = window if (window.start or window.end or window.until) else None
        r.except_ = ex
        r.weekend_shift = weekend_shift
        return r

    # ---- every N hours between t1 and t2 ----
    m = re.fullmatch(r"every\s+(\d+)\s+hours\s+between\s+(.+?)\s+and\s+(.+)", s_lower)
    if m:
        n = int(m.group(1))
        t1 = parse_time(m.group(2))
        t2 = parse_time(m.group(3))
        r = IRRule(type="rrule", freq="hourly", interval=n, between_time=IRBetweenTime(t1, t2))
        r.window_date = window if (window.start or window.end or window.until) else None
        r.except_ = ex
        r.weekend_shift = weekend_shift
        return r

    # ---- every hour between t1 and t2 ----
    m = re.fullmatch(r"every\s+hour\s+between\s+(.+?)\s+and\s+(.+)", s_lower)
    if m:
        t1 = parse_time(m.group(1))
        t2 = parse_time(m.group(2))
        r = IRRule(type="rrule", freq="hourly", interval=1, between_time=IRBetweenTime(t1, t2))
        r.window_date = window if (window.start or window.end or window.until) else None
        r.except_ = ex
        r.weekend_shift = weekend_shift
        return r

    # ---- every <n> units [on ...] [at ...] ----
    m = re.fullmatch(
        r"every\s+(\d+)\s+(minutes|hours|days|weeks)(?:\s+on\s+(.+?))?(?:\s+at\s+(.+))?",
        s_lower,
    )
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        on_part = (m.group(3) or "").strip()
        at_part = (m.group(4) or "").strip()

        freq = {"minutes": "minutely", "hours": "hourly", "days": "daily", "weeks": "weekly"}[unit]

        bywd = None
        if on_part:
            wds = parse_weekday_list(on_part)
            if wds:
                bywd = [WEEKDAY_MAP[w] for w in wds]

        times: List[time] = []
        if at_part:
            at_part = at_part.replace(",", " ")
            chunks = [c for c in at_part.split() if c.lower() not in {"and"}]
            times = [parse_time(c) for c in chunks]

        r = IRRule(type="rrule", freq=freq, interval=n, byweekday=bywd, times=times)
        r.window_date = window if (window.start or window.end or window.until) else None
        r.except_ = ex
        r.weekend_shift = weekend_shift
        return r

    # ---- every weekday at ... ----
    m = re.fullmatch(r"every\s+weekday\s+at\s+(.+)", s_lower)
    if m:
        at_part = m.group(1).replace(",", " ")
        chunks = [c for c in at_part.split() if c.lower() not in {"and"}]
        times = [parse_time(c) for c in chunks]
        r = IRRule(type="rrule", freq="daily", interval=1, byweekday=[0, 1, 2, 3, 4], times=times)
        r.window_date = window if (window.start or window.end or window.until) else None
        r.except_ = ex
        r.weekend_shift = weekend_shift
        return r

    # ---- every day at ... ----
    m = re.fullmatch(r"every\s+day\s+at\s+(.+)", s_lower)
    if m:
        at_part = m.group(1).replace(",", " ")
        chunks = [c for c in at_part.split() if c.lower() not in {"and"}]
        times = [parse_time(c) for c in chunks]
        r = IRRule(type="rrule", freq="daily", interval=1, times=times)
        r.window_date = window if (window.start or window.end or window.until) else None
        r.except_ = ex
        r.weekend_shift = weekend_shift
        return r

    # ---- every <weekday list> at ... ----
    m = re.fullmatch(r"every\s+(.+?)\s+at\s+(.+)", s_lower)
    if m:
        days_part = m.group(1).strip()
        at_part = m.group(2).strip()
        tokens = [t for t in re.split(r"[,\s]+", days_part) if t and t != "and"]
        if tokens and all(t in WEEKDAYS for t in tokens):
            at_part = at_part.replace(",", " ")
            chunks = [c for c in at_part.split() if c.lower() not in {"and"}]
            times = [parse_time(c) for c in chunks]
            r = IRRule(type="rrule", freq="weekly", interval=1,
                       byweekday=[WEEKDAY_MAP[w] for w in tokens],
                       times=times)
            r.window_date = window if (window.start or window.end or window.until) else None
            r.except_ = ex
            r.weekend_shift = weekend_shift
            return r

    # ---- yearly: every year on the last sunday of october at 23:00 ----
    m = re.fullmatch(
        r"every\s+year\s+on\s+the\s+"
        r"(first|second|third|fourth|fifth|last)\s+"
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+"
        r"of\s+"
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+"
        r"at\s+(.+)",
        s_lower,
    )
    if m:
        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        pos = ORDINAL[m.group(1)]
        wd = WEEKDAY_MAP[m.group(2)]
        mm = month_map[m.group(3)]
        at = parse_time(m.group(4))
        r = IRRule(type="rrule", freq="yearly", interval=1,
                   bymonth=[mm], byweekday=[wd], bysetpos=[pos], times=[at])
        r.window_date = window if (window.start or window.end or window.until) else None
        r.except_ = ex
        r.weekend_shift = weekend_shift
        return r

    # ---- every month on the ... at ... ----
    m = re.fullmatch(r"every\s+month\s+on\s+the\s+(.+?)\s+at\s+(.+)", s_lower)
    if m:
        on_part = m.group(1).strip()
        at = parse_time(m.group(2).strip())

        if on_part == "last day":
            r = IRRule(type="rrule", freq="monthly", interval=1, bymonthday=[-1], times=[at])
        else:
            nums = re.findall(r"(\d{1,2})(?:st|nd|rd|th)?", on_part)
            if nums and all(1 <= int(x) <= 31 for x in nums):
                r = IRRule(type="rrule", freq="monthly", interval=1,
                           bymonthday=[int(x) for x in nums], times=[at])
            else:
                m2 = re.fullmatch(
                    r"(first|second|third|fourth|fifth|last)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
                    on_part,
                )
                if not m2:
                    raise ValueError(f"Unsupported rule: {text!r}")
                pos = ORDINAL[m2.group(1)]
                wd = WEEKDAY_MAP[m2.group(2)]
                r = IRRule(type="rrule", freq="monthly", interval=1,
                           byweekday=[wd], bysetpos=[pos], times=[at])

        r.window_date = window if (window.start or window.end or window.until) else None
        r.except_ = ex
        r.weekend_shift = weekend_shift
        return r

    raise ValueError(f"Unsupported rule: {text!r}")
