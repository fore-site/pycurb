from fastapi import Request


def ip_extractor(request: Request) -> str:
    """Extract client IP address, respecting X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def api_key_extractor(request: Request, header_name: str = "X-API-Key") -> str:
    """Extract API key from a header."""
    return request.headers.get(header_name, "")


def user_id_extractor(request: Request) -> str:
    """Extract user ID from request state (set by auth middleware)."""
    return getattr(request.state, "user_id", "anon")


def custom_extractor(extractor_func):
    """Decorator to register custom extractors (optional)."""
    return extractor_func
