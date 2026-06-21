from flask import request, session


def ip_extractor():
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def flask_login_user_extractor():
    """Extract authenticated user ID (using flask_login)."""
    try:
        from flask_login import current_user

        if current_user.is_authenticated:
            return str(current_user.get_id())
    except (ImportError, AttributeError):
        pass
    return "anon"


def session_user_extractor():
    """Extract authenticated user ID directly from session."""
    return session.get("user_id", "anon")


def api_key_extractor(header="X-API-Key"):
    """Extract API key from a custom header."""
    return request.headers.get(header, "")

def custom_extractor(extractor_func):
    """Decorator to register custom extractors (optional)."""
    return extractor_func
