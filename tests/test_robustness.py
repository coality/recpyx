"""
Robustness / edge-case regression tests.

Companion to test_engine.py (which covers the happy-path NL -> next_occurrence
matrix). This file pins down:
  - malformed input never crashes with an unexpected exception type;
  - zero / negative intervals and steps are rejected instead of hanging forever
    (the engine's dateutil.rrule loop and the step-within-day loop never advance
    with a 0 step -> previously an infinite loop / DoS);
  - empty or unparseable schedules raise InvalidRuleError, not a bare RuntimeError;
  - a handful of calendar edge cases (leap day, short months, nth-weekday gaps,
    weekend shift) resolve to the correct instant.

All cases pass an explicit `now` so they don't depend on the wall clock.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from recpyx import InvalidRuleError, next_occurrence, parse_rule, validate

PARIS = ZoneInfo("Europe/Paris")
NOW = datetime(2026, 3, 12, 12, 0, tzinfo=PARIS)


# --------------------------------------------------------------------------- #
# Infinite-loop guards: zero / negative interval & step
# --------------------------------------------------------------------------- #

ZERO_INTERVAL_RULES = [
    "every 0 days at 10:00",
    "every 0 weeks at 10:00",
    "every 0 hours",
    "every 0 minutes",
    "every 0 hours between 09:00 and 17:00",
    "every day every 0 hours between 09:00 and 17:00",
    "every day every 0 minutes between 09:00 and 17:00",
    "every weekday every 0 minutes between 09:00 and 17:00",
]


@pytest.mark.parametrize("rule", ZERO_INTERVAL_RULES, ids=ZERO_INTERVAL_RULES)
def test_zero_interval_or_step_rejected_not_hang(rule: str) -> None:
    # Must raise (a ValueError subclass) rather than loop forever.
    with pytest.raises(ValueError):
        next_occurrence(rule, now=NOW)


@pytest.mark.parametrize("rule", ZERO_INTERVAL_RULES, ids=ZERO_INTERVAL_RULES)
def test_zero_interval_rejected_by_validate(rule: str) -> None:
    with pytest.raises(ValueError):
        validate(rule, now=NOW)


def test_parse_rule_rejects_zero_interval() -> None:
    # The public parser (no engine) must also refuse to build a hanging IR.
    with pytest.raises(ValueError):
        parse_rule("every 0 days at 10:00")


def test_negative_interval_rejected() -> None:
    # "-1" is not even matched by the grammar -> unsupported, but must not crash.
    with pytest.raises(ValueError):
        next_occurrence("every -1 days at 10:00", now=NOW)


# --------------------------------------------------------------------------- #
# Empty / malformed input -> clean ValueError, never an unexpected exception
# --------------------------------------------------------------------------- #

EMPTY_RULES = ["", "   ", "\t\n"]


@pytest.mark.parametrize("rule", EMPTY_RULES, ids=["empty", "spaces", "ws"])
def test_empty_schedule_raises_invalid_rule(rule: str) -> None:
    with pytest.raises(InvalidRuleError):
        next_occurrence(rule, now=NOW)
    with pytest.raises(InvalidRuleError):
        validate(rule, now=NOW)


MALFORMED_RULES = [
    "garbage nonsense",
    "every",
    "every day at",
    "every day at 25:00",
    "every day at 10:99",
    "every day at 24:00",
    "every month on the 32nd at 10:00",
    "every month on the 0th at 10:00",
    "every 30 minutes between 09:00 and 17:00",  # minutely-between not supported
]


@pytest.mark.parametrize("rule", MALFORMED_RULES, ids=MALFORMED_RULES)
def test_malformed_input_raises_value_error(rule: str) -> None:
    # Whatever the parser decides, the caller-visible contract is "a ValueError",
    # never a TypeError / IndexError / hang.
    with pytest.raises(ValueError):
        next_occurrence(rule, now=NOW)


# --------------------------------------------------------------------------- #
# Public-holidays exclusion: parseable but unsupported -> clean error, both langs
# --------------------------------------------------------------------------- #

HOLIDAY_RULES = [
    "every day at 10:00 except on public holidays",
    "every day at 10:00 except public holidays",
    "tous les jours à 10h00 sauf les jours fériés",
    "tous les jours à 10h00 sauf jour férié",
]


@pytest.mark.parametrize("rule", HOLIDAY_RULES, ids=HOLIDAY_RULES)
def test_public_holidays_exclusion_rejected(rule: str) -> None:
    # Must raise InvalidRuleError (not crash with RuntimeError for EN, and not be
    # silently ignored for FR).
    with pytest.raises(InvalidRuleError):
        next_occurrence(rule, now=NOW)
    with pytest.raises(InvalidRuleError):
        validate(rule, now=NOW)


# --------------------------------------------------------------------------- #
# Calendar edge cases (locked-in correct answers)
# --------------------------------------------------------------------------- #

def _next_local(rule: str, now: datetime) -> str:
    return next_occurrence(rule, now=now).astimezone(PARIS).replace(tzinfo=None).isoformat()


@pytest.mark.parametrize(
    "rule, now, expected",
    [
        # leap day: 2026/2027 are not leap, 2028 is
        ("every year on 02-29 at 10:00", NOW, "2028-02-29T10:00:00"),
        # 31st skips 30-day months (April -> May)
        ("every month on the 31st at 20:00", datetime(2026, 4, 1, tzinfo=PARIS), "2026-05-31T20:00:00"),
        # last day of a short, non-leap February
        ("every month on the last day at 20:00", datetime(2026, 2, 10, tzinfo=PARIS), "2026-02-28T20:00:00"),
        # fifth monday: skips months that have only four (April & May 2026) -> June 29
        ("every month on the fifth monday at 09:00", datetime(2026, 4, 1, tzinfo=PARIS), "2026-06-29T09:00:00"),
        # weekend shift: 2026-07-04 is a Saturday -> next Monday
        ("every year on 07-04 at 09:00 if weekend then next monday", NOW, "2026-07-06T09:00:00"),
    ],
    ids=["leap-feb29", "31st-skips-april", "last-day-feb", "fifth-monday-gap", "weekend-shift-yearly"],
)
def test_calendar_edge_cases(rule: str, now: datetime, expected: str) -> None:
    assert _next_local(rule, now) == expected
