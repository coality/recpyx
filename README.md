# recpyx

recpyx is a pragmatic recurrence rule engine that turns human-readable schedules into precise, deterministic
next-occurrence datetimes. It ships with:

- An English parser that converts supported rules into an Intermediate Representation (IR).
- A French normalization layer that converts FR rules into the supported English grammar before parsing.
- A scheduling engine that computes the next valid occurrence, including time zones, exceptions, and
  date windows.

The project focuses on pragmatic, well-scoped grammar coverage rather than trying to be a full natural
language system. The rule sets below document exactly what is accepted today and how it maps to the IR.

## Features

- Parse English recurrence rules into an intermediate representation (IR).
- Parse French rules by normalizing them into English grammar.
- Compute the next occurrence with time zone handling, exceptions, and date/time windows.
- Validate rules by checking that an occurrence exists within a reasonable horizon.

## Project Structure

```
recpyx/
  __init__.py      # Public API exports
  engine.py        # Scheduling engine
  en.py            # English parser (EN -> IR)
  fr.py            # French normalization (FR -> EN -> IR)
tests/
  test_engine.py   # Regression coverage for rule parsing + engine
```

## Installation

This project depends on `python-dateutil` for the recurrence engine.

```bash
pip install -r requirements.txt
```

## Usage

### English rules

```python
from recpyx import next_occurrence, validate

rule = "every weekday at 09:00"
validate(rule)
print(next_occurrence(rule))
```

### French rules

```python
from recpyx import parse_schedule_fr

schedule = parse_schedule_fr("tous les jours ouvrés à 09h00")
print(schedule)
```

### Exceptions and windows

```python
from recpyx import next_occurrence

rule = "every day at 10:00 except 2026-03-13"
print(next_occurrence(rule))
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

## English Rule Specification (Supported Grammar)

The following English rule shapes are accepted. They are *exact* patterns, so stick to the
wording shown here.

### Base schedules

1. **One-shot**
   - `YYYY-MM-DD at HH:MM`

2. **Every day / weekday**
   - `every day at HH:MM`
   - `every weekday at HH:MM`
   - Multiple times: `every day at 08:00 and 18:30`

3. **Specific weekdays**
   - `every monday and thursday at 09:00`
   - `every tuesday at 10:15`

4. **Every N units (minutes/hours/days/weeks)**
   - `every 2 hours`
   - `every 3 days at 07:30`
   - `every 2 weeks on monday at 08:30`
   - `every 15 minutes on monday and friday at 09:00` (time list optional)

5. **Hourly ranges**
   - `every hour between 09:00 and 17:00`
   - `every 2 hours between 08:00 and 18:00`

6. **Step within day (daily/weekday)**
   - `every day every 2 hours between 09:00 and 17:00`
   - `every weekday every 30 minutes between 08:00 and 12:00`

7. **Monthly rules**
   - `every month on the 1st at 09:00`
   - `every month on the 1st 15th at 09:00`
   - `every month on the last day at 23:00`
   - `every month on the first monday at 09:00`

8. **Yearly rules**
   - `every year on 03-12 at 12:30`
   - `every year on the last sunday of october at 23:00`

### Suffix clauses (may appear in any order)

- **Date window**
  - `between 2026-01-01 and 2026-03-31`
  - `until 2026-12-31`

- **Exceptions**
  - `except monday` (weekday exclusion)
  - `except 2026-03-13` (date exclusion)
  - `except public holidays` (syntax accepted, engine raises at runtime)
  - `except monday, 2026-03-13` (mixed list)

- **Weekend shifts**
  - `if weekend then next monday`
  - `if weekend then next business day`

### Multiple rules in one schedule

Separate rules with `", and"` (comma + “and”):

```
every monday at 09:00, and every friday at 17:00
```

The parser only splits on the literal `", and"` to avoid breaking weekday lists.

## French Rule Specification (Spécification complète - FR)

La grammaire française est normalisée en anglais avant parsing. Voici les formes acceptées en français.
Utilisez ces formes exactes pour un résultat garanti.

### Règles de base

1. **One-shot**
   - `le YYYY-MM-DD à HHhMM` ou `le YYYY-MM-DD à HH:MM`

2. **Chaque jour / jours ouvrés**
   - `tous les jours à 09h00`
   - `tous les jours ouvrés à 09h00`
   - Plusieurs horaires: `tous les jours à 08h00 et 18h30`

3. **Jours spécifiques**
   - `tous les lundis et jeudis à 09h00`
   - `tous les mardis à 10h15`

4. **Chaque N unités (minutes/heures/jours/semaines)**
   - `toutes les 2 heures`
   - `tous les 3 jours à 07h30`
   - `toutes les 2 semaines lundi à 08h30`
   - `toutes les 15 minutes lundi et vendredi à 09h00`

5. **Plages horaires (heures)**
   - `toutes les heures entre 09h00 et 17h00`
   - `toutes les 2 heures entre 08h00 et 18h00`

6. **Pas dans la journée (jour / jour ouvré)**
   - `tous les jours, toutes les 2 heures entre 09h00 et 17h00`
   - `tous les jours ouvrés, toutes les 30 minutes entre 08h00 et 12h00`

7. **Règles mensuelles**
   - `tous les mois le 1er à 09h00`
   - `tous les mois le 1er et 15 à 09h00`
   - `tous les mois le dernier jour à 23h00`
   - `tous les mois le premier lundi à 09h00`

8. **Règles annuelles**
   - `tous les ans le 03-12 à 12h30`
   - `tous les ans le dernier dimanche d'octobre à 23h00`

