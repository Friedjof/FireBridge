from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class CronExpression:
    expression: str
    minutes: set[int]
    hours: set[int]
    days: set[int]
    months: set[int]
    weekdays: set[int]
    day_is_wildcard: bool
    weekday_is_wildcard: bool

    def matches(self, value: datetime) -> bool:
        if value.minute not in self.minutes:
            return False
        if value.hour not in self.hours:
            return False
        if value.month not in self.months:
            return False

        day_matches = value.day in self.days
        cron_weekday = (value.weekday() + 1) % 7
        weekday_matches = cron_weekday in self.weekdays

        if not self.day_is_wildcard and not self.weekday_is_wildcard:
            return day_matches or weekday_matches
        return day_matches and weekday_matches

    def next_after(self, value: datetime) -> datetime:
        candidate = value.replace(second=0, microsecond=0) + timedelta(minutes=1)
        deadline = candidate + timedelta(days=366 * 5)
        while candidate <= deadline:
            if self.matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)
        raise ValueError(f"Could not find next run for cron expression: {self.expression}")


def parse_cron_expression(expression: str) -> CronExpression:
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("Cron expression must have exactly 5 fields")

    minute, hour, day, month, weekday = fields
    return CronExpression(
        expression=expression,
        minutes=_parse_field(minute, 0, 59),
        hours=_parse_field(hour, 0, 23),
        days=_parse_field(day, 1, 31),
        months=_parse_field(month, 1, 12),
        weekdays=_parse_weekday_field(weekday),
        day_is_wildcard=day == "*",
        weekday_is_wildcard=weekday == "*",
    )


def _parse_weekday_field(value: str) -> set[int]:
    values = _parse_field(value, 0, 7)
    normalized = {0 if item == 7 else item for item in values}
    return normalized


def _parse_field(value: str, minimum: int, maximum: int) -> set[int]:
    result: set[int] = set()
    for part in value.split(","):
        result.update(_parse_part(part.strip(), minimum, maximum))
    if not result:
        raise ValueError(f"Cron field is empty: {value}")
    return result


def _parse_part(value: str, minimum: int, maximum: int) -> set[int]:
    if not value:
        raise ValueError("Cron field contains an empty item")

    step = 1
    base = value
    if "/" in value:
        base, raw_step = value.split("/", 1)
        step = int(raw_step)
        if step <= 0:
            raise ValueError("Cron step must be greater than zero")

    if base == "*":
        start = minimum
        end = maximum
    elif "-" in base:
        raw_start, raw_end = base.split("-", 1)
        start = int(raw_start)
        end = int(raw_end)
    else:
        start = int(base)
        end = maximum if "/" in value else start

    if start < minimum or end > maximum or start > end:
        raise ValueError(f"Cron field value out of range: {value}")

    return set(range(start, end + 1, step))
