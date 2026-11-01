import functools
from typing import Callable, List, Optional, ParamSpec, Union

from flask import Response, jsonify, make_response
from flask.typing import ResponseReturnValue

from pycurb.core import RateLimiter
from pycurb.core.models import RateLimitHeaders, RateLimitResult

from .extractors import ip_extractor

P = ParamSpec("P")


def rate_limit(
    limiter: RateLimiter,
    rule_name: Union[str, List[str]],
    key_extractor: Callable[[], str] = ip_extractor,
    on_limit: Optional[
        Callable[[RateLimitResult], Optional[ResponseReturnValue]]
    ] = None,
) -> Callable[[Callable[P, ResponseReturnValue]], Callable[P, Response]]:
    """
    Flask view decorator for rate limiting.
    Works with sync views.
    """

    def with_headers(
        response: ResponseReturnValue, result: RateLimitResult
    ) -> Response:
        response = make_response(response)
        for name, value in RateLimitHeaders.from_result(result).to_dict().items():
            response.headers[name] = value
        return response

    def decorator(
        f: Callable[P, ResponseReturnValue],
    ) -> Callable[P, Response]:
        @functools.wraps(f)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Response:
            key = key_extractor()
            result = limiter.check(key, rule_name)
            if result.storage_unavailable:
                return with_headers(
                    (jsonify({"detail": "Rate limiter unavailable"}), 503), result
                )

            if not result:
                if on_limit:
                    response = on_limit(result)
                    if response is not None:
                        return with_headers(response, result)
                return with_headers(
                    (jsonify({"detail": "Rate limit exceeded"}), 429), result
                )

            rv = f(*args, **kwargs)
            return with_headers(rv, result)

        return wrapper

    return decorator
