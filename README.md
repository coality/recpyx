# recpyx

recpyx is a pragmatic recurrence rule engine that turns human-readable schedules into precise, deterministic
next-occurrence datetimes. It ships with:

- An English parser that converts supported rules into an Intermediate Representation (IR).
- A French normalization layer that converts FR rules into the supported English grammar before parsing.
- An automatic language detector that routes English/French rules to the right parser.
- A scheduling engine that computes the next valid occurrence, including time zones, exceptions, and
  date windows.

The project focuses on pragmatic, well-scoped grammar coverage rather than trying to be a full natural
language system. The rule sets below document exactly what is accepted today and how it maps to the IR.

## Features

- Parse English recurrence rules into an intermediate representation (IR).
- Parse French rules by normalizing them into English grammar.
- Automatically detect English vs. French rules in the public API.
- Compute the next occurrence with time zone handling, exceptions, and date/time windows.
- Validate rules by checking that an occurrence exists within a reasonable horizon.

## Project Structure

```
recpyx/
  __init__.py      # Public API exports
  engine.py        # Scheduling engine
  en.py            # English parser (EN -> IR)
  fr.py            # French normalization (FR -> EN -> IR)
  parser.py        # Language detection + routing to EN/FR parser
tests/
  test_engine.py   # Regression coverage for rule parsing + engine
```

## Installation

This project depends on `python-dateutil` for the recurrence engine.

### Create a virtual environment (venv)

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows (PowerShell):

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
```

```bash
pip install -r requirements.txt
```

## Usage

### English rules (automatic detection)

```python
from recpyx import next_occurrence, validate

rule = "every weekday at 09:00"
validate(rule)
print(next_occurrence(rule))
```

### French rules (automatic detection)

```python
from recpyx import next_occurrence, validate

rule = "tous les jours ouvrés à 09h00"
validate(rule)
print(next_occurrence(rule))
```

### Exceptions and windows

```python
from recpyx import next_occurrence

rule = "every day at 10:00 except 2026-03-13"
print(next_occurrence(rule))
```

### Explicit parser usage (optional)

If you prefer to bypass auto-detection, you can call the language-specific parsers directly.

```python
from recpyx import parse_schedule_en, parse_schedule_fr

print(parse_schedule_en("every weekday at 09:00"))
print(parse_schedule_fr("tous les jours ouvrés à 09h00"))
```

## Intermediate Representation (IR) Specification (v1)

The parser outputs an `IRSchedule` that contains one or more `IRRule` objects. The IR is a structured,
deterministic description that the engine understands.

### IRSchedule

- **tz**: IANA time zone name, e.g. `Europe/Paris` or `America/New_York`.
- **rules**: List of `IRRule` objects.
- **version**: IR schema version (currently `"1"`).

### IRRule (core fields)

| Field | Type | Meaning |
| --- | --- | --- |
| `type` | `"rrule"` or `"oneshot"` | Recurrence rule vs. a single datetime. |
| `at` | `datetime` | For `oneshot` only. Naive local datetime; engine localizes with schedule time zone. |
| `freq` | `minutely`/`hourly`/`daily`/`weekly`/`monthly`/`yearly` | RRule frequency. |
| `interval` | `int` | RRule interval (default 1). |
| `bymonth` | `List[int]` | Month numbers 1-12 (yearly only). |
| `byweekday` | `List[int]` | Weekday indices 0=Mon ... 6=Sun. |
| `bymonthday` | `List[int]` | Day numbers 1-31 or `-1` for last day of month. |
| `bysetpos` | `List[int]` | Nth weekday positions (1..5 or `-1` for last). |
| `times` | `List[time]` | Specific times within a day for the rule. |
| `between_time` | `IRBetweenTime` | Time window within a day (used by step-within-day or hourly rules). |
| `step` | `IRStep` | Step size for repeating within a day (`hours` or `minutes`). |
| `window_date` | `IRWindowDate` | Date window constraints (start/end/until). |
| `except_` | `IRExcept` | Exclusion rules (weekdays, dates, holidays). |
| `weekend_shift` | `none`/`next_monday`/`next_business_day` | Shift occurrences that fall on weekends. |

### Supporting IR structures

**IRBetweenTime**
- `start`: start time (inclusive)
- `end`: end time (inclusive)

**IRStep**
- `hours`: integer step in hours (exclusive with `minutes`)
- `minutes`: integer step in minutes (exclusive with `hours`)

**IRWindowDate**
- `start`: date boundary (inclusive, start of day)
- `end`: date boundary (inclusive, end of day)
- `until`: upper bound (inclusive, end of day). If both `end` and `until` are present, the earliest wins.

**IRExcept**
- `weekdays`: list of weekday indices to exclude.
- `dates`: list of specific dates to exclude.
- `holidays`: `IRHolidaySpec` (accepted in syntax, not yet implemented by engine).

**IRHolidaySpec**
- `enabled`: boolean
- `country`: ISO-like country code, e.g. `"FR"` (reserved for future use)

### IR semantics

- All times are interpreted in the schedule time zone (`IRSchedule.tz`).
- `weekend_shift` is applied **after** rule expansion and **before** exclusions.
- `between_time` is inclusive on both ends. For hourly rules, it acts as a filter. For step-within-day rules
  it defines the window for repeating times.
- `except_` excludes specific weekdays, dates, and (eventually) holidays.
- `oneshot` rules still honor `window_date`, `weekend_shift`, and `except_` during validation/selection.

### Example IR (JSON-ish)

```json
{
  "tz": "Europe/Paris",
  "version": "1",
  "rules": [
    {
      "type": "rrule",
      "freq": "weekly",
      "interval": 1,
      "byweekday": [0, 3],
      "times": ["09:00"],
      "except_": {"weekdays": [], "dates": ["2026-05-01"], "holidays": {"enabled": false}},
      "weekend_shift": "none"
    }
  ]
}
```

## Grammaire BNF complète des expressions acceptées par `next_occurrence`

> `next_occurrence()` accepte une expression en **anglais** (grammaire native) ou en **français** (normalisée vers l'anglais avant parsing).
> La grammaire ci-dessous décrit donc la forme canonique réellement reconnue par le parseur.

### 1) Lexique

```bnf
<digit>         ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
<yyyy>          ::= <digit><digit><digit><digit>
<mm>            ::= <digit><digit>
<dd>            ::= <digit><digit>
<hh>            ::= <digit> | <digit><digit>
<min2>          ::= <digit><digit>
<date>          ::= <yyyy> "-" <mm> "-" <dd>
<month-day>     ::= <mm> "-" <dd>
<time24>        ::= <hh> ":" <min2>
<time12>        ::= <hh> [":" <min2>] ("am" | "pm")
<time>          ::= <time24> | <time12>
<timezone>      ::= <tz-token> "/" <tz-token>
<tz-token>      ::= letter { letter | "_" }
<int>           ::= <digit> { <digit> }

