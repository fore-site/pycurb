import re
from typing import Tuple

def parse_duration(duration_str: str) -> int:
    """
    Convert a shorthand duration string into seconds.
    Duration must be an integer followed by a unit.
    Supported units:
        - s: seconds
        - m: minutes
        - h: hours
        - d: days

    Examples:
        parse_duration("30s") -> 30
        parse_duration("5m") -> 300
        parse_duration("2h") -> 7200
        parse_duration("1d") -> 86400

    Raises:
        ValueError: If the format is invalid or unit is unsupported.
    """
    duration_str = duration_str.strip().lower()
    if not duration_str:
        raise ValueError("Duration string cannot be empty.")
    
    unit = duration_str[-1]
    if unit not in ['s', 'm', 'h', 'd']:
        raise ValueError(f"Unsupported duration unit '{unit}'. Use 's', 'm', 'h', or 'd'.")

    try:
        value = int(duration_str[:-1])
    except ValueError:
        raise ValueError(f"Invalid duration value in '{duration_str}'. Must be an integer followed by a unit.")
    
    if value <= 0:
        raise ValueError("Duration value must be positive.")
    
    multipliers = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400
    }
    return value * multipliers[unit]


def parse_rate_limit_string(rate_str: str) -> Tuple[int, int]:
    """
    Parse a shorthand rate limit string into (limit, window_seconds).

    Supported formats (examples):

    - Single number (per-second): ``100`` -> limit=100, window=1
    - Per-unit shorthand: ``100/s`` -> limit=100, window=1
    - Explicit duration with unit: ``100/30s`` -> limit=100, window=30
    - Numeric window without unit: ``100/60`` -> limit=100, window=60
    - Larger units: ``5/m`` -> limit=5, window=60; ``10/h`` -> limit=10, window=3600

    Examples::

        ```
        100/s
        100/30s
        5/m
        5/2m
        10/h
        10/2h
        2/d
        2/2d
        100
        100/60
        ```

    Raises:
        ValueError: if format is invalid.
    """
    rate_str = rate_str.strip().lower()
    if not rate_str:
        raise ValueError("Empty rate limit string")

    match = re.match(r'^(\d+)(?:/(\d*)([smhd]?))?$', rate_str)
    if not match:
        raise ValueError(f"Invalid rate limit format: '{rate_str}'")

    limit = int(match.group(1))
    window_part = match.group(2)  # may be empty string or None
    unit = match.group(3)         # may be empty string or None

     # Detect trailing slash: window_part is empty string, no unit, and there is a slash
    if '/' in rate_str and window_part == "" and not unit:
        raise ValueError(f"Invalid rate limit format: '{rate_str}'")

    # Determine window value
    if window_part is not None and window_part != "":
        window = int(window_part)
    else:
        # No explicit window number: use 1 as base
        window = 1

    # Apply unit multiplier
    if unit:
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        if unit not in multipliers:
            raise ValueError(f"Unknown unit '{unit}'. Allowed: s, m, h, d")
        window *= multipliers[unit]

    if window <= 0:
        raise ValueError("Window must be positive")

    return limit, window