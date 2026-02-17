"""
Nightshift configuration management.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json
import os
import re

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


def get_data_dir() -> Path:
    data_dir = os.getenv("NIGHTSHIFT_DATA_DIR")
    if data_dir:
        return Path(data_dir).expanduser()
    return Path.home() / ".nightshift"


def get_config_path(config_path: Optional[Path] = None) -> Path:
    if config_path:
        return Path(config_path).expanduser()

    env_config_path = os.getenv("NIGHTSHIFT_CONFIG_FILE")
    if env_config_path:
        return Path(env_config_path).expanduser()

    return get_data_dir() / "config.toml"


@dataclass
class ProjectConfig:
    """Configuration for a project to analyze."""
    name: str
    path: Path
    
    def __post_init__(self):
        if isinstance(self.path, str):
            self.path = Path(self.path)


@dataclass
class ModelConfig:
    """Configuration for a model provider."""
    provider: str
    model_id: str
    priority: int = 0
    rate_limited_until: Optional[float] = None


def _default_models() -> list[ModelConfig]:
    return [
        ModelConfig("google", "antigravity-claude-opus-4-5-thinking-high", priority=1),
        ModelConfig("openai", "gpt-5.2", priority=2),
        ModelConfig("google", "antigravity-gemini-3-pro-high", priority=3),
        ModelConfig("google", "antigravity-gemini-3-flash", priority=4),
    ]


@dataclass
class NightshiftConfig:
    """Main configuration for a nightshift run."""
    
    # Projects to analyze
    projects: list[ProjectConfig] = field(default_factory=list)
    
    # Model failover chain (priority order)
    models: list[ModelConfig] = field(default_factory=_default_models)
    
    # Task configuration
    enable_codebase_audit: bool = True
    enable_enhancement_recommendations: bool = True
    enable_tool_stack_research: bool = True
    
    # Runtime configuration
    max_duration_hours: float = 8.0
    checkpoint_interval_minutes: int = 5
    quota_check_interval_minutes: int = 30
    priority_mode: str = "balanced"
    open_report_in_browser: bool = True
    
    # Paths
    data_dir: Path = field(default_factory=get_data_dir)
    reports_dir: Path = field(default_factory=lambda: get_data_dir() / "reports")
    
    def __post_init__(self):
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def db_path(self) -> Path:
        return self.data_dir / "nightshift.db"
    
    @property
    def state_path(self) -> Path:
        return self.data_dir / "state.json"
    
    def save_state(self, state: dict):
        """Save current run state for recovery."""
        with open(self.state_path, "w") as f:
            json.dump(state, f, indent=2, default=str)
    
    def load_state(self) -> Optional[dict]:
        """Load previous run state if exists."""
        if self.state_path.exists():
            with open(self.state_path) as f:
                return json.load(f)
        return None


def _project_path_from_env_or_default(env_var: str, default_path: Path) -> Path:
    value = os.getenv(env_var)
    if value:
        return Path(value).expanduser()
    return default_path


BUILTIN_PROJECT_ALIASES = {
    "opsorchestra": _project_path_from_env_or_default(
        "NIGHTSHIFT_PROJECT_OPSORCHESTRA",
        Path.home() / "Projects" / "opsorchestra",
    ),
    "ghost-sentry": _project_path_from_env_or_default(
        "NIGHTSHIFT_PROJECT_GHOST_SENTRY",
        Path.home() / "Projects" / "anor" / "ghost-sentry",
    ),
}


def _slug_to_env_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def _safe_float(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_priority_mode(value, fallback: str) -> str:
    if isinstance(value, str) and value in {
        "balanced",
        "security_first",
        "research_heavy",
        "quick_scan",
    }:
        return value
    return fallback


def load_user_config(config_path: Optional[Path] = None) -> dict:
    path = get_config_path(config_path)
    if not path.exists():
        return {}
    if tomllib is None:
        return {}

    try:
        loaded = tomllib.loads(path.read_text())
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def get_config_defaults(user_config: Optional[dict] = None) -> dict:
    cfg = user_config or {}
    defaults = cfg.get("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}

    return {
        "duration_hours": _safe_float(defaults.get("duration_hours"), 8.0),
        "priority_mode": _safe_priority_mode(defaults.get("priority_mode"), "balanced"),
        "open_report_in_browser": bool(defaults.get("open_report_in_browser", True)),
    }


def get_default_project_aliases(
    config_path: Optional[Path] = None,
    user_config: Optional[dict] = None,
) -> dict[str, Path]:
    aliases = dict(BUILTIN_PROJECT_ALIASES)
    cfg = user_config if user_config is not None else load_user_config(config_path)

    configured_projects = cfg.get("projects", {})
    if isinstance(configured_projects, dict):
        for alias, path in configured_projects.items():
            if isinstance(alias, str) and isinstance(path, str) and path.strip():
                aliases[alias.strip()] = Path(path).expanduser()

    for alias in list(aliases.keys()):
        override_env = f"NIGHTSHIFT_PROJECT_{_slug_to_env_key(alias)}"
        override_path = os.getenv(override_env)
        if override_path:
            aliases[alias] = Path(override_path).expanduser()

    return aliases


DEFAULT_PROJECTS = get_default_project_aliases()


def get_preferred_models(
    config_path: Optional[Path] = None,
    user_config: Optional[dict] = None,
) -> list[ModelConfig]:
    cfg = user_config if user_config is not None else load_user_config(config_path)
    models_section = cfg.get("models", {})
    if not isinstance(models_section, dict):
        return _default_models()

    preferred = models_section.get("preferred", [])
    if not isinstance(preferred, list):
        return _default_models()

    model_configs: list[ModelConfig] = []
    for idx, identifier in enumerate(preferred, start=1):
        if not isinstance(identifier, str) or "/" not in identifier:
            continue
        provider, model_id = identifier.split("/", 1)
        provider = provider.strip()
        model_id = model_id.strip()
        if not provider or not model_id:
            continue
        model_configs.append(ModelConfig(provider, model_id, priority=idx))

    return model_configs or _default_models()


def _sanitize_alias(value: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
    return sanitized or "project"


def render_default_config_toml(current_project: Optional[Path] = None) -> str:
    project_line = '# example = "/path/to/your/project"'
    if current_project:
        alias = _sanitize_alias(current_project.name)
        project_line = f'{alias} = "{current_project.resolve()}"'

    return f"""# Nightshift user configuration
