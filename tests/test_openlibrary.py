import pytest

from app.services.openlibrary import InvalidISBNError, normalize_isbn


@pytest.mark.parametrize(
    ("value", "expected"),
    [("978-0-306-40615-7", "9780306406157"), ("0 306 40615 2", "0306406152"), ("043942089X", "043942089X")],
)
def test_normalize_isbn(value, expected):
    assert normalize_isbn(value) == expected


def test_normalize_rejects_invalid_isbn():
    with pytest.raises(InvalidISBNError):
        normalize_isbn("12345")