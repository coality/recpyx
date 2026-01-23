# engine.py
"""
IR -> engine (next occurrence)

Depends on:
  - en_impl.py (EN -> IR parser + IR dataclasses)

Public API:
  - next_occurrence(text, now=None, default_tz="Europe/Paris") -> datetime
  - validate(text, now=None, default_tz="Europe/Paris") -> None | raises InvalidRuleError
"""

from __future__ import annotations

from datetime import datetime, timedelta, time, date
from zoneinfo import ZoneInfo
from typing import Optional, List, Tuple

from dateutil.rrule import (
    rrule, rruleset,
    MINUTELY, HOURLY, DAILY, WEEKLY, MONTHLY, YEARLY,
    MO, TU, WE, TH, FR, SA, SU,
)

#from en_impl import (
#    parse_schedule,
#    IRSchedule, IRRule, IRWindowDate, IRBetweenTime, IRStep,
#)

class InvalidRuleError(ValueError):
    pass

FREQ_MAP = {
    "minutely": MINUTELY,
    "hourly": HOURLY,
    "daily": DAILY,
    "weekly": WEEKLY,
    "monthly": MONTHLY,
    "yearly": YEARLY,
}

IDX_TO_DU = [MO, TU, WE, TH, FR, SA, SU]

def is_weekend(d: date) -> bool:
    return d.weekday() >= 5

def next_business_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d

def _combine_datetime(d: date, t: time, tzinfo: ZoneInfo) -> datetime:
    return datetime(d.year, d.month, d.day, t.hour, t.minute, 0, 0, tzinfo)

def _window_datetimes(w: Optional[IRWindowDate], tzinfo: ZoneInfo) -> Tuple[Optional[datetime], Optional[datetime]]:
    if not w:
        return None, None

    start_dt = None
    end_dt = None

    if w.start:
        start_dt = datetime(w.start.year, w.start.month, w.start.day, 0, 0, 0, tzinfo=tzinfo)
    if w.end:
        end_dt = datetime(w.end.year, w.end.month, w.end.day, 23, 59, 0, tzinfo=tzinfo)
    if w.until:
        until_dt = datetime(w.until.year, w.until.month, w.until.day, 23, 59, 0, tzinfo=tzinfo)
        end_dt = until_dt if end_dt is None else min(end_dt, until_dt)

    return start_dt, end_dt

def _apply_weekend_shift(dt: datetime, mode: str) -> datetime:
    if mode == "none":
        return dt
    d = dt.date()
    if not is_weekend(d):
        return dt
    if mode == "next_monday":
        while d.weekday() != 0:
            d += timedelta(days=1)
        return dt.replace(year=d.year, month=d.month, day=d.day)
    if mode == "next_business_day":
        d2 = next_business_day(d)
        return dt.replace(year=d2.year, month=d2.month, day=d2.day)
    return dt

def _excluded(dt: datetime, rule: IRRule, tzinfo: ZoneInfo) -> bool:
    # hourly filter window (HOURLY + between_time only)
    if rule.type == "rrule" and rule.freq == "hourly" and rule.between_time and rule.step is None:
        t = dt.timetz().replace(tzinfo=None)
        if not (rule.between_time.start <= t <= rule.between_time.end):
            return True

    if dt.weekday() in rule.except_.weekdays:
        return True
    if dt.date() in rule.except_.dates:
        return True

    # Not used in your tests; keep explicit to avoid silent wrong behavior.
    if rule.except_.holidays.enabled:
        raise RuntimeError("Public holidays exclusion not implemented (plug holidays here).")

    return False

