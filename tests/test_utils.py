import pytest
from ..utils import parse_duration

class TestParseDuration:
    def test_seconds(self):
        assert parse_duration("30s") == 30
        assert parse_duration("1s") == 1

    def test_minutes(self):
        assert parse_duration("1m") == 60
        assert parse_duration("2m") == 120
        assert parse_duration("10m") == 600

    def test_hours(self):
        assert parse_duration("1h") == 3600
        assert parse_duration("3h") == 10800

    def test_days(self):
        assert parse_duration("1d") == 86400
        assert parse_duration("7d") == 604800

    def test_case_insensitive(self):
        assert parse_duration("1M") == 60
        assert parse_duration("2H") == 7200
        assert parse_duration("1D") == 86400

    def test_empty_duration_string(self):
        with pytest.raises(ValueError, match="Duration string cannot be empty"):
            parse_duration("")

    def test_whitespace_stripped(self):
        assert parse_duration(" 2m ") == 120

    def test_invalid_unit(self):
        with pytest.raises(ValueError, match="Unsupported duration unit 'x'"):
            parse_duration("10x")
        with pytest.raises(ValueError, match="Unsupported duration unit 'k'"):
            parse_duration("1k")

    def test_invalid_numeric(self):
        with pytest.raises(ValueError, match="Invalid duration value"):
            parse_duration("abcs")
        with pytest.raises(ValueError, match="Invalid duration value"):
            parse_duration("1.5m")

    def test_non_positive(self):
        with pytest.raises(ValueError, match="positive"):
            parse_duration("0s")
        with pytest.raises(ValueError, match="positive"):
            parse_duration("-1m")