<weekday>       ::= "monday" | "tuesday" | "wednesday" | "thursday" | "friday" | "saturday" | "sunday"
<weekday-list>  ::= <weekday> { ("and" | ",") <weekday> }
<month-name>    ::= "january" | "february" | "march" | "april" | "may" | "june" |
                    "july" | "august" | "september" | "october" | "november" | "december"
<ordinal>       ::= "first" | "second" | "third" | "fourth" | "fifth" | "last"
<monthday>      ::= ("1".."31") ["st" | "nd" | "rd" | "th"]
<monthday-list> ::= <monthday> { ("and" | ",") <monthday> }
<time-list>     ::= <time> { ("and" | ",") <time> }
```

### 2) Grammaire de haut niveau

```bnf
<schedule>              ::= <rule-list> [<tz-suffix>]
<rule-list>             ::= <rule> { ", and" <rule> }
<tz-suffix>             ::= " in " <timezone>

<rule>                  ::= <base-rule> { <suffix-clause> }
<suffix-clause>         ::= <date-window> | <until-window> | <except-clause> | <weekend-shift>
```

### 3) Règles de base

```bnf
<base-rule> ::= <oneshot>
              | <every-day>
              | <every-weekday>
              | <every-weekday-list>
              | <every-n-units>
              | <hourly-between>
              | <step-within-day>
              | <monthly-rule>
              | <yearly-date>
              | <yearly-nth-weekday>

<oneshot>              ::= <date> " at " <time>
<every-day>            ::= "every day at " <time-list>
<every-weekday>        ::= "every weekday at " <time-list>
<every-weekday-list>   ::= "every " <weekday-list> " at " <time-list>

<every-n-units>        ::= "every " <int> " " <unit> [" on " <weekday-list>] [" at " <time-list>]
<unit>                 ::= "minutes" | "hours" | "days" | "weeks"

<hourly-between>       ::= "every hour between " <time> " and " <time>
                         | "every " <int> " hours between " <time> " and " <time>

<step-within-day>      ::= "every " <day-scope> " every " <int> " " <step-unit>
                           " between " <time> " and " <time>
<day-scope>            ::= "day" | "weekday"
<step-unit>            ::= "hours" | "minutes"

<monthly-rule>         ::= "every month on the " <monthly-selector> " at " <time>
<monthly-selector>     ::= "last day"
                         | <monthday-list>
                         | <ordinal> " " <weekday>

<yearly-date>          ::= "every year on " <month-day> " at " <time>
<yearly-nth-weekday>   ::= "every year on the " <ordinal> " " <weekday>
                           " of " <month-name> " at " <time>
```

### 4) Suffixes (ordre libre)

```bnf
<date-window>   ::= " between " <date> " and " <date>
<until-window>  ::= " until " <date>
<except-clause> ::= " except " <except-item-list>
<except-item-list> ::= <except-item> { ("," | " ") <except-item> }
<except-item>   ::= <weekday>
                  | <date>
                  | "public holidays"
                  | "on public holidays"
