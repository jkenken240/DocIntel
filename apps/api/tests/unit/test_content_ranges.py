import pytest

from docintel.services.content import (
    ByteRange,
    RangeNotSatisfiable,
    parse_byte_range,
)


@pytest.mark.parametrize(
    ("value", "size", "expected"),
    [
        (None, 100, None),
        ("bytes=0-4", 100, ByteRange(0, 4)),
        ("bytes=95-", 100, ByteRange(95, 99)),
        ("bytes=-5", 100, ByteRange(95, 99)),
        ("bytes=0-999", 100, ByteRange(0, 99)),
    ],
)
def test_supported_byte_ranges(
    value: str | None,
    size: int,
    expected: ByteRange | None,
) -> None:
    assert parse_byte_range(value, size) == expected


@pytest.mark.parametrize(
    "value",
    [
        "items=0-1",
        "bytes=100-101",
        "bytes=5-4",
        "bytes=-0",
        "bytes=0-1,4-5",
        "bytes=abc-def",
    ],
)
def test_invalid_byte_ranges_are_rejected(value: str) -> None:
    with pytest.raises(RangeNotSatisfiable):
        parse_byte_range(value, 100)
