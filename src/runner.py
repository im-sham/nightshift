from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import asyncio
import time
import uuid
import json
import subprocess
from pathlib import Path

from .config import NightshiftConfig, ProjectConfig
from .models import (
    ResearchTask, TaskStatus, TaskType, Finding, FindingSeverity,
    NightshiftReport, ProjectReport
)
from .task_queue import TaskQueue
from .model_manager import ModelFailoverManager, create_default_manager
from .report_generator import ReportGenerator


TASK_PROMPTS = {
    TaskType.FILE_STRUCTURE_ANALYSIS: """Analyze the file structure of this project:
Project: {project_name}
Path: {project_path}

Examine:
1. Directory organization and naming conventions
2. Module structure and separation of concerns
3. Configuration file placement
4. Test file organization
5. Documentation structure

Return findings as JSON array with format:
[{{"severity": "high|medium|low|info", "title": "...", "description": "...", "location": "path/to/file", "recommendation": "..."}}]""",

    TaskType.DEPENDENCY_AUDIT: """Audit the dependencies of this project:
Project: {project_name}
Path: {project_path}

Check pyproject.toml, requirements.txt, package.json for:
1. Outdated dependencies (major version behind)
2. Known security vulnerabilities
3. Unused dependencies
4. Missing version pins
5. Dependency conflicts

Return findings as JSON array.""",

    TaskType.CODE_PATTERN_ANALYSIS: """Analyze code patterns in this project:
Project: {project_name}
Path: {project_path}

Look for:
1. Inconsistent coding styles
2. Anti-patterns (god classes, deep nesting, etc.)
3. Copy-paste code / DRY violations
4. Missing error handling
5. Hardcoded values that should be config

Return findings as JSON array.""",

    TaskType.TECH_DEBT_SCAN: """Scan for technical debt in this project:
Project: {project_name}
Path: {project_path}

Identify:
1. TODO/FIXME/HACK comments
2. Deprecated API usage
3. Complex functions that need refactoring
4. Missing tests for critical paths
5. Incomplete implementations

Return findings as JSON array.""",

    TaskType.SECURITY_REVIEW: """Perform a security review of this project:
Project: {project_name}
Path: {project_path}

Check for:
1. Hardcoded secrets or credentials
2. SQL injection vulnerabilities
3. Insecure authentication patterns
4. Missing input validation
5. Exposed sensitive endpoints

Return findings as JSON array with severity=critical for security issues.""",

    TaskType.ARCHITECTURE_REVIEW: """Review the architecture of this project:
Project: {project_name}
Path: {project_path}

Evaluate:
1. Layer separation (API, business logic, data access)
2. Dependency injection patterns
3. Configuration management
4. Error handling strategy
5. Scalability considerations

Return findings as JSON array.""",

    TaskType.BEST_PRACTICES_CHECK: """Check adherence to best practices:
Project: {project_name}
Path: {project_path}

Verify:
1. Type hints usage (Python) or TypeScript types
2. Logging practices
3. Environment variable handling
4. Database connection management
5. API design conventions

Return findings as JSON array.""",

    TaskType.PERFORMANCE_ANALYSIS: """Analyze potential performance issues:
Project: {project_name}
Path: {project_path}

Look for:
1. N+1 query patterns
2. Missing caching opportunities
3. Synchronous operations that could be async
4. Large data processing without pagination
5. Resource leaks

Return findings as JSON array.""",

    TaskType.DEPENDENCY_UPDATES: """Research dependency updates for this project:
Project: {project_name}
Path: {project_path}

For each major dependency:
1. Check current version vs latest stable
2. Review changelog for breaking changes
3. Assess migration effort
4. Identify security fixes in newer versions

Return findings as JSON array.""",

    TaskType.SOTA_ALTERNATIVES: """Research state-of-the-art alternatives:
Project: {project_name}
Path: {project_path}

For key libraries used, research:
1. Newer alternatives with better performance
2. More actively maintained options
3. Industry trends and adoption
4. Cost/benefit of switching

Return findings as JSON array.""",

    TaskType.INTEGRATION_OPPORTUNITIES: """Research integration opportunities:
Project: {project_name}
Path: {project_path}

Based on the project's purpose, research:
1. APIs that could enhance functionality
2. Services that could reduce custom code
3. Tools that improve developer experience
4. Monitoring/observability solutions

Return findings as JSON array.""",
}