<weekend-shift> ::= " if weekend then next monday"
                  | " if weekend then next business day"
```

## Exemples exhaustifs par cas de la grammaire

### A. Cas `<schedule>` (règle simple, multi-règles, fuseau)

- `every day at 09:00`
- `every monday at 09:00, and every friday at 17:00`
- `every day at 09:00 in Europe/Paris`

### B. Cas `<oneshot>`

- `2026-03-13 at 10:00`
- `2026-03-13 at 2pm`

### C. Cas `<every-day>` et `<every-weekday>`

- `every day at 08:00`
- `every day at 08:00 and 18:30`
- `every weekday at 09:00`
- `every weekday at 09:00 and 17:00`

### D. Cas `<every-weekday-list>`

- `every monday at 09:00`
- `every monday and thursday at 09:00`
- `every monday, wednesday and friday at 09:00 and 18:00`

### E. Cas `<every-n-units>`

- `every 15 minutes`
- `every 2 hours`
- `every 3 days at 07:30`
- `every 2 weeks on monday`
- `every 2 weeks on monday and friday at 08:30 and 18:30`

### F. Cas `<hourly-between>`

- `every hour between 09:00 and 17:00`
- `every 2 hours between 08:00 and 18:00`

### G. Cas `<step-within-day>`

- `every day every 2 hours between 09:00 and 17:00`
- `every weekday every 30 minutes between 08:00 and 12:00`

### H. Cas `<monthly-rule>`

- `every month on the 1st at 09:00`
- `every month on the 1st and 15th at 09:00`
- `every month on the last day at 23:00`
- `every month on the first monday at 09:00`
- `every month on the last friday at 18:00`

### I. Cas `<yearly-date>` et `<yearly-nth-weekday>`

- `every year on 03-12 at 12:30`
- `every year on the last sunday of october at 23:00`
- `every year on the first monday of january at 09:00`

### J. Cas `<date-window>`

- `every day at 09:00 between 2026-01-01 and 2026-01-31`
- `every month on the 1st at 09:00 between 2026-01-01 and 2026-12-31`

### K. Cas `<until-window>`

- `every day at 09:00 until 2026-01-31`
- `every 2 weeks on monday at 08:30 until 2026-12-31`

### L. Cas `<except-clause>`

- `every day at 10:00 except monday`
- `every day at 10:00 except 2026-03-13`
- `every day at 10:00 except monday, 2026-03-13`
- `every day at 10:00 except public holidays`
- `every day at 10:00 except on public holidays`

### M. Cas `<weekend-shift>`

- `every month on the 1st at 09:00 if weekend then next monday`
- `every day at 09:00 if weekend then next business day`

### N. Combinaisons de suffixes (ordre libre)

- `every day at 09:00 except monday until 2026-06-30`
- `every day at 09:00 until 2026-06-30 except monday`
- `every month on the 1st at 09:00 between 2026-01-01 and 2026-12-31 if weekend then next monday`
- `every month on the 1st at 09:00 if weekend then next monday between 2026-01-01 and 2026-12-31`

## Équivalents français (normalisés automatiquement)

`next_occurrence` détecte la langue, puis convertit le français vers la grammaire anglaise ci-dessus.
Exemples de formes FR valides (1 exemple par famille) :

- One-shot : `le 2026-03-13 à 10h00`
- Quotidien : `tous les jours à 08h00 et 18h30`
- Jours ouvrés : `tous les jours ouvrés à 09h00`
- Jours nommés : `tous les lundis et jeudis à 09h00`
- N unités : `toutes les 2 semaines lundi à 08h30`
- Plage horaire : `toutes les heures entre 09h00 et 17h00`
- Pas intrajournalier : `tous les jours, toutes les 2 heures entre 09h00 et 17h00`
- Mensuel : `tous les mois le dernier jour à 23h00`
- Annuel : `tous les ans le dernier dimanche d'octobre à 23h00`
- Fenêtre dates : `tous les jours à 09h00 entre le 2026-01-01 et le 2026-01-31`
- Until : `tous les jours à 09h00 jusqu'au 2026-01-31`
- Exceptions : `tous les jours à 10h00 sauf lundi, 2026-03-13`
- Report week-end : `tous les mois le 1er à 09h00 si week-end alors lundi suivant`
- Fuseau : `tous les jours à 09h00 (Europe/Paris)`
- Multi-règles : `tous les lundis à 09h00, et tous les vendredis à 17h00`

## Notes & Limitations

- Time zones must be IANA names (e.g., `Europe/Paris`, `America/New_York`).
- Public holiday exclusions are accepted by the grammar but not implemented in the engine; a runtime error
  is raised if used.
- The parser is intentionally strict to keep the IR deterministic; use the exact forms described above.

## Testing

```bash
pytest
```
