from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import json
from datetime import datetime

from .models import TaskType, ResearchTask, FindingSeverity
from .config import NightshiftConfig


TOKEN_COST_ESTIMATES = {
    TaskType.FILE_STRUCTURE_ANALYSIS: 2000,
    TaskType.DEPENDENCY_AUDIT: 3000,
    TaskType.CODE_PATTERN_ANALYSIS: 8000,
    TaskType.TECH_DEBT_SCAN: 6000,
    TaskType.SECURITY_REVIEW: 10000,
    TaskType.ARCHITECTURE_REVIEW: 12000,
    TaskType.BEST_PRACTICES_CHECK: 5000,
    TaskType.PERFORMANCE_ANALYSIS: 7000,
    TaskType.DEPENDENCY_UPDATES: 4000,
    TaskType.SOTA_ALTERNATIVES: 6000,
    TaskType.INTEGRATION_OPPORTUNITIES: 5000,
}

TASK_IMPACT_SCORES = {
    TaskType.SECURITY_REVIEW: 100,
    TaskType.DEPENDENCY_AUDIT: 90,
    TaskType.ARCHITECTURE_REVIEW: 85,
    TaskType.TECH_DEBT_SCAN: 75,
    TaskType.CODE_PATTERN_ANALYSIS: 70,
    TaskType.PERFORMANCE_ANALYSIS: 65,
    TaskType.BEST_PRACTICES_CHECK: 60,
    TaskType.DEPENDENCY_UPDATES: 55,
    TaskType.SOTA_ALTERNATIVES: 50,
    TaskType.FILE_STRUCTURE_ANALYSIS: 40,
    TaskType.INTEGRATION_OPPORTUNITIES: 35,
}


@dataclass
class PriorityMode:
    name: str
    weights: dict[str, float]


PRIORITY_MODES = {
    "security_first": PriorityMode(
        name="Security First",
        weights={"security": 2.0, "dependencies": 1.5, "architecture": 1.0, "other": 0.5}
    ),
    "balanced": PriorityMode(
        name="Balanced",
        weights={"security": 1.2, "dependencies": 1.1, "architecture": 1.0, "other": 1.0}
    ),
    "research_heavy": PriorityMode(
        name="Research Heavy",
        weights={"security": 0.8, "dependencies": 1.0, "architecture": 1.0, "other": 1.5}
    ),
    "quick_scan": PriorityMode(
        name="Quick Scan",
        weights={"security": 1.5, "dependencies": 1.2, "architecture": 0.5, "other": 0.3}
    ),
}


def get_task_category(task_type: TaskType) -> str:
    if task_type == TaskType.SECURITY_REVIEW:
        return "security"
    elif task_type in (TaskType.DEPENDENCY_AUDIT, TaskType.DEPENDENCY_UPDATES):
        return "dependencies"
    elif task_type in (TaskType.ARCHITECTURE_REVIEW, TaskType.CODE_PATTERN_ANALYSIS):
        return "architecture"
    return "other"


@dataclass
class SmartPrioritizer:
    mode: str = "balanced"
    token_budget: Optional[int] = None
    
    def prioritize_tasks(self, tasks: list[ResearchTask]) -> list[ResearchTask]:
        priority_mode = PRIORITY_MODES.get(self.mode, PRIORITY_MODES["balanced"])
        
        scored_tasks = []
        for task in tasks:
            base_score = TASK_IMPACT_SCORES.get(task.task_type, 50)
            category = get_task_category(task.task_type)
            weight = priority_mode.weights.get(category, 1.0)
            final_score = base_score * weight
            scored_tasks.append((task, final_score))
        
        scored_tasks.sort(key=lambda x: x[1], reverse=True)
        
        if self.token_budget:
            selected = []
            remaining_budget = self.token_budget
            for task, score in scored_tasks:
                cost = TOKEN_COST_ESTIMATES.get(task.task_type, 5000)
                if remaining_budget >= cost:
                    selected.append(task)
                    remaining_budget -= cost
            return selected
        
        return [t for t, _ in scored_tasks]

    def estimate_total_tokens(self, tasks: list[ResearchTask]) -> int:
        return sum(TOKEN_COST_ESTIMATES.get(t.task_type, 5000) for t in tasks)

    def estimate_duration_hours(self, tasks: list[ResearchTask], tokens_per_minute: int = 5000) -> float:
        total_tokens = self.estimate_total_tokens(tasks)
        minutes = total_tokens / tokens_per_minute
        return minutes / 60


@dataclass 
class ModelPerformanceTracker:
    config: NightshiftConfig
    
    def __post_init__(self):
        self.metrics_file = self.config.data_dir / "model_metrics.json"

    def _load_metrics(self) -> dict:
        if self.metrics_file.exists():
            with open(self.metrics_file) as f:
                return json.load(f)
        return {"models": {}, "tasks": {}}

    def _save_metrics(self, metrics: dict):
        with open(self.metrics_file, "w") as f:
            json.dump(metrics, f, indent=2)

    def record_task_result(
        self,
        model_key: str,
        task_type: TaskType,
        tokens_used: int,
        findings_count: int,
        duration_seconds: float,
        success: bool
    ):
        metrics = self._load_metrics()
        
        if model_key not in metrics["models"]:
            metrics["models"][model_key] = {
                "total_tasks": 0,
                "successful_tasks": 0,
                "total_tokens": 0,
                "total_findings": 0,
                "total_duration": 0,
            }
        
        m = metrics["models"][model_key]
        m["total_tasks"] += 1
        if success:
            m["successful_tasks"] += 1
        m["total_tokens"] += tokens_used
        m["total_findings"] += findings_count
        m["total_duration"] += duration_seconds
        
        task_key = f"{model_key}|{task_type.value}"
        if task_key not in metrics["tasks"]:
            metrics["tasks"][task_key] = {
                "count": 0,
                "avg_findings": 0,
                "avg_tokens": 0,
                "avg_duration": 0,
            }
        
        t = metrics["tasks"][task_key]
        old_count = t["count"]
        t["count"] += 1
        t["avg_findings"] = (t["avg_findings"] * old_count + findings_count) / t["count"]
        t["avg_tokens"] = (t["avg_tokens"] * old_count + tokens_used) / t["count"]
        t["avg_duration"] = (t["avg_duration"] * old_count + duration_seconds) / t["count"]
        
        self._save_metrics(metrics)

    def get_best_model_for_task(self, task_type: TaskType) -> Optional[str]:
        metrics = self._load_metrics()
        
        candidates = []
        for task_key, data in metrics["tasks"].items():
            if task_type.value in task_key:
                model_key = task_key.split("|")[0]
                if data["count"] >= 3:
                    score = data["avg_findings"] / max(data["avg_tokens"], 1) * 1000
                    candidates.append((model_key, score))
        
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]
        
        return None

    def get_model_report(self) -> dict:
        metrics = self._load_metrics()
        
        report = {}
        for model_key, data in metrics["models"].items():
            if data["total_tasks"] > 0:
                report[model_key] = {
                    "tasks_completed": data["total_tasks"],
                    "success_rate": data["successful_tasks"] / data["total_tasks"] * 100,
                    "avg_findings_per_task": data["total_findings"] / data["total_tasks"],
                    "avg_tokens_per_task": data["total_tokens"] / data["total_tasks"],
                    "efficiency": data["total_findings"] / max(data["total_tokens"], 1) * 1000,
                }
        
        return report
