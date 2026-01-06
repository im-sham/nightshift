from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import sqlite3
import json
from pathlib import Path
import uuid

from .models import ResearchTask, TaskStatus, TaskType, Finding, FindingSeverity
from .config import NightshiftConfig, ProjectConfig


@dataclass
class TaskQueue:
    config: NightshiftConfig
    _conn: Optional[sqlite3.Connection] = field(default=None, repr=False)

    def __post_init__(self):
        self._conn = sqlite3.connect(self.config.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                project_name TEXT NOT NULL,
                project_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                started_at TEXT,
                completed_at TEXT,
                model_used TEXT,
                tokens_used INTEGER DEFAULT 0,
                raw_output TEXT,
                error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS findings (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                location TEXT,
                recommendation TEXT,
                references_json TEXT,
                metadata_json TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );
            
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                total_tasks INTEGER DEFAULT 0,
                completed_tasks INTEGER DEFAULT 0,
                failed_tasks INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                models_used_json TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_name);
            CREATE INDEX IF NOT EXISTS idx_findings_task ON findings(task_id);
        """)
        self._conn.commit()

    def create_run(self) -> str:
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self._conn.execute(
            "INSERT INTO runs (id, started_at) VALUES (?, ?)",
            (run_id, datetime.now().isoformat())
        )
        self._conn.commit()
        return run_id

    def generate_tasks_for_project(self, project: ProjectConfig) -> list[ResearchTask]:
        tasks = []
        
        audit_tasks = [
            (TaskType.FILE_STRUCTURE_ANALYSIS, 1),
            (TaskType.DEPENDENCY_AUDIT, 2),
            (TaskType.CODE_PATTERN_ANALYSIS, 3),
            (TaskType.TECH_DEBT_SCAN, 4),
            (TaskType.SECURITY_REVIEW, 5),
        ]
        
        enhancement_tasks = [
            (TaskType.ARCHITECTURE_REVIEW, 6),
            (TaskType.BEST_PRACTICES_CHECK, 7),
            (TaskType.PERFORMANCE_ANALYSIS, 8),
        ]
        
        research_tasks = [
            (TaskType.DEPENDENCY_UPDATES, 9),
            (TaskType.SOTA_ALTERNATIVES, 10),
            (TaskType.INTEGRATION_OPPORTUNITIES, 11),
        ]
        
        all_task_types = []
        if self.config.enable_codebase_audit:
            all_task_types.extend(audit_tasks)
        if self.config.enable_enhancement_recommendations:
            all_task_types.extend(enhancement_tasks)
        if self.config.enable_tool_stack_research:
            all_task_types.extend(research_tasks)
        
        for task_type, priority in all_task_types:
            task = ResearchTask(
                id=f"{project.name}_{task_type.value}_{uuid.uuid4().hex[:8]}",
                task_type=task_type,
                project_name=project.name,
                project_path=project.path,
                priority=priority,
            )
            tasks.append(task)
            self._save_task(task)
        
        return tasks

    def _save_task(self, task: ResearchTask):
        self._conn.execute("""
            INSERT OR REPLACE INTO tasks 
            (id, task_type, project_name, project_path, status, priority, 
             started_at, completed_at, model_used, tokens_used, raw_output, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.id, task.task_type.value, task.project_name, str(task.project_path),
            task.status.value, task.priority, 
            task.started_at.isoformat() if task.started_at else None,
            task.completed_at.isoformat() if task.completed_at else None,
            task.model_used, task.tokens_used, task.raw_output, task.error
        ))
        self._conn.commit()

    def save_finding(self, task_id: str, finding: Finding):
        self._conn.execute("""
            INSERT INTO findings 
            (id, task_id, severity, title, description, location, recommendation, references_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            finding.id, task_id, finding.severity.value, finding.title, 
            finding.description, finding.location, finding.recommendation,
            json.dumps(finding.references), json.dumps(finding.metadata)
        ))
        self._conn.commit()

    def get_next_pending_task(self) -> Optional[ResearchTask]:
        row = self._conn.execute("""
            SELECT * FROM tasks 
            WHERE status = 'pending' 
            ORDER BY priority ASC 
            LIMIT 1
        """).fetchone()
        
        if row:
            return self._row_to_task(row)
        return None

    def get_pending_count(self) -> int:
        result = self._conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'pending'"
        ).fetchone()
        return result[0] if result else 0

    def get_completed_count(self) -> int:
        result = self._conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'completed'"
        ).fetchone()
        return result[0] if result else 0

    def mark_in_progress(self, task_id: str, model: str):
        self._conn.execute("""
            UPDATE tasks SET status = 'in_progress', started_at = ?, model_used = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), model, task_id))
        self._conn.commit()

    def mark_completed(self, task_id: str, tokens_used: int, raw_output: str):
        self._conn.execute("""
            UPDATE tasks SET status = 'completed', completed_at = ?, tokens_used = ?, raw_output = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), tokens_used, raw_output, task_id))
        self._conn.commit()

    def mark_failed(self, task_id: str, error: str):
        self._conn.execute("""
            UPDATE tasks SET status = 'failed', completed_at = ?, error = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), error, task_id))
        self._conn.commit()

    def get_all_findings(self) -> list[Finding]:
        rows = self._conn.execute("SELECT * FROM findings").fetchall()
        return [self._row_to_finding(row) for row in rows]

    def get_findings_for_project(self, project_name: str) -> list[Finding]:
        rows = self._conn.execute("""
            SELECT f.* FROM findings f
            JOIN tasks t ON f.task_id = t.id
            WHERE t.project_name = ?
        """, (project_name,)).fetchall()
        return [self._row_to_finding(row) for row in rows]

    def _row_to_task(self, row) -> ResearchTask:
        return ResearchTask(
            id=row["id"],
            task_type=TaskType(row["task_type"]),
            project_name=row["project_name"],
            project_path=Path(row["project_path"]),
            status=TaskStatus(row["status"]),
            priority=row["priority"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            model_used=row["model_used"],
            tokens_used=row["tokens_used"] or 0,
            raw_output=row["raw_output"],
            error=row["error"],
        )

    def _row_to_finding(self, row) -> Finding:
        return Finding(
            id=row["id"],
            severity=FindingSeverity(row["severity"]),
            title=row["title"],
            description=row["description"],
            location=row["location"],
            recommendation=row["recommendation"],
            references=json.loads(row["references_json"]) if row["references_json"] else [],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )

    def get_statistics(self) -> dict:
        stats = {}
        for status in TaskStatus:
            result = self._conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status = ?", (status.value,)
            ).fetchone()
            stats[status.value] = result[0] if result else 0
        
        tokens_result = self._conn.execute(
            "SELECT SUM(tokens_used) FROM tasks WHERE status = 'completed'"
        ).fetchone()
        stats["total_tokens"] = tokens_result[0] or 0
        
        return stats

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
