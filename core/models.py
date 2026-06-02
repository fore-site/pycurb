from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal, Dict, Any

class LimitRule(BaseModel):
    name: str = Field(..., min_length=1)
    key_type: Literal["ip", "api_key", "user_id", "custom"] = "ip"
    algorithm: Literal["sliding_window", "fixed_window", "token_bucket", "leaky_bucket"]
    limit: int = Field(..., gt=0)
    window: int = Field(..., gt=0)
    capacity: Optional[int] = None
    refill_rate: Optional[float] = None
    leak_rate: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_algorithm_params(self):
        if self.algorithm in ("sliding_window", "fixed_window"):
            # window and limit must be present; no extra checks
            pass
        elif self.algorithm == "token_bucket":
            cap = self.capacity if self.capacity is not None else self.limit
            rate = self.refill_rate
            if rate is None:
                # assume refill_rate = capacity / window
                rate = cap / self.window
            if rate <= 0:
                raise ValueError("refill_rate must be positive")
        elif self.algorithm == "leaky_bucket":
            if self.leak_rate is None or self.leak_rate <= 0:
                raise ValueError("leak_rate must be positive for leaky bucket")
        return self