@dataclass
class NightshiftRunner:
    config: NightshiftConfig
    task_queue: TaskQueue = field(init=False)
    model_manager: ModelFailoverManager = field(init=False)
    report_generator: ReportGenerator = field(init=False)
    
    run_id: str = field(default="", init=False)
    start_time: float = field(default=0, init=False)
    _stop_requested: bool = field(default=False, init=False)

    def __post_init__(self):
        self.task_queue = TaskQueue(self.config)
        self.model_manager = create_default_manager()
        self.report_generator = ReportGenerator(self.config.reports_dir)

    def setup_tasks(self):
        self.run_id = self.task_queue.create_run()
        for project in self.config.projects:
            self.task_queue.generate_tasks_for_project(project)

    def run(self) -> NightshiftReport:
        self.start_time = time.time()
        self.setup_tasks()
        
        print(f"[Nightshift] Starting run {self.run_id}")
        print(f"[Nightshift] Projects: {[p.name for p in self.config.projects]}")
        print(f"[Nightshift] Pending tasks: {self.task_queue.get_pending_count()}")
        
        max_seconds = self.config.max_duration_hours * 3600
        
        while not self._stop_requested:
            elapsed = time.time() - self.start_time
            if elapsed >= max_seconds:
                print(f"[Nightshift] Max duration reached ({self.config.max_duration_hours}h)")
                break
            
            task = self.task_queue.get_next_pending_task()
            if not task:
                print("[Nightshift] All tasks completed")
                break
            
            model = self.model_manager.get_available_model()
            if not model:
                print("[Nightshift] All models exhausted, waiting for quota refresh...")
                time.sleep(self.config.quota_check_interval_minutes * 60)
                continue
            
            self._execute_task(task, model)
        
        return self._generate_report()

    def _execute_task(self, task: ResearchTask, model):
        model_key = f"{model.provider}/{model.model_id}"
        print(f"[Nightshift] Executing {task.task_type.value} for {task.project_name} with {model_key}")
        
        self.task_queue.mark_in_progress(task.id, model_key)
        
        try:
            prompt = TASK_PROMPTS.get(task.task_type, "Analyze this project.")
            formatted_prompt = prompt.format(
                project_name=task.project_name,
                project_path=task.project_path
            )
            
            result = self._call_opencode_agent(
                agent_type=self._get_agent_for_task(task.task_type),
                prompt=formatted_prompt,
                model=model
            )
            
            findings = self._parse_findings(result, task)
            for finding in findings:
                self.task_queue.save_finding(task.id, finding)
            
            self.task_queue.mark_completed(task.id, tokens_used=1000, raw_output=result)
            print(f"[Nightshift] Completed {task.task_type.value}: {len(findings)} findings")
            
        except RateLimitError:
            self.model_manager.mark_rate_limited(model)
            self.task_queue.mark_failed(task.id, "Rate limited")
            print(f"[Nightshift] Rate limited on {model_key}, switching models...")
            
        except Exception as e:
            self.task_queue.mark_failed(task.id, str(e))
            print(f"[Nightshift] Task failed: {e}")

    def _get_agent_for_task(self, task_type: TaskType) -> str:
        research_tasks = {
            TaskType.DEPENDENCY_UPDATES,
            TaskType.SOTA_ALTERNATIVES, 
            TaskType.INTEGRATION_OPPORTUNITIES,
        }
        
        if task_type in research_tasks:
            return "librarian"
        return "explore"

    def _call_opencode_agent(self, agent_type: str, prompt: str, model) -> str:
        from .agent_client import get_agent_client
        import asyncio
        
        client = get_agent_client(use_mock=False)
        
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                client.call_agent(agent_type, prompt)
            )
            if result["success"]:
                return result["output"]
            else:
                raise Exception(result["error"] or "Agent call failed")
        finally:
            loop.close()

    def _parse_findings(self, result: str, task: ResearchTask) -> list[Finding]:
        findings = []
        try:
            data = json.loads(result)
            if isinstance(data, list):
                for item in data:
                    finding = Finding(
                        id=f"finding_{uuid.uuid4().hex[:8]}",
                        severity=FindingSeverity(item.get("severity", "info")),
                        title=item.get("title", "Untitled"),
                        description=item.get("description", ""),
                        location=item.get("location"),
                        recommendation=item.get("recommendation"),
                    )
                    findings.append(finding)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            findings.append(Finding(
                id=f"finding_{uuid.uuid4().hex[:8]}",
                severity=FindingSeverity.INFO,
                title="Raw Analysis Output",
                description=result[:2000] if result else "No output",
            ))
        return findings

    def _generate_report(self) -> NightshiftReport:
        stats = self.task_queue.get_statistics()
        
        projects = []
        for project_config in self.config.projects:
            findings = self.task_queue.get_findings_for_project(project_config.name)
            project_report = ProjectReport(
                name=project_config.name,
                path=project_config.path,
                findings=findings,
                tasks_completed=stats.get("completed", 0),
            )
            projects.append(project_report)
        
        report = NightshiftReport(
            run_id=self.run_id,
            started_at=datetime.fromtimestamp(self.start_time),
            completed_at=datetime.now(),
            projects=projects,
            total_tasks=stats.get("pending", 0) + stats.get("completed", 0) + stats.get("failed", 0),
            completed_tasks=stats.get("completed", 0),
            failed_tasks=stats.get("failed", 0),
            total_tokens=stats.get("total_tokens", 0),
            models_used=list(self.model_manager.get_status().keys()),
        )
        
        report_path = self.report_generator.generate(report, open_browser=True)
        print(f"[Nightshift] Report generated: {report_path}")
        
        return report

    def stop(self):
        self._stop_requested = True


class RateLimitError(Exception):
    pass


def run_nightshift(
    projects: list[str],
    duration_hours: float = 8.0,
) -> NightshiftReport:
    from .config import get_config
    
    config = get_config(projects, duration_hours)
    runner = NightshiftRunner(config)
    return runner.run()
