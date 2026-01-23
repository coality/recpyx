from __future__ import annotations

import re
from typing import Optional

import en_impl

# FR -> IR.
# Strategy: normalize French surface forms into the supported EN grammar,
# then reuse the proven EN->IR parser.
#
# This is still "FR -> IR" from API perspective (returns IR), without running the engine.

_FR_WD = {
    "lundi": "monday",
    "mardis?": "tuesday",
    "mardi": "tuesday",
    "mercredi": "wednesday",
    "jeudi": "thursday",
    "vendredi": "friday",
    "samedi": "saturday",
    "dimanche": "sunday",
    "lundis": "monday",
    "mardis": "tuesday",
    "mercredis": "wednesday",
    "jeudis": "thursday",
    "vendredis": "friday",
    "samedis": "saturday",
    "dimanches": "sunday",
}

# order matters: longer first
_FR_MONTH_ORD = [
    ("premier", "first"),
    ("deuxième", "second"),
    ("deuxieme", "second"),
    ("troisième", "third"),
    ("troisieme", "third"),
    ("quatrième", "fourth"),
    ("quatrieme", "fourth"),
    ("cinquième", "fifth"),
    ("cinquieme", "fifth"),
    ("dernier", "last"),
    ("dernière", "last"),
    ("derniere", "last"),
]

_TIME_H_RE = re.compile(r"(?<!\d)(\d{1,2})h(?:(\d{2}))?(?!\d)", re.I)


def _fr_time_to_en(s: str) -> str:
    # 10h -> 10:00 ; 10h00 -> 10:00 ; 08h30 -> 08:30
    def repl(m: re.Match) -> str:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        return f"{hh:02d}:{mm:02d}"

    return _TIME_H_RE.sub(repl, s)


def _norm_spaces(s: str) -> str:
    s = s.replace("’", "'")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _wd_fr_to_en(s: str) -> str:
    # replace standalone weekday words (sing/plural)
    out = s
    for fr, en in [
        ("lundis", "monday"),
        ("lundi", "monday"),
        ("mardis", "tuesday"),
        ("mardi", "tuesday"),
        ("mercredis", "wednesday"),
        ("mercredi", "wednesday"),
        ("jeudis", "thursday"),
        ("jeudi", "thursday"),
        ("vendredis", "friday"),
        ("vendredi", "friday"),
        ("samedis", "saturday"),
        ("samedi", "saturday"),
        ("dimanches", "sunday"),
        ("dimanche", "sunday"),
    ]:
        out = re.sub(rf"\b{fr}\b", en, out, flags=re.I)
    return out