# Save as: {get_config_path()}

[defaults]
duration_hours = 8.0
priority_mode = "balanced"
open_report_in_browser = true

[projects]
{project_line}

[models]
# Optional model preference order. If omitted, Nightshift auto-discovers
# available models and falls back to built-in defaults.
# preferred = ["openai/gpt-5.2", "google/antigravity-gemini-3-pro-high"]
"""


def get_config(
    project_names: list[str],
    duration_hours: Optional[float] = None,
    priority_mode: Optional[str] = None,
    open_report_in_browser: Optional[bool] = None,
    config_path: Optional[Path] = None,
) -> NightshiftConfig:
    """Create a NightshiftConfig from project names."""
    user_config = load_user_config(config_path)
    defaults = get_config_defaults(user_config)
    aliases = get_default_project_aliases(config_path, user_config)
    preferred_models = get_preferred_models(config_path, user_config)

    resolved_duration = duration_hours if duration_hours is not None else defaults["duration_hours"]
    resolved_priority_mode = (
        _safe_priority_mode(priority_mode, defaults["priority_mode"])
        if priority_mode is not None
        else defaults["priority_mode"]
    )
    resolved_open_browser = (
        open_report_in_browser
        if open_report_in_browser is not None
        else defaults["open_report_in_browser"]
    )

    projects = []
    for name in project_names:
        if name in aliases:
            projects.append(ProjectConfig(name=name, path=aliases[name]))
        else:
            # Assume it's a path
            path = Path(name).expanduser().resolve()
            if path.exists():
                projects.append(ProjectConfig(name=path.name, path=path))
            else:
                raise ValueError(f"Project not found: {name}")
    
    return NightshiftConfig(
        projects=projects,
        models=preferred_models,
        max_duration_hours=resolved_duration,
        priority_mode=resolved_priority_mode,
        open_report_in_browser=resolved_open_browser,
    )
