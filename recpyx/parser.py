from __future__ import annotations

import re
from typing import Callable

from . import en, fr

_FR_MARKERS = re.compile(
    r"\b("
    r"tous|toutes|sauf|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|"
    r"ouvr[eé]s?|semaine|semaines|mois|ans|an|entre|jusqu(?:'|’)?au|week-?end|"
    r"janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|"
    r"septembre|octobre|novembre|décembre|decembre"
    r")\b",
    re.I,
)
_EN_MARKERS = re.compile(
    r"\b("
    r"every|except|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"weekday|weekend|between|until|january|february|march|april|may|june|"
    r"july|august|september|october|november|december"
    r")\b",
    re.I,
)


def detect_language(text: str) -> str:
    fr_hits = len(_FR_MARKERS.findall(text))
    en_hits = len(_EN_MARKERS.findall(text))
    if fr_hits > en_hits:
        return "fr"
    if en_hits > fr_hits:
        return "en"
    return "en"


def _parse_with_fallback(
    text: str,
    default_tz: str,
    primary: Callable[[str, str], en.IRSchedule],
    secondary: Callable[[str, str], en.IRSchedule],
) -> en.IRSchedule:
    try:
        return primary(text, default_tz=default_tz)
    except ValueError:
        return secondary(text, default_tz=default_tz)


def parse_schedule(text: str, default_tz: str = "Europe/Paris") -> en.IRSchedule:
    lang = detect_language(text)
    if lang == "fr":
        return _parse_with_fallback(text, default_tz, fr.parse_schedule, en.parse_schedule)
    return _parse_with_fallback(text, default_tz, en.parse_schedule, fr.parse_schedule)


def parse_rule(text: str) -> en.IRRule:
    lang = detect_language(text)
    if lang == "fr":
        try:
            return fr.parse_rule(text)
        except ValueError:
            return en.parse_rule(text)
    try:
        return en.parse_rule(text)
    except ValueError:
        return fr.parse_rule(text)
