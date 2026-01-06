"""
Data models for Nightshift.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from pathlib import Path


class TaskStatus(Enum):
    """Status of a research task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskType(Enum):
    """Types of research tasks."""
    # Codebase Audit
    FILE_STRUCTURE_ANALYSIS = "file_structure_analysis"
    DEPENDENCY_AUDIT = "dependency_audit"
    CODE_PATTERN_ANALYSIS = "code_pattern_analysis"
    TECH_DEBT_SCAN = "tech_debt_scan"
    SECURITY_REVIEW = "security_review"
    
    # Enhancement Recommendations
    ARCHITECTURE_REVIEW = "architecture_review"
    BEST_PRACTICES_CHECK = "best_practices_check"
    PERFORMANCE_ANALYSIS = "performance_analysis"
    
    # Tool Stack Research
    DEPENDENCY_UPDATES = "dependency_updates"
    SOTA_ALTERNATIVES = "sota_alternatives"
    INTEGRATION_OPPORTUNITIES = "integration_opportunities"


class FindingSeverity(Enum):
    """Severity level for findings."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Finding:
    """A single finding from research."""
    id: str
    severity: FindingSeverity
    title: str
    description: str
    location: Optional[str] = None  # File path or component
    recommendation: Optional[str] = None
    references: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchTask:
    """A single research task to be executed."""
    id: str
    task_type: TaskType
    project_name: str
    project_path: Path
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    
    # Execution metadata
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    model_used: Optional[str] = None
    tokens_used: int = 0
    
    # Results
    findings: list[Finding] = field(default_factory=list)
    raw_output: Optional[str] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if isinstance(self.project_path, str):
            self.project_path = Path(self.project_path)
        if isinstance(self.task_type, str):
            self.task_type = TaskType(self.task_type)
        if isinstance(self.status, str):
            self.status = TaskStatus(self.status)


@dataclass
class ProjectReport:
    """Report for a single project."""
    name: str
    path: Path
    findings: list[Finding] = field(default_factory=list)
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_tokens: int = 0
    
    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.CRITICAL)
    
    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.HIGH)
    
    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.MEDIUM)


@dataclass
class NightshiftReport:
    """Complete nightshift run report."""
    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    # Project reports
    projects: list[ProjectReport] = field(default_factory=list)
    
    # Run statistics
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_tokens: int = 0
    models_used: list[str] = field(default_factory=list)
    
    # Tool stack research (cross-project)
    tool_research_findings: list[Finding] = field(default_factory=list)
    
    @property
    def duration_minutes(self) -> float:
        if self.completed_at:
            delta = self.completed_at - self.started_at
            return delta.total_seconds() / 60
        return 0
    
    @property
    def all_findings(self) -> list[Finding]:
        """All findings across all projects."""
        findings = []
        for project in self.projects:
            findings.extend(project.findings)
        findings.extend(self.tool_research_findings)
        return findings
