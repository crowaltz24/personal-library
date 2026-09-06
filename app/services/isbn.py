import re


class InvalidISBNError(ValueError):
    pass


def normalize_isbn(value: str) -> str:
    normalized = re.sub(r"[\s-]", "", value).upper()
    if not normalized or any(character not in "0123456789X" for character in normalized):
        raise InvalidISBNError("ISBN contains invalid characters")
    if len(normalized) not in (10, 13):
        raise InvalidISBNError("ISBN must contain 10 or 13 characters")
    if len(normalized) == 10 and not normalized[:-1].isdigit():
        raise InvalidISBNError("ISBN-10 must contain digits followed by an optional X")
    if len(normalized) == 13 and not normalized.isdigit():
        raise InvalidISBNError("ISBN-13 must contain only digits")
    if not is_valid_isbn(normalized):
        raise InvalidISBNError("ISBN has an invalid check digit")
    return normalized


def is_valid_isbn(value: str) -> bool:
    try:
        if len(value) == 10:
            total = sum((10 - index) * (10 if digit == "X" else int(digit)) for index, digit in enumerate(value))
            return total % 11 == 0
        if len(value) == 13:
            total = sum((1 if index % 2 == 0 else 3) * int(digit) for index, digit in enumerate(value))
            return total % 10 == 0
    except (TypeError, ValueError):
        pass
    return False


def isbn10_to_isbn13(isbn10: str) -> str:
    normalized = normalize_isbn(isbn10)
    if len(normalized) != 10:
        raise InvalidISBNError("Only ISBN-10 values can be converted")
    body = "978" + normalized[:-1]
    check_digit = (10 - sum((1 if index % 2 == 0 else 3) * int(digit) for index, digit in enumerate(body)) % 10) % 10
    return body + str(check_digit)


def isbn_from_barcode(value: str) -> str | None:
    try:
        normalized = normalize_isbn(value)
    except InvalidISBNError:
        return None
    if len(normalized) == 13 and not normalized.startswith(("978", "979")):
        return None
    return normalized