def _build_rruleset(rule: IRRule, tzinfo: ZoneInfo, now: datetime, w_start: Optional[datetime]) -> rruleset:
    rs = rruleset()
    dtstart = (w_start or now).replace(second=0, microsecond=0)

    # Anchor nth weekday monthly/yearly to period start to avoid "first monday after now" bug.
    if rule.freq in {"monthly", "yearly"} and rule.bysetpos and rule.byweekday:
        if rule.freq == "monthly":
            dtstart = dtstart.replace(day=1, hour=0, minute=0)
        else:
            dtstart = dtstart.replace(month=1, day=1, hour=0, minute=0)

    freq_const = FREQ_MAP[rule.freq]  # type: ignore

    def add_rr(dt0: datetime, hour: Optional[int] = None, minute: Optional[int] = None) -> None:
        rs.rrule(
            rrule(
                freq=freq_const,
                interval=rule.interval,
                dtstart=dt0,
                bymonth=rule.bymonth,
                byweekday=[IDX_TO_DU[i] for i in rule.byweekday] if rule.byweekday else None,
                bymonthday=rule.bymonthday,
                bysetpos=rule.bysetpos,
                byhour=hour,
                byminute=minute,
            )
        )

    # Step-within-day: base DAILY, expanded later
    if rule.step is not None and rule.between_time is not None and rule.freq == "daily":
        add_rr(dtstart)
        return rs

    # Normal rules: 1 rrule per time
    if rule.times:
        for t in rule.times:
            add_rr(dtstart.replace(hour=t.hour, minute=t.minute), hour=t.hour, minute=t.minute)
    else:
        add_rr(dtstart)

    return rs

def _step_to_timedelta(step: IRStep) -> timedelta:
    if step.hours is not None:
        return timedelta(hours=step.hours)
    if step.minutes is not None:
        return timedelta(minutes=step.minutes)
    raise ValueError("Invalid step: missing hours/minutes")

def _expand_step_within_day(base_dt: datetime, rule: IRRule, tzinfo: ZoneInfo, after_dt: datetime) -> Optional[datetime]:
    assert rule.step and rule.between_time
    step = _step_to_timedelta(rule.step)

    d = base_dt.date()
    cur = _combine_datetime(d, rule.between_time.start, tzinfo)
    end_dt = _combine_datetime(d, rule.between_time.end, tzinfo)

    while cur <= end_dt:
        if cur > after_dt:
            return cur
        cur += step
    return None

def next_occurrence(text: str, now: Optional[datetime] = None, default_tz: str = "Europe/Paris") -> datetime:
    sched: IRSchedule = parse_schedule(text, default_tz=default_tz)
    tzinfo = ZoneInfo(sched.tz)

    now = now or datetime.now(tzinfo)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tzinfo)

    candidates: List[datetime] = []

    for r in sched.rules:
        w_start, w_end = _window_datetimes(r.window_date, tzinfo)

        # oneshot
        if r.type == "oneshot":
            dt = r.at
            assert dt is not None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tzinfo)
            if dt > now and not _excluded(dt, r, tzinfo):
                candidates.append(dt)
            continue

        rs = _build_rruleset(r, tzinfo, now, w_start)

        probe = now
        for _ in range(500):
            base = rs.after(probe, inc=False)
            if base is None:
                break

            dt = base

            # Step-within-day
            if r.step and r.between_time:
                # If rrule jumped to next day, try same-day base once.
                if dt.date() != probe.date():
                    day_probe = probe.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
                    base_today = rs.after(day_probe, inc=False)
                    if base_today is not None and base_today.date() == probe.date():
                        dt = base_today

                dt2 = _expand_step_within_day(dt, r, tzinfo, after_dt=probe)
                if dt2 is None:
                    next_day = dt.date() + timedelta(days=1)
                    probe = datetime(next_day.year, next_day.month, next_day.day, 0, 0, 0, tzinfo=tzinfo)
                    continue
                dt = dt2

            dt = _apply_weekend_shift(dt, r.weekend_shift)

            if w_start and dt < w_start:
                probe = w_start - timedelta(seconds=1)
                continue
            if w_end and dt > w_end:
                break

            if _excluded(dt, r, tzinfo):
                probe = dt + timedelta(seconds=1)
                continue

            candidates.append(dt)
            break

    if not candidates:
        raise RuntimeError("No next occurrence found (rules ended or filtered out).")

    return min(candidates)

