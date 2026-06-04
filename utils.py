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
     