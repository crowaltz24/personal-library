import pytest

from app.services.isbn import InvalidISBNError, isbn10_to_isbn13, normalize_isbn


def test_valid_isbn13():
    assert normalize_isbn("978-0-306-40615-7") == "9780306406157"


def test_valid_isbn10():
    assert normalize_isbn("0 306 40615 2") == "0306406152"


def test_invalid_check_digit():
    with pytest.raises(InvalidISBNError):
        normalize_isbn("9780306406158")


def test_isbn10_to_isbn13():
    assert isbn10_to_isbn13("0-306-40615-2") == "9780306406157"