def validate(rule_text: str, now: Optional[datetime] = None, default_tz: str = "Europe/Paris") -> None:
    sched: IRSchedule = parse_schedule(rule_text, default_tz=default_tz)
    tzinfo = ZoneInfo(sched.tz)

    now = now or datetime.now(tzinfo)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tzinfo)
    now = now.replace(second=0, microsecond=0)

    for r in sched.rules:
        w_start, w_end = _window_datetimes(r.window_date, tzinfo)
        if w_start and w_end and w_end < w_start:
            raise InvalidRuleError(f"Invalid window: end < start for rule '{rule_text}'")

        if r.type == "oneshot":
            dt = r.at
            assert dt is not None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tzinfo)

            if dt.weekday() in r.except_.weekdays:
                raise InvalidRuleError(f"One-shot excluded by weekday exception for rule '{rule_text}'")
            if dt.date() in r.except_.dates:
                raise InvalidRuleError(f"One-shot excluded by date exception for rule '{rule_text}'")
            if w_start and dt < w_start:
                raise InvalidRuleError(f"One-shot before window start for rule '{rule_text}'")
            if w_end and dt > w_end:
                raise InvalidRuleError(f"One-shot after window end for rule '{rule_text}'")
            continue

        horizon_end = w_end or (now + timedelta(days=366))
        try:
            dt = next_occurrence(rule_text, now=now, default_tz=default_tz)
        except RuntimeError:
            raise InvalidRuleError(f"No occurrence exists in horizon for rule '{rule_text}'")

        if dt > horizon_end:
            raise InvalidRuleError(f"No occurrence exists in horizon for rule '{rule_text}'")

# ------------------ full unit test suite (your list) ------------------

