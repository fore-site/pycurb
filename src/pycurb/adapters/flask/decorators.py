import functools
from flask import make_response, jsonify
from typing import Union, Callable, List, Optional
from pycurb.core import RateLimiter
from pycurb.core.models import RateLimitHeaders
from .extractors import ip_extractor


def rate_limit(
    limiter: RateLimiter,
    rule_name: Union[str, List[str]],
    key_extractor: Callable[..., str] = ip_extractor,
    on_limit: Optional[Callable] = None,
):
    """
    Flask view decorator for rate limiting.
    Works with sync views.
    """

    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            key = key_extractor()
            result = limiter.check(key, rule_name)
            if not result.allowed:
                if on_limit:
                    response = on_limit(result)
                    if response is not None:
                        return response
                headers = RateLimitHeaders.from_result(result)
                resp = make_response(jsonify({"detail": "Rate limit exceeded"}), 429)
                for name, value in headers.to_dict().items():
                    resp.headers[name] = value
                return resp
            rv = f(*args, **kwargs)
            resp = make_response(rv)
            headers = RateLimitHeaders.from_result(result)
            for name, value in headers.to_dict().items():
                resp.headers[name] = value
            return resp

        return wrapper

    return decorator
