"""
Nightshift configuration management.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json
import os


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


@dataclass
class NightshiftConfig:
    """Main configuration for a nightshift run."""
    
    # Projects to analyze
    projects: list[ProjectConfig] = field(default_factory=list)
    
    # Model failover chain (priority order)
    models: list[ModelConfig] = field(default_factory=lambda: [
        ModelConfig("google", "antigravity-claude-opus-4-5-thinking-high", priority=1),
        ModelConfig("openai", "gpt-5.2", priority=2),
        ModelConfig("google", "antigravity-gemini-3-pro-high", priority=3),
        ModelConfig("google", "antigravity-gemini-3-flash", priority=4),
    ])
    
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
    data_dir: Path = field(default_factory=lambda: Path.home() / ".nightshift")
    reports_dir: Path = field(default_factory=lambda: Path.home() / ".nightshift" / "reports")
    
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


# Default project paths (can be overridden via env vars)
DEFAULT_PROJECTS = {
    "opsorchestra": _project_path_from_env_or_default(
        "NIGHTSHIFT_PROJECT_OPSORCHESTRA",
        Path.home() / "Projects" / "opsorchestra",
    ),
    "ghost-sentry": _project_path_from_env_or_default(
        "NIGHTSHIFT_PROJECT_GHOST_SENTRY",
        Path.home() / "Projects" / "anor" / "ghost-sentry",
    ),
}


def get_config(
    project_names: list[str],
    duration_hours: float = 8.0,
    priority_mode: str = "balanced",
    open_report_in_browser: bool = True,
) -> NightshiftConfig:
    """Create a NightshiftConfig from project names."""
    
    projects = []
    for name in project_names:
        if name in DEFAULT_PROJECTS:
            projects.append(ProjectConfig(name=name, path=DEFAULT_PROJECTS[name]))
        else:
            # Assume it's a path
            path = Path(name).expanduser().resolve()
            if path.exists():
                projects.append(ProjectConfig(name=path.name, path=path))
            else:
                raise ValueError(f"Project not found: {name}")
    
    return NightshiftConfig(
        projects=projects,
        max_duration_hours=duration_hours,
        priority_mode=priority_mode,
        open_report_in_browser=open_report_in_browser,
    )
