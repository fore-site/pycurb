from django.http import HttpRequest


def ip_extractor(request: HttpRequest) -> str:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def user_id_extractor(request: HttpRequest) -> str:
    """Extract authenticated user ID (or 'anon')."""
    if hasattr(request, "user") and request.user.is_authenticated:
        return str(request.user.pk)
    return "anon"


def api_key_extractor(request: HttpRequest, header: str = "X-API-Key") -> str:
    """Extract API key from a custom header."""
    return request.headers.get(header, "")
