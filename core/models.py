from pydantic import BaseModel, Field, model_validator, ConfigDict
from typing import Optional, Literal, Dict, Any
import time

class LimitRule(BaseModel):
    """
    Configuration for a rate limit rule.
    Users create an instance of this class to define how requests are limited.
    """
    model_config = ConfigDict(frozen=True)

    name: str = Field(..., min_length=1, description="Short unique identifier for the rule.")
    key_type: Literal["ip", "api_key", "user_id", "custom"] = Field(default="ip", description="Hint for adapters on how to extract client key.")
    algorithm: Literal["sliding_window", "fixed_window", "token_bucket", "leaky_bucket"] = Field(..., description="Rate limit algorithm to use.")
    
    # Window algorithms require limit and window; token bucket can use them if capacity and refill_rate are not provided.
    limit: Optional[int] = Field(default=None, gt=0, description="Maximum requests allowed (window-based) or capacity (token bucket).")
    window: Optional[int] = Field(default=None, gt=0, description="Time window in seconds (for window-based algorithms) or base to calculate refill rate.")
    
    # Optional parameters for token bucket and leaky bucket algorithms
    capacity: Optional[int] = Field(default=None, gt=0, description="Maximum capacity for token bucket (burst limit).")
    refill_rate: Optional[float] = Field(default=None, gt=0, description="Tokens added per second.")

    # Leaky bucket parameter
    leak_rate: Optional[float] = Field(default=None, gt=0, description="Requests processed per second.")

    # Metadata for extra conditional logic
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary user data for extra conditional logic.")

    @model_validator(mode="after")
    def validate_algorithm_parameters(self) -> "LimitRule":
        """
        Ensure algorithm-specific parameters are valid.
        """
        if self.algorithm in ("sliding_window", "fixed_window"):
            if self.limit is None or self.window is None:
                raise ValueError(f"'limit' and 'window' are required for {self.algorithm} algorithm.")
            
        elif self.algorithm == "token_bucket":
            has_cap = self.capacity is not None
            has_refill = self.refill_rate is not None
            has_limit = self.limit is not None
            has_window = self.window is not None

            # Must have capacity (or limit) for bucket size
            if not (has_cap or has_limit):
                raise ValueError("'capacity' or 'limit' is required for token_bucket algorithm.") 
            
            # Must have refill_rate (or window) to determine how tokens are added
            if not (has_refill or has_window):
                raise ValueError("'refill_rate' or 'window' is required for token_bucket algorithm.")
            
            cap = self.capacity if has_cap else self.limit
            if cap is None:
                raise ValueError("'capacity' or 'limit' is required for token_bucket algorithm.")
            
            if self.refill_rate is not None:
                rate = self.refill_rate
            else:
                if self.window is None:
                    raise ValueError("'window' is required for token_bucket algorithm when 'refill_rate' is not provided.")
                rate = cap / self.window

            if rate <= 0:
                raise ValueError(
                    f"'refill_rate' must be positive, got {rate}"
                )

        elif self.algorithm == "leaky_bucket":
            has_cap = self.capacity is not None
            has_limit = self.limit is not None
            if not (has_cap or has_limit):
                raise ValueError("'capacity' or 'limit' is required for leaky_bucket algorithm.")
            if self.leak_rate is None:
                raise ValueError("'leak_rate' is required for leaky_bucket algorithm.")
        return self
    

class RateLimitResult(BaseModel):
    """
    Outcome of a rate limit check.
    """
    model_config = ConfigDict(frozen=True)

    allowed: bool = Field(..., description="Request permitted or not")
    remaining: int = Field(..., ge=0, description="Remaining requests/tokens in current window/bucket.")
    reset_at: float = Field(..., description="Unix timestamp (seconds) when the limit resets.")
    limit: int = Field(..., gt=0, description="The configured limit (for X-RateLimit-Limit header).")
    retry_after: Optional[int] = Field(default=None, ge=0, description="Seconds to wait before retrying (only when allowed is False).")
    rule_name: Optional[str] = Field(default=None, description="Name of the rule that was applied.")


class RateLimitHeaders(BaseModel):
    """
    Helper to build standard HTTP ratelimit headers.
    """
    limit: int
    remaining: int
    reset: int
    retry_after: Optional[int] = None

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary of header names and values"""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset),
        }
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        return headers
    
    @classmethod
    def from_result(cls, result: RateLimitResult, now: Optional[float] = None) -> "RateLimitHeaders":
        """
        Construct headers from a rate limit result
        If retry_after is not set, compute as max(0, reset_at - now).
        """
        if now is None:
            now = time.time()
        retry_after = result.retry_after
        if retry_after is None and not result.allowed:
            retry_after = max(0, int(result.reset_at - now))

        return cls(
            limit=result.limit,
            remaining=result.remaining,
            reset=int(result.reset_at),
            retry_after=retry_after,
        )