def fr_to_en_rule(fr_rule: str) -> str:
    s = _norm_spaces(fr_rule)

    # timezone: "(Europe/Paris)" => "in Europe/Paris"
    m = re.search(r"\(([^)]+/[^)]+)\)\s*$", s)
    tz_suffix = ""
    if m:
        tz = m.group(1).strip()
        s = s[: m.start()].strip()
        tz_suffix = f" in {tz}"

    s = _fr_time_to_en(s)
    s = re.sub(r"\bà\b", " a ", s)
    # do NOT split "au" (would break words like "sauf")
    s = _norm_spaces(s)

    # composed rules: ", et " => ", and "
    s = re.sub(r"\s*,\s*et\s+", ", and ", s, flags=re.I)

    # date windows
    s = re.sub(
        r"\bentre\s+le\s+(\d{4}-\d{2}-\d{2})\s+et\s+le\s+(\d{4}-\d{2}-\d{2})\b",
        r"between \1 and \2",
        s,
        flags=re.I,
    )
    # time range: "entre 09h00 et 17h00"
    s = re.sub(
        r"\bentre\s+(\d{2}:\d{2})\s+et\s+(\d{2}:\d{2})\b",
        r"between \1 and \2",
        s,
        flags=re.I,
    )
    s = re.sub(r"\bjusqu\'?au\s+(\d{4}-\d{2}-\d{2})\b", r"until \1", s, flags=re.I)

    # weekend shift
    s = re.sub(
        r"\bsi\s+week-?end\s+alors\s+lundi\s+suivant\b",
        "if weekend then next monday",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"\bsi\s+week-?end\s+alors\s+prochain\s+jour\s+ouvr[eé]\b",
        "if weekend then next business day",
        s,
        flags=re.I,
    )
    # cleanup commas before suffix clauses
    s = re.sub(
        r",\s*(if\s+weekend\s+then\s+next\s+(?:monday|business\s+day))\b",
        r" \1",
        s,
        flags=re.I,
    )
    s = re.sub(r",\s*$", "", s)

    # frequency base phrases
    s = re.sub(r"\b(tous|toutes)\s+les\b", "every", s, flags=re.I)
    s = re.sub(r"\bjour\s+ouvr[eé]s\b", "weekday", s, flags=re.I)
    s = re.sub(r"\bjours\s+ouvr[eé]s\b", "weekday", s, flags=re.I)
    s = re.sub(r"\bjours\b", "days", s, flags=re.I)
    s = re.sub(r"\bjour\b", "day", s, flags=re.I)
    s = re.sub(r"\bsemaines\b", "weeks", s, flags=re.I)
    s = re.sub(r"\bsemaine\b", "week", s, flags=re.I)
    s = re.sub(r"\bheures\b", "hours", s, flags=re.I)
    s = re.sub(r"\bheure\b", "hour", s, flags=re.I)
    s = re.sub(r"\bminutes\b", "minutes", s, flags=re.I)
    s = re.sub(r"\bminute\b", "minute", s, flags=re.I)

    # fix plural artefacts
    s = re.sub(r"\bevery\s+days\b", "every day", s, flags=re.I)
    s = re.sub(r"\bevery\s+weekdays\b", "every weekday", s, flags=re.I)
    s = re.sub(r"\bevery\s+hours\b", "every hour", s, flags=re.I)
    s = re.sub(r"\bevery\s+minutes\b", "every minute", s, flags=re.I)
    s = re.sub(r"\bevery\s+weeks\b", "every week", s, flags=re.I)

    # months / years
    s = re.sub(r"\bmois\b", "month", s, flags=re.I)
    s = re.sub(r"\bans\b", "years", s, flags=re.I)
    s = re.sub(r"\ban\b", "year", s, flags=re.I)

    # singularize after FR->EN unit replacements
    s = re.sub(r"\bevery\s+years\b", "every year", s, flags=re.I)

    # ordinal day-of-month: "1er" -> "1st"
    s = re.sub(r"\b1er\b", "1st", s, flags=re.I)

    # "dernier jour" -> "last day"
    s = re.sub(r"\bdernier\s+jour\b", "last day", s, flags=re.I)

    # nth weekday in month: "le premier lundi" -> "the first monday"
    for fr, en in _FR_MONTH_ORD:
        s = re.sub(rf"\b{re.escape(fr)}\b", en, s, flags=re.I)

    # weekdays
    s = _wd_fr_to_en(s)

    # french months (for yearly "of <month>")
    month_map = {
        "janvier": "january",
        "février": "february",
        "fevrier": "february",
        "mars": "march",
        "avril": "april",
        "mai": "may",
        "juin": "june",
        "juillet": "july",
        "août": "august",
        "aout": "august",
        "septembre": "september",
        "octobre": "october",
        "novembre": "november",
        "décembre": "december",
        "decembre": "december",
    }
    for fr_m, en_m in month_map.items():
        s = re.sub(rf"\bd[\\'’]{fr_m}\b", f"of {en_m}", s, flags=re.I)
        s = re.sub(rf"\bde\s+{fr_m}\b", f"of {en_m}", s, flags=re.I)

    # ensure "every year on the <ordinal> <weekday> of <month>"
    s = re.sub(
        r"\bevery\s+year\s+on\s+(first|second|third|fourth|fifth|last)\b",
        r"every year on the \1",
        s,
        flags=re.I,
    )

    # connectors: "et" between weekdays / times -> "and"
    s = re.sub(r"\b(et)\b", "and", s, flags=re.I)

    # "sauf" -> "except"
    s = re.sub(r"\bsauf\b", "except", s, flags=re.I)

    # normalize commas
    s = re.sub(r"\s*,\s*", ", ", s)
    s = _norm_spaces(s)

    # Handle special patterns:
    # - "every day, every 2 hours between ..." -> "every day every 2 hours between ..."
    s = re.sub(
        r"^(every\s+(?:day|weekday))\s*,\s*every\s+(\d+)\s+(hours|minutes)\s+between\b",
        r"\1 every \2 \3 between",
        s,
        flags=re.I,
    )

    # - "every month le X ..." -> "every month on the X ..."
    s = re.sub(r"\bevery\s+month\s+le\b", "every month on the", s, flags=re.I)

    # ensure "every month" has "on the"
    s = re.sub(r"^(every\s+month)\s+(?!on\b)", r"\1 on the ", s, flags=re.I)

    # yearly forms:
    s = re.sub(r"\bevery\s+year\s+le\b", "every year on", s, flags=re.I)

    # "every year le 03-12 a 12:30" -> "every year on 03-12 at 12:30"
    s = re.sub(
        r"^(every\s+year)\s+le\s+(\d{2}-\d{2})\s+a\s+(\d{2}:\d{2})$",
        r"\1 on \2 at \3",
        s,
        flags=re.I,
    )

    # one-shot: "le 2026-03-13 a 02:00" -> "2026-03-13 at 02:00"
    s = re.sub(
        r"^le\s+(\d{4}-\d{2}-\d{2})\s+a\s+(\d{2}:\d{2})$",
        r"\1 at \2",
        s,
        flags=re.I,
    )

    # generic: " a " -> " at "
    s = re.sub(r"\sa\s+(\d{2}:\d{2})", r" at \1", s, flags=re.I)

    # one-shot: remove leading "le" even inside composed schedules
    s = re.sub(
        r"\ble\s+(\d{4}-\d{2}-\d{2})\s+at\s+(\d{2}:\d{2})\b",
        r"\1 at \2",
        s,
        flags=re.I,
    )

    # "le monday" after conversions: remove "le" when it remains
    s = re.sub(
        r"\ble\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\1",
        s,
        flags=re.I,
    )

    # "every 3 weeks monday at 08:30" needs "on monday"
    s = re.sub(
        r"^(every\s+\d+\s+weeks)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\1 on \2",
        s,
        flags=re.I,
    )

    # final tidy
    # final fixups for yearly nth-weekday patterns
    s = re.sub(
        r"\bevery\s+year\s+on\s+(first|second|third|fourth|fifth|last)\b",
        r"every year on the \1",
        s,
        flags=re.I,
    )

    s = _norm_spaces(s) + tz_suffix
    return s


def parse_schedule(fr_text: str, default_tz: str = "Europe/Paris") -> en_impl.ScheduleSpec:
    en = fr_to_en_rule(fr_text)
    return en_impl.parse_schedule(en, default_tz=default_tz)


def parse_rule(fr_text: str) -> en_impl.RuleSpec:
    en = fr_to_en_rule(fr_text)
    return en_impl.parse_rule(en)