### Clauses suffixes (dans n'importe quel ordre)

- **Fenêtre de dates**
  - `entre le 2026-01-01 et le 2026-03-31`
  - `jusqu'au 2026-12-31`

- **Exceptions**
  - `sauf lundi` (exclusion d'un jour de semaine)
  - `sauf 2026-03-13` (exclusion d'une date)
  - `sauf jours fériés` (accepté, mais non implémenté par le moteur)
  - `sauf lundi, 2026-03-13` (liste mixte)

- **Report week-end**
  - `si week-end alors lundi suivant`
  - `si week-end alors prochain jour ouvré`

### Plusieurs règles dans une même phrase

Séparez les règles avec `", et"` (virgule + “et”) :

```
tous les lundis à 09h00, et tous les vendredis à 17h00
```

## French Rule Specification (Complete Rules in EN)

The French layer is implemented by transforming French phrases into the exact English grammar above. The
following points explain the full conversion behavior:

- Times: `10h`, `10h00`, `08h30` → `10:00`, `10:00`, `08:30`.
- Weekdays and month names are mapped into English equivalents.
- `tous les` / `toutes les` → `every`.
- `jour(s) ouvré(s)` → `weekday`.
- `sauf` → `except`.
- `entre le ... et le ...` → `between ... and ...` (date window).
- `entre HHhMM et HHhMM` → `between HH:MM and HH:MM` (time window).
- `jusqu'au YYYY-MM-DD` → `until YYYY-MM-DD`.
- `si week-end alors lundi suivant` → `if weekend then next monday`.
- `si week-end alors prochain jour ouvré` → `if weekend then next business day`.
- `tous les mois le ...` → `every month on the ...`.
- `tous les ans le ...` → `every year on ...`.
- `le YYYY-MM-DD à HHhMM` → `YYYY-MM-DD at HH:MM` (one-shot).
- `(... )` time zone suffix: `(Europe/Paris)` → `in Europe/Paris`.

## Examples with Explanations (EN)

Each example shows the accepted rule followed by a clear explanation of the behavior.

1. **`every weekday at 09:00`**
   - Occurs Monday–Friday at 09:00 in the schedule time zone.

2. **`every day at 08:00 and 18:30`**
   - Occurs twice per day, at 08:00 and 18:30.

3. **`every monday and thursday at 09:00`**
   - Occurs weekly on Mondays and Thursdays at 09:00.

4. **`every 2 weeks on monday at 08:30`**
   - Occurs every two weeks, only on Monday, at 08:30.

5. **`every 3 days at 07:30`**
   - Occurs every three days at 07:30.

6. **`every hour between 09:00 and 17:00`**
   - Occurs every hour, but only within the inclusive window 09:00–17:00.

7. **`every 2 hours between 08:00 and 18:00`**
   - Occurs every two hours between 08:00 and 18:00, inclusive.

8. **`every day every 2 hours between 09:00 and 17:00`**
   - For each day, produces a sequence 09:00, 11:00, 13:00, 15:00, 17:00.

9. **`every weekday every 30 minutes between 08:00 and 12:00`**
   - On weekdays, produces 08:00, 08:30, 09:00... up to 12:00.

10. **`every month on the last day at 23:00`**
    - Occurs on the last calendar day of each month at 23:00.

11. **`every month on the first monday at 09:00`**
    - Occurs on the first Monday of each month at 09:00.

12. **`every year on 03-12 at 12:30`**
    - Occurs every year on March 12th at 12:30.

13. **`every year on the last sunday of october at 23:00`**
    - Occurs on the last Sunday of October each year at 23:00.

14. **`2026-03-13 at 10:00`**
    - One-shot occurrence on 2026-03-13 at 10:00 only.

15. **`every day at 10:00 except 2026-03-13`**
    - Daily at 10:00, but skips the specific date 2026-03-13.

16. **`every weekday at 09:00 except monday`**
    - Weekdays at 09:00, but Monday is excluded, so Tuesday–Friday only.

17. **`every day at 09:00 between 2026-01-01 and 2026-01-31`**
    - Daily at 09:00, but only within January 2026.

18. **`every day at 09:00 until 2026-01-31`**
    - Daily at 09:00, but stops after 2026-01-31.

19. **`every month on the 1st at 09:00 if weekend then next monday`**
    - Monthly on the 1st at 09:00; if that day is a weekend, shift to next Monday.

20. **`every monday at 09:00, and every friday at 17:00`**
    - Two separate rules in one schedule: Mondays at 09:00 and Fridays at 17:00.

21. **`every day at 09:00 in America/New_York`**
    - Same daily schedule, explicitly tied to the America/New_York time zone.

## Exemples avec explications (FR)

Chaque exemple contient la règle acceptée puis une explication claire.

1. **`tous les jours ouvrés à 09h00`**
   - Se produit du lundi au vendredi à 09h00 (fuseau horaire de la règle).

2. **`tous les jours à 08h00 et 18h30`**
   - Deux occurrences par jour, à 08h00 et 18h30.

3. **`tous les lundis et jeudis à 09h00`**
   - Une occurrence hebdomadaire les lundis et jeudis à 09h00.

4. **`toutes les 2 semaines lundi à 08h30`**
   - Une occurrence toutes les deux semaines, le lundi, à 08h30.

5. **`tous les 3 jours à 07h30`**
   - Une occurrence tous les trois jours à 07h30.

6. **`toutes les heures entre 09h00 et 17h00`**
   - Une occurrence chaque heure, dans la plage 09h00–17h00 (incluse).

7. **`toutes les 2 heures entre 08h00 et 18h00`**
   - Une occurrence toutes les deux heures entre 08h00 et 18h00.

8. **`tous les jours, toutes les 2 heures entre 09h00 et 17h00`**
   - Chaque jour, occurrences à 09h00, 11h00, 13h00, 15h00, 17h00.

9. **`tous les jours ouvrés, toutes les 30 minutes entre 08h00 et 12h00`**
   - En semaine, occurrences toutes les 30 minutes entre 08h00 et 12h00.

10. **`tous les mois le dernier jour à 23h00`**
    - Occurrence le dernier jour de chaque mois à 23h00.

11. **`tous les mois le premier lundi à 09h00`**
    - Occurrence le premier lundi de chaque mois à 09h00.

12. **`tous les ans le 03-12 à 12h30`**
    - Occurrence chaque année le 12 mars à 12h30.

13. **`tous les ans le dernier dimanche d'octobre à 23h00`**
    - Occurrence le dernier dimanche d'octobre chaque année à 23h00.

14. **`le 2026-03-13 à 10h00`**
    - Une occurrence unique le 13/03/2026 à 10h00.

15. **`tous les jours à 10h00 sauf 2026-03-13`**
    - Tous les jours à 10h00, sauf le 13/03/2026.

16. **`tous les jours ouvrés à 09h00 sauf lundi`**
    - Tous les jours ouvrés à 09h00, mais le lundi est exclu (donc mardi à vendredi).

17. **`tous les jours à 09h00 entre le 2026-01-01 et le 2026-01-31`**
    - Tous les jours à 09h00, uniquement en janvier 2026.

18. **`tous les jours à 09h00 jusqu'au 2026-01-31`**
    - Tous les jours à 09h00, arrêt après le 31/01/2026.

19. **`tous les mois le 1er à 09h00 si week-end alors lundi suivant`**
    - Le 1er de chaque mois à 09h00 ; si week-end, report au lundi suivant.

20. **`tous les lundis à 09h00, et tous les vendredis à 17h00`**
    - Deux règles distinctes : lundi 09h00 et vendredi 17h00.

21. **`tous les jours à 09h00 (Europe/Paris)`**
    - Règle quotidienne à 09h00 avec fuseau explicite Europe/Paris.

## Notes & Limitations

- Time zones must be IANA names (e.g., `Europe/Paris`, `America/New_York`).
- Public holiday exclusions are accepted by the grammar but not implemented in the engine; a runtime error
  is raised if used.
- The parser is intentionally strict to keep the IR deterministic; use the exact forms described above.

## Testing

```bash
pytest
```
