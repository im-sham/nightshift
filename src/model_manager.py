from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import time
import httpx

from .config import ModelConfig


@dataclass 
class ModelFailoverManager:
    models: list[ModelConfig] = field(default_factory=list)
    quota_check_interval: int = 1800
    _last_quota_check: float = field(default=0, repr=False)
    _rate_limit_until: dict[str, float] = field(default_factory=dict, repr=False)

    def get_model_key(self, model: ModelConfig) -> str:
        return f"{model.provider}/{model.model_id}"

    def get_available_model(self) -> Optional[ModelConfig]:
        now = time.time()
        
        if now - self._last_quota_check > self.quota_check_interval:
            self._check_quota_refresh()
            self._last_quota_check = now
        
        sorted_models = sorted(self.models, key=lambda m: m.priority)
        
        for model in sorted_models:
            key = self.get_model_key(model)
            rate_limited_until = self._rate_limit_until.get(key, 0)
            if now > rate_limited_until:
                return model
        
        return None

    def mark_rate_limited(self, model: ModelConfig, retry_after_seconds: int = 3600):
        key = self.get_model_key(model)
        self._rate_limit_until[key] = time.time() + retry_after_seconds

    def mark_available(self, model: ModelConfig):
        key = self.get_model_key(model)
        if key in self._rate_limit_until:
            del self._rate_limit_until[key]

    def _check_quota_refresh(self):
        now = time.time()
        keys_to_remove = []
        for key, until_time in self._rate_limit_until.items():
            if now > until_time:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del self._rate_limit_until[key]

    def get_status(self) -> dict:
        now = time.time()
        status = {}
        for model in self.models:
            key = self.get_model_key(model)
            rate_limited_until = self._rate_limit_until.get(key, 0)
            if now > rate_limited_until:
                status[key] = {"available": True}
            else:
                remaining = int(rate_limited_until - now)
                status[key] = {
                    "available": False,
                    "retry_after_seconds": remaining,
                    "retry_at": datetime.fromtimestamp(rate_limited_until).isoformat()
                }
        return status

    def all_exhausted(self) -> bool:
        return self.get_available_model() is None


def create_default_manager() -> ModelFailoverManager:
    return ModelFailoverManager(
        models=[
            ModelConfig("google", "antigravity-claude-opus-4-5-thinking-high", priority=1),
            ModelConfig("openai", "gpt-5.2", priority=2),
            ModelConfig("google", "antigravity-gemini-3-pro-high", priority=3),
            ModelConfig("google", "antigravity-gemini-3-flash", priority=4),
        ]
    )
