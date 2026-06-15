import pytest
from pycurb.utils import parse_duration, parse_rate_limit_string

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


class TestParseRateLimitString:
    """Test the parse_rate_limit_string function."""

    # Valid formats
    def test_simple_number_no_unit(self):
        """Just a number -> limit=number, window=1 (second)."""
        assert parse_rate_limit_string("100") == (100, 1)

    def test_slash_number_no_unit(self):
        """100/60 -> limit=100, window=60 (seconds)."""
        assert parse_rate_limit_string("100/60") == (100, 60)

    def test_per_second_unit_without_number(self):
        """100/s -> limit=100, window=1."""
        assert parse_rate_limit_string("100/s") == (100, 1)

    def test_per_second_unit_with_number(self):
        """100/20s -> limit=100, window=20."""
        assert parse_rate_limit_string("100/20s") == (100, 20)

    def test_per_minute_unit_without_number(self):
        """5/m -> limit=5, window=60."""
        assert parse_rate_limit_string("5/m") == (5, 60)

    def test_per_minute_unit_with_number(self):
        """5/3m -> limit=5, window=180."""
        assert parse_rate_limit_string("5/3m") == (5, 180)

    def test_per_hour_unit_without_number(self):
        """10/h -> limit=10, window=3600."""
        assert parse_rate_limit_string("10/h") == (10, 3600)

    def test_per_hour_unit_with_number(self):
        """10/2h -> limit=10, window=7200."""
        assert parse_rate_limit_string("10/2h") == (10, 7200)

    def test_per_day_unit_without_number(self):
        """2/d -> limit=2, window=86400."""
        assert parse_rate_limit_string("2/d") == (2, 86400)

    def test_per_day_unit_with_number(self):
        """2/2d -> limit=2, window=172800."""
        assert parse_rate_limit_string("2/2d") == (2, 172800)

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace should be ignored."""
        assert parse_rate_limit_string("  10/m  ") == (10, 60)

    def test_case_insensitive(self):
        """Units are case-insensitive."""
        assert parse_rate_limit_string("5/M") == (5, 60)
        assert parse_rate_limit_string("5/H") == (5, 3600)

    # Edge cases
    def test_zero_limit(self):
        """Limit = 0 is allowed (though rate limiter would reject due to gt=0 in model)."""
        assert parse_rate_limit_string("0/s") == (0, 1)

    def test_large_numbers(self):
        """Large integers are handled."""
        assert parse_rate_limit_string("1000000/3600s") == (1000000, 3600)

    def test_window_zero(self):
        """Window 0 is invalid (should raise)."""
        with pytest.raises(ValueError, match="Window must be positive"):
            parse_rate_limit_string("100/0")

    def test_window_zero_with_unit(self):
        with pytest.raises(ValueError, match="Window must be positive"):
            parse_rate_limit_string("100/0s")

    def test_negative_limit(self):
        """Negative limit not allowed in format (digits only)."""
        with pytest.raises(ValueError):
            parse_rate_limit_string("-5/m")

    # Invalid formats
    def test_empty_string(self):
        with pytest.raises(ValueError, match="Empty rate limit string"):
            parse_rate_limit_string("")

    def test_invalid_format_no_numbers(self):
        with pytest.raises(ValueError, match="Invalid rate limit format"):
            parse_rate_limit_string("abc")

    def test_invalid_format_mixed(self):
        with pytest.raises(ValueError, match="Invalid rate limit format"):
            parse_rate_limit_string("100/per_minute")

    def test_unknown_unit(self):
        with pytest.raises(ValueError, match="Invalid rate limit format"):
            parse_rate_limit_string("100/x")

    def test_trailing_slash(self):
        with pytest.raises(ValueError, match="Invalid rate limit format"):
            parse_rate_limit_string("100/")

    def test_leading_slash(self):
        with pytest.raises(ValueError, match="Invalid rate limit format"):
            parse_rate_limit_string("/100")

    def test_multiple_slashes(self):
        with pytest.raises(ValueError, match="Invalid rate limit format"):
            parse_rate_limit_string("100/60/s")

    def test_fractional_limit(self):
        """Only integers allowed, so '1.5/m' should raise."""
        with pytest.raises(ValueError):
            parse_rate_limit_string("1.5/m")

    def test_fractional_window(self):
        with pytest.raises(ValueError):
            parse_rate_limit_string("100/1.5m")