def test():
    """
    Fixed reference date: 2026-03-12 12:00 in Europe/Paris
    """
    tz = "Europe/Paris"
    now = datetime(2026, 3, 12, 12, 0, 0, tzinfo=ZoneInfo(tz))

    cases = [
        # --- Basics ---
        ("every sunday at 10AM", "2026-03-15T10:00:00"),
        ("every day at 3PM", "2026-03-12T15:00:00"),
        ("every day except wednesday at 10AM", "2026-03-13T10:00:00"),
        ("every 2 days at 10:00", "2026-03-14T10:00:00"),
        ("every 3 weeks on monday at 08:30", "2026-03-30T08:30:00"),
        ("every monday and thursday at 18:00", "2026-03-12T18:00:00"),
        ("every weekday at 09:00", "2026-03-13T09:00:00"),
        ("every day at 09:00 and 18:00", "2026-03-12T18:00:00"),
        ("every saturday at 10:00, 14:00, 18:00", "2026-03-14T10:00:00"),

        # --- Step within day window branch (DAILY + expand_step_within_day) ---
        ("every day every 2 hours between 09:00 and 17:00", "2026-03-12T13:00:00"),
        ("every weekday every 2 hours between 09:00 and 17:00", "2026-03-12T13:00:00"),

        # --- HOURLY between_times (filter in _excluded) ---
        ("every 2 hours between 09:00 and 17:00", "2026-03-12T14:00:00"),
        ("every hour between 18:00 and 23:00", "2026-03-12T18:00:00"),

        # --- Date windows ---
        ("every weekday at 15:00 between 2026-02-01 and 2026-03-31", "2026-03-12T15:00:00"),
        ("every day at 10:00 until 2026-12-31", "2026-03-13T10:00:00"),

        # --- Monthly day-of-month variants ---
        ("every month on the 1st at 09:00", "2026-04-01T09:00:00"),
        ("every month on the last day at 20:00", "2026-03-31T20:00:00"),
        ("every month on the 2nd and 15th at 08:00", "2026-03-15T08:00:00"),
        ("every month on the 15th at 08:00", "2026-03-15T08:00:00"),
        ("every month on the 31st at 20:00", "2026-03-31T20:00:00"),

        # --- Monthly nth weekday variants (MONTHLY + bysetpos + anchor) ---
        ("every month on the first monday at 09:00", "2026-04-06T09:00:00"),
        ("every month on the last friday at 18:00", "2026-03-27T18:00:00"),

        # --- Exceptions ---
        ("every day at 10:00 except 2026-03-13", "2026-03-14T10:00:00"),
        ("every day at 10:00 except 2026-12-25, 2026-01-01", "2026-03-13T10:00:00"),
        ("every weekday except friday at 09:00", "2026-03-16T09:00:00"),
        ("every day except wednesday and sunday at 10:00", "2026-03-13T10:00:00"),

        # --- Composed rules (min of candidates) ---
        ("every weekday at 09:00, and every saturday at 10:30", "2026-03-13T09:00:00"),
        ("every day at 18:00, and 2026-03-13 at 02:00", "2026-03-12T18:00:00"),

        # --- Weekend shift ---
        ("every month on the 1st at 09:00 between 2026-08-01 and 2026-08-31 if weekend then next monday",
         "2026-08-03T09:00:00"),
        ("every month on the 1st at 09:00 between 2026-08-01 and 2026-08-31 if weekend then next business day",
         "2026-08-03T09:00:00"),

        # --- Timezones ---
        ("every day at 10:00 in Europe/Paris", "2026-03-13T10:00:00"),
        ("every day at 10:00 in America/New_York", "2026-03-13T10:00:00"),

        # --- One-shot ---
        ("2026-03-13 at 2:00", "2026-03-13T02:00:00"),

        # --- Yearly ---
        ("every year on 03-14 at 10:00", "2026-03-14T10:00:00"),
        ("every year on 03-01 at 10:00", "2027-03-01T10:00:00"),
        ("every day except thursday at 18:00", "2026-03-13T18:00:00"),
        ("every day except friday at 18:00", "2026-03-12T18:00:00"),
        ("every day except wednesday and sunday at 10:00", "2026-03-13T10:00:00"),

        # --- except weekdays with weekday rule ---
        ("every weekday except thursday at 15:00", "2026-03-13T15:00:00"),
        ("every weekday except friday at 09:00", "2026-03-16T09:00:00"),
        ("every monday and thursday except thursday at 18:00", "2026-03-16T18:00:00"),

        # --- except at end (postfix) ---
        ("every day at 18:00 except thursday", "2026-03-13T18:00:00"),
        ("every weekday at 09:00 except friday", "2026-03-16T09:00:00"),

        # --- except dates (single + multiple) ---
        ("every day at 10:00 except 2026-03-13", "2026-03-14T10:00:00"),
        ("every day at 10:00 except 2026-03-13, 2026-03-14", "2026-03-15T10:00:00"),
        ("every day at 10:00 except 2026-03-13 2026-03-14", "2026-03-15T10:00:00"),

        # --- except dates on weekly rule ---
        ("every sunday at 10AM except 2026-03-15", "2026-03-22T10:00:00"),

        # --- except combined (weekday + date) ---
        ("every day except friday 2026-03-15 at 10:00", "2026-03-14T10:00:00"),
        ("every weekday except friday 2026-03-16 at 09:00", "2026-03-17T09:00:00"),

        # --- except with between window (step-within-day) ---
        ("every day every 2 hours between 09:00 and 17:00 except thursday", "2026-03-13T09:00:00"),
        ("every day every 2 hours between 09:00 and 17:00 except friday", "2026-03-12T13:00:00"),

        # --- except with HOURLY-between (filter in _excluded) ---
        ("every 2 hours between 09:00 and 17:00 except thursday", "2026-03-13T10:00:00"),
        ("every hour between 18:00 and 23:00 except thursday", "2026-03-13T18:00:00"),

        ("every day at 18:00 until 2026-03-13 except 2026-03-12", "2026-03-13T18:00:00"),
        ("every day at 18:00 between 2026-03-12 and 2026-03-13 except 2026-03-12", "2026-03-13T18:00:00"),

        # --- composed rules: except applies per-rule (NOT global) ---
        ("every day at 18:00 except thursday, and 2026-03-13 at 02:00", "2026-03-13T02:00:00"),
        ("every day at 18:00 except friday, and 2026-03-13 at 02:00", "2026-03-12T18:00:00"),

        # --- monthly + except date ---
        ("every month on the 15th at 08:00 except 2026-03-15", "2026-04-15T08:00:00"),
        ("every month on the last day at 20:00 except 2026-03-31", "2026-04-30T20:00:00"),

        # --- nth weekday monthly + except date ---
        ("every month on the first monday at 09:00 except 2026-04-06", "2026-05-04T09:00:00"),

        # --- Daily + multi-times + except ---
        ("every day at 12:01", "2026-03-12T12:01:00"),
        ("every day at 12:00", "2026-03-13T12:00:00"),
        ("every day at 11:00, 12:30, 23:00", "2026-03-12T12:30:00"),
        ("every day except thursday at 12:30", "2026-03-13T12:30:00"),
        ("every day except thursday friday 2026-03-12 at 18:00", "2026-03-14T18:00:00"),
        ("every day at 18:00 except thursday", "2026-03-13T18:00:00"),
        ("every day at 18:00 except friday", "2026-03-12T18:00:00"),
        ("every day except friday 2026-03-15 at 18:00", "2026-03-12T18:00:00"),
        ("every day except thursday at 18:00 between 2026-03-12 and 2026-03-20", "2026-03-13T18:00:00"),
        ("every day at 18:00 between 2026-03-12 and 2026-03-15 except 2026-03-12, 2026-03-13", "2026-03-14T18:00:00"),

        # --- Weekday rules + except ---
        ("every weekday at 12:30", "2026-03-12T12:30:00"),
        ("every weekday at 13:00 except thursday", "2026-03-13T13:00:00"),
        ("every weekday at 13:00 except friday", "2026-03-12T13:00:00"),
        ("every weekday at 09:00 except thursday", "2026-03-13T09:00:00"),
        ("every weekday at 09:00 except friday", "2026-03-16T09:00:00"),
        ("every weekday at 15:30 between 2026-03-01 and 2026-03-31 except thursday", "2026-03-13T15:30:00"),
        ("every weekday at 15:30 until 2026-03-20 except 2026-03-13", "2026-03-12T15:30:00"),
        ("every weekday at 15:30 until 2026-03-20 except thursday", "2026-03-13T15:30:00"),
        ("every weekday at 09:00 between 2026-03-12 and 2026-03-16 except 2026-03-13", "2026-03-16T09:00:00"),
        ("every weekday at 09:00 between 2026-03-12 and 2026-03-16 except friday", "2026-03-16T09:00:00"),

        # --- Step-within-day (DAILY expand) + excepts ---
        ("every day every 30 minutes between 12:00 and 14:00", "2026-03-12T12:30:00"),
        ("every day every 30 minutes between 12:00 and 14:00 except thursday", "2026-03-13T12:00:00"),
        ("every weekday every 30 minutes between 12:00 and 14:00", "2026-03-12T12:30:00"),
        ("every weekday every 30 minutes between 12:00 and 14:00 except thursday", "2026-03-13T12:00:00"),
        ("every weekday every 90 minutes between 08:00 and 12:00 except friday", "2026-03-16T08:00:00"),
        ("every day every 2 hours between 09:00 and 17:00 except thursday", "2026-03-13T09:00:00"),
        ("every day every 2 hours between 09:00 and 17:00 except 2026-03-13", "2026-03-12T13:00:00"),
        ("every day every 2 hours between 09:00 and 17:00 between 2026-03-12 and 2026-03-14 except 2026-03-13", "2026-03-12T13:00:00"),
        ("every weekday every 2 hours between 09:00 and 17:00 between 2026-03-12 and 2026-03-14 except thursday", "2026-03-13T09:00:00"),
        ("every weekday every 2 hours between 09:00 and 17:00 between 2026-03-12 and 2026-03-14 except friday", "2026-03-12T13:00:00"),

        # --- HOURLY between window (filter) + except ---
        ("every 2 hours between 09:00 and 17:00", "2026-03-12T14:00:00"),
        ("every 2 hours between 09:00 and 17:00 except thursday", "2026-03-13T10:00:00"),
        ("every 3 hours between 08:00 and 23:00", "2026-03-12T15:00:00"),
        ("every 4 hours between 01:00 and 23:00 except thursday", "2026-03-13T04:00:00"),
        ("every hour between 12:00 and 14:00", "2026-03-12T13:00:00"),
        ("every hour between 12:00 and 14:00 except thursday", "2026-03-13T12:00:00"),
        ("every hour between 18:00 and 23:00 except thursday", "2026-03-13T18:00:00"),
        ("every 6 hours between 00:00 and 23:00", "2026-03-12T18:00:00"),

        # --- Minutes / hours pure intervals ---
        ("every 15 minutes", "2026-03-12T12:15:00"),
        ("every 45 minutes", "2026-03-12T12:45:00"),
        ("every 6 hours", "2026-03-12T18:00:00"),
        ("every 6 hours except thursday", "2026-03-13T00:00:00"),

        # --- Monthly (day-of-month) + except + windows ---
        ("every month on the 12th at 12:30", "2026-03-12T12:30:00"),
        ("every month on the 12th at 18:00", "2026-03-12T18:00:00"),
        ("every month on the 13th at 10:00", "2026-03-13T10:00:00"),
        ("every month on the 31st at 20:00 except 2026-03-31", "2026-05-31T20:00:00"),
        ("every month on the 15th at 08:00 except 2026-03-15", "2026-04-15T08:00:00"),
        ("every month on the last day at 20:00 except 2026-03-31", "2026-04-30T20:00:00"),
        ("every month on the 12th and 14th at 18:00", "2026-03-12T18:00:00"),
        ("every month on the 31st at 20:00 except 2026-03-31 and 2026-05-31", "2026-07-31T20:00:00"),

        # --- Monthly nth weekday (MONTHLY + bysetpos) ---
        ("every month on the second thursday at 18:00", "2026-03-12T18:00:00"),
        ("every month on the second thursday at 09:00", "2026-04-09T09:00:00"),
        ("every month on the third friday at 08:00", "2026-03-20T08:00:00"),
        ("every month on the last monday at 07:15", "2026-03-30T07:15:00"),
        ("every month on the fifth monday at 09:00", "2026-03-30T09:00:00"),

        # --- Composed (min candidate wins) ---
        ("2026-03-12 at 13:00, and every day at 18:00", "2026-03-12T13:00:00"),
        ("every day at 18:00 except thursday, and every day at 17:00", "2026-03-12T17:00:00"),
        ("every day at 18:00 except friday, and 2026-03-13 at 02:00", "2026-03-12T18:00:00"),

        # --- Yearly ---
        ("every year on 03-12 at 12:30", "2026-03-12T12:30:00"),
        ("every year on 03-12 at 11:00", "2027-03-12T11:00:00"),
        ("every year on the last sunday of october at 23:00", "2026-10-25T23:00:00"),
    ]

    for rule, expected_prefix in cases:
        print(rule)
        validate(rule, now=now, default_tz=tz)
        got = next_occurrence(rule, now=now, default_tz=tz)
        got_local = got.astimezone(ZoneInfo(tz)).replace(tzinfo=None).isoformat()
        assert got_local.startswith(expected_prefix), (
            f"\nRule: {rule}\nNow:  {now.isoformat()}\nGot:  {got.isoformat()} (local={got_local})\nExp:  {expected_prefix}..."
        )

    invalid_rules = [
        "every day at 10:00 until 2026-03-13 except 2026-03-13",
        "every day at 18:00 between 2026-03-12 and 2026-03-12 except 2026-03-12",
    ]
    for rule in invalid_rules:
        try:
            print(rule)
            validate(rule, now=now, default_tz=tz)
            raise AssertionError(f"Expected InvalidRuleError for: {rule}")
        except InvalidRuleError:
            pass

    print(f"OK: {len(cases)} tests passed.")

if __name__ == "__main__":
    test()
