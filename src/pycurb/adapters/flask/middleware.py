from flask import make_response, jsonify, request
from typing import Optional, Union, List, Callable
from pycurb.core import RateLimiter
from pycurb.core.models import RateLimitHeaders
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
            app, 
            limiter: RateLimiter, 
            rule_name: Union[str, List[str]], 
            key_extractor: Callable[..., str]
            ):
        self.app = app
        self.limiter = limiter
        self.rule_name = rule_name
        self.key_extractor = key_extractor or ip_extractor
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.before_request(self.before_request)
        app.after_request(self.after_request)
        app.extensions['ratelimit'] = self

    def before_request(self):
        key = self.key_extractor()
        result = self.limiter.check(key, self.rule_name)
        if not result.allowed:
            headers = RateLimitHeaders.from_result(result)
            resp = make_response(jsonify({"detail": "Rate limit exceeded"}), 429)
            for name, value in headers.to_dict().items():
                resp.headers[name] = value
            return resp
        # Store result in request context for after_request
        request.environ['_rate_limit_result'] = result

    def after_request(self, response):
        result = request.environ.get('_rate_limit_result', None)
        if result:
            headers = RateLimitHeaders.from_result(result)
            for name, value in headers.to_dict().items():
                response.headers[name] = value
        return response