from datetime import date


class AgeRestrictionError(ValueError):
    pass


def parse_birth_date(raw_value: str) -> date:
    """Parse a birth date entered as DD.MM.YYYY (or similar) or ISO YYYY-MM-DD."""
    if not isinstance(raw_value, str):
        raise ValueError("Birth date must be provided as a string")

    normalized = raw_value.strip().replace(",", ".").replace("/", ".").replace("-", ".")
    parts = [part for part in normalized.split(".") if part]
    if len(parts) != 3:
        raise ValueError("Birth date format must be DD.MM.YYYY or YYYY-MM-DD")

    # Allow both DD.MM.YYYY and YYYY.MM.DD notations.
    if len(parts[0]) == 4:
        year, month, day = parts
    else:
        day, month, year = parts

    try:
        day_int = int(day)
        month_int = int(month)
        year_int = int(year)
    except ValueError as exc:
        raise ValueError("Birth date must contain numeric values") from exc

    return date(year_int, month_int, day_int)


def ensure_is_adult(birth_date: date, minimum_age: int = 18) -> None:
    today = date.today()
    age = today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )
    if age < minimum_age:
        raise AgeRestrictionError(
            f"User must be at least {minimum_age} years old. Current age: {age}"
        )
