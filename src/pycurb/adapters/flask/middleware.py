from typing import Callable, List, Optional, Union, cast

from flask import Flask, Response, jsonify, make_response, request

from pycurb.core import RateLimiter
from pycurb.core.models import RateLimitHeaders, RateLimitResult

from .extractors import ip_extractor


class RateLimit:
    """
    Flask extension for global rate limiting.
    Usage:
        app = Flask(__name__)
        limiter = RateLimiterSync(...)
        RateLimit(app, limiter, rule_name="global")
    """

    def __init__(
        self,
        app: Optional[Flask],
        limiter: RateLimiter,
        rule_name: Union[str, List[str]],
        key_extractor: Optional[Callable[[], str]] = None,
    ) -> None:
        self.app: Optional[Flask] = app
        self.limiter = limiter
        self.rule_name = rule_name
        self.key_extractor = key_extractor or ip_extractor
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        app.before_request(self.before_request)
        app.after_request(self.after_request)
        app.extensions["ratelimit"] = self

    def before_request(self) -> Optional[Response]:
        key = self.key_extractor()
        if not (result := self.limiter.check(key, self.rule_name)):
            headers = RateLimitHeaders.from_result(result)
            status_code = 503 if result.storage_unavailable else 429
            detail = (
                "Rate limiter unavailable"
                if result.storage_unavailable
                else "Rate limit exceeded"
            )
            resp = make_response(jsonify({"detail": detail}), status_code)
            for name, value in headers.to_dict().items():
                resp.headers[name] = value
            return resp
        # Store result in request context for after_request
        request.environ["_rate_limit_result"] = result

    def after_request(self, response: Response) -> Response:
        result = cast(
            Optional[RateLimitResult],
            request.environ.get("_rate_limit_result"),
        )
        if result:
            headers = RateLimitHeaders.from_result(result)
            for name, value in headers.to_dict().items():
                response.headers[name] = value
        return response
