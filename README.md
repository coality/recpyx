# recpyx

recpyx is a pragmatic recurrence rule engine that turns human-readable schedules into precise, deterministic
datetimes. It includes an English parser, a French-to-English normalization layer, and a scheduling engine that
computes the next occurrence of a rule. 

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

## Testing

```bash
pytest
```

## Notes

- Time zones use the IANA name, for example `Europe/Paris` or `America/New_York`.
- Public holiday exclusions are not implemented yet (the parser accepts the syntax, but the engine raises).
