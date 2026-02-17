from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import time
import subprocess

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


DEFAULT_MODEL_CHAIN = [
    ModelConfig("google", "antigravity-claude-opus-4-5-thinking-high", priority=1),
    ModelConfig("openai", "gpt-5.2", priority=2),
    ModelConfig("google", "antigravity-gemini-3-pro-high", priority=3),
    ModelConfig("google", "antigravity-gemini-3-flash", priority=4),
]

_MODEL_DISCOVERY_CACHE = {
    "timestamp": 0.0,
    "models": [],
}


def discover_available_model_ids(
    opencode_path: str = "opencode",
    ttl_seconds: int = 300,
    refresh: bool = False,
) -> list[str]:
    now = time.time()
    if not refresh and _MODEL_DISCOVERY_CACHE["models"] and (now - _MODEL_DISCOVERY_CACHE["timestamp"] < ttl_seconds):
        return list(_MODEL_DISCOVERY_CACHE["models"])

    try:
        result = subprocess.run(
            [opencode_path, "models"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return list(_MODEL_DISCOVERY_CACHE["models"])

    if result.returncode != 0:
        return list(_MODEL_DISCOVERY_CACHE["models"])

    models = [line.strip() for line in result.stdout.splitlines() if "/" in line]
    if models:
        _MODEL_DISCOVERY_CACHE["models"] = models
        _MODEL_DISCOVERY_CACHE["timestamp"] = now

    return list(_MODEL_DISCOVERY_CACHE["models"])


def _score_discovered_model(identifier: str) -> int:
    model_lower = identifier.lower()
    provider = identifier.split("/", 1)[0]

    score = {
        "openai": 35,
        "anthropic": 30,
        "google": 28,
        "opencode": 20,
    }.get(provider, 10)

    if any(token in model_lower for token in ("embedding", "image", "audio", "tts", "live")):
        score -= 50
    if "preview" in model_lower:
        score -= 10
    if any(token in model_lower for token in ("opus", "pro", "gpt-5", "claude-sonnet", "gemini-3-pro")):
        score += 20
    if any(token in model_lower for token in ("nano", "lite", "flash", "haiku", "free")):
        score -= 5

    return score


def _build_fallback_chain_from_available(available_model_ids: list[str], limit: int = 4) -> list[ModelConfig]:
    ranked = sorted(
        available_model_ids,
        key=lambda identifier: (_score_discovered_model(identifier), identifier),
        reverse=True,
    )

    selected: list[ModelConfig] = []
    for identifier in ranked:
        if "/" not in identifier:
            continue
        provider, model_id = identifier.split("/", 1)
        selected.append(ModelConfig(provider=provider, model_id=model_id, priority=len(selected) + 1))
        if len(selected) >= limit:
            break

    return selected


def _normalize_priorities(models: list[ModelConfig]) -> list[ModelConfig]:
    normalized: list[ModelConfig] = []
    for index, model in enumerate(models, start=1):
        normalized.append(ModelConfig(model.provider, model.model_id, priority=index))
    return normalized


def create_default_manager(
    preferred_models: Optional[list[ModelConfig]] = None,
    use_discovery: bool = True,
) -> ModelFailoverManager:
    preferred = preferred_models or DEFAULT_MODEL_CHAIN

    if not use_discovery:
        return ModelFailoverManager(models=_normalize_priorities(preferred))

    available = discover_available_model_ids()
    if not available:
        return ModelFailoverManager(models=_normalize_priorities(preferred))

    available_set = set(available)
    discovered_preferred: list[ModelConfig] = []
    for model in preferred:
        model_key = f"{model.provider}/{model.model_id}"
        if model_key in available_set:
            discovered_preferred.append(model)

    final_models = discovered_preferred or _build_fallback_chain_from_available(available)
    if not final_models:
        final_models = list(preferred)

    return ModelFailoverManager(
        models=_normalize_priorities(final_models)
    )
