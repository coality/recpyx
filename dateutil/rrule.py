from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import Iterable, List, Optional, Sequence

MINUTELY = "minutely"
HOURLY = "hourly"
DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"
YEARLY = "yearly"


@dataclass(frozen=True)
class Weekday:
    weekday: int


MO = Weekday(0)
TU = Weekday(1)
WE = Weekday(2)
TH = Weekday(3)
FR = Weekday(4)
SA = Weekday(5)
SU = Weekday(6)


def _normalize_weekdays(values: Optional[Sequence[Weekday | int]]) -> Optional[List[int]]:
    if values is None:
        return None
    normalized = []
    for item in values:
        if isinstance(item, Weekday):
            normalized.append(item.weekday)
        else:
            normalized.append(int(item))
    return normalized


def _last_day_of_month(year: int, month: int) -> int:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day


def _add_months(year: int, month: int, months: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + months
    new_year = total // 12
    new_month = total % 12 + 1
    return new_year, new_month


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


class rrule:
    def __init__(
        self,
        *,
        freq: str,
        interval: int = 1,
        dtstart: datetime,
        bymonth: Optional[Sequence[int]] = None,
        byweekday: Optional[Sequence[Weekday | int]] = None,
        bymonthday: Optional[Sequence[int]] = None,
        bysetpos: Optional[Sequence[int]] = None,
        byhour: Optional[int] = None,
        byminute: Optional[int] = None,
    ) -> None:
        self.freq = freq
        self.interval = interval
        self.dtstart = dtstart.replace(second=0, microsecond=0)
        self.bymonth = list(bymonth) if bymonth else None
        self.byweekday = _normalize_weekdays(byweekday)
        self.bymonthday = list(bymonthday) if bymonthday else None
        self.bysetpos = list(bysetpos) if bysetpos else None
        self.byhour = byhour
        self.byminute = byminute

    def after(self, dt: datetime, inc: bool = False) -> Optional[datetime]:
        target = dt
        inclusive = inc
        if self.freq == MINUTELY:
            return self._after_minutely(target, inclusive)
        if self.freq == HOURLY:
            return self._after_hourly(target, inclusive)
        if self.freq == DAILY:
            return self._after_daily(target, inclusive)
        if self.freq == WEEKLY:
            return self._after_weekly(target, inclusive)
        if self.freq == MONTHLY:
            return self._after_monthly(target, inclusive)
        if self.freq == YEARLY:
            return self._after_yearly(target, inclusive)
        raise ValueError(f"Unsupported frequency: {self.freq}")

    def _time_for(self, base: datetime) -> datetime:
        hour = self.byhour if self.byhour is not None else base.hour
        minute = self.byminute if self.byminute is not None else base.minute
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _after_minutely(self, target: datetime, inclusive: bool) -> Optional[datetime]:
        step = timedelta(minutes=self.interval)
        candidate = self.dtstart
        while candidate < target or (not inclusive and candidate == target):
            candidate += step
        return candidate

    def _after_hourly(self, target: datetime, inclusive: bool) -> Optional[datetime]:
        step = timedelta(hours=self.interval)
        candidate = self.dtstart
        while candidate < target or (not inclusive and candidate == target):
            candidate += step
        return candidate

    def _after_daily(self, target: datetime, inclusive: bool) -> Optional[datetime]:
        step = timedelta(days=self.interval)
        candidate = self.dtstart
        while candidate < target or (not inclusive and candidate == target):
            candidate += step

        while True:
            if self.byweekday is None or candidate.weekday() in self.byweekday:
                return candidate
            candidate += step

    def _weekly_candidates_for_week(self, week_start: date) -> List[datetime]:
        weekdays = self.byweekday or [self.dtstart.weekday()]
        candidates = []
        for wd in sorted(set(weekdays)):
            day = week_start + timedelta(days=wd)
            dt = datetime(day.year, day.month, day.day, tzinfo=self.dtstart.tzinfo)
            candidates.append(self._time_for(dt))
        return sorted(candidates)

    def _after_weekly(self, target: datetime, inclusive: bool) -> Optional[datetime]:
        anchor_week = _week_start(self.dtstart.date())
        weeks = 0
        while True:
            week_start = anchor_week + timedelta(weeks=self.interval * weeks)
            for candidate in self._weekly_candidates_for_week(week_start):
                if candidate > target or (inclusive and candidate == target):
                    return candidate
            weeks += 1

    def _month_candidates(self, year: int, month: int) -> List[datetime]:
        tzinfo = self.dtstart.tzinfo
        if self.bymonth and month not in self.bymonth:
            return []

        candidates: List[datetime] = []
        if self.bysetpos and self.byweekday:
            matches = []
            last_day = _last_day_of_month(year, month)
            for day in range(1, last_day + 1):
                d = date(year, month, day)
                if d.weekday() in self.byweekday:
                    matches.append(d)
            for pos in self.bysetpos:
                if pos == 0:
                    continue
                idx = pos - 1 if pos > 0 else pos
                try:
                    chosen = matches[idx]
                except IndexError:
                    continue
                dt = datetime(chosen.year, chosen.month, chosen.day, tzinfo=tzinfo)
                candidates.append(self._time_for(dt))
        elif self.bymonthday:
            last_day = _last_day_of_month(year, month)
            for day in self.bymonthday:
                if day == -1:
                    d = date(year, month, last_day)
                else:
                    if not (1 <= day <= last_day):
                        continue
                    d = date(year, month, day)
                dt = datetime(d.year, d.month, d.day, tzinfo=tzinfo)
                candidates.append(self._time_for(dt))
        else:
            dt = datetime(year, month, self.dtstart.day, tzinfo=tzinfo)
            candidates.append(self._time_for(dt))

        return sorted(set(candidates))

    def _after_monthly(self, target: datetime, inclusive: bool) -> Optional[datetime]:
        anchor_year = self.dtstart.year
        anchor_month = self.dtstart.month
        months = 0
        while True:
            year, month = _add_months(anchor_year, anchor_month, self.interval * months)
            for candidate in self._month_candidates(year, month):
                if candidate > target or (inclusive and candidate == target):
                    return candidate
            months += 1

    def _year_candidates(self, year: int) -> List[datetime]:
        months = self.bymonth or [self.dtstart.month]
        candidates: List[datetime] = []
        for month in months:
            candidates.extend(self._month_candidates(year, month))
        return sorted(candidates)

    def _after_yearly(self, target: datetime, inclusive: bool) -> Optional[datetime]:
        anchor_year = self.dtstart.year
        years = 0
        while True:
            year = anchor_year + self.interval * years
            for candidate in self._year_candidates(year):
                if candidate > target or (inclusive and candidate == target):
                    return candidate
            years += 1


class rruleset:
    def __init__(self) -> None:
        self._rules: List[rrule] = []

    def rrule(self, rule: rrule) -> None:
        self._rules.append(rule)

    def after(self, dt: datetime, inc: bool = False) -> Optional[datetime]:
        next_values = [rule.after(dt, inc=inc) for rule in self._rules]
        candidates = [value for value in next_values if value is not None]
        return min(candidates) if candidates else None
