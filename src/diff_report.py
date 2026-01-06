from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from pathlib import Path
import json

from .config import NightshiftConfig
from .models import Finding, FindingSeverity
from .task_queue import TaskQueue


@dataclass
class FindingDiff:
    new_findings: list[Finding]
    fixed_findings: list[Finding]
    persistent_findings: list[Finding]
    
    @property
    def summary(self) -> str:
        parts = []
        if self.new_findings:
            parts.append(f"{len(self.new_findings)} new")
        if self.fixed_findings:
            parts.append(f"{len(self.fixed_findings)} fixed")
        if self.persistent_findings:
            parts.append(f"{len(self.persistent_findings)} persistent")
        return ", ".join(parts) if parts else "No changes"


class DiffReportGenerator:
    def __init__(self, config: NightshiftConfig):
        self.config = config
        self.history_file = config.data_dir / "finding_history.json"

    def _load_history(self) -> dict:
        if self.history_file.exists():
            with open(self.history_file) as f:
                return json.load(f)
        return {"runs": [], "findings": {}}

    def _save_history(self, history: dict):
        with open(self.history_file, "w") as f:
            json.dump(history, f, indent=2, default=str)

    def _finding_signature(self, finding: Finding) -> str:
        return f"{finding.title}|{finding.location or 'global'}|{finding.severity.value}"

    def record_run(self, run_id: str, findings: list[Finding]):
        history = self._load_history()
        
        run_record = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "finding_signatures": [self._finding_signature(f) for f in findings],
        }
        history["runs"].append(run_record)
        
        if len(history["runs"]) > 30:
            history["runs"] = history["runs"][-30:]
        
        for finding in findings:
            sig = self._finding_signature(finding)
            if sig not in history["findings"]:
                history["findings"][sig] = {
                    "first_seen": datetime.now().isoformat(),
                    "last_seen": datetime.now().isoformat(),
                    "occurrences": 1,
                    "finding_data": {
                        "title": finding.title,
                        "severity": finding.severity.value,
                        "description": finding.description,
                        "location": finding.location,
                        "recommendation": finding.recommendation,
                    }
                }
            else:
                history["findings"][sig]["last_seen"] = datetime.now().isoformat()
                history["findings"][sig]["occurrences"] += 1
        
        self._save_history(history)

    def compute_diff(
        self, 
        current_findings: list[Finding],
        compare_to_run_id: Optional[str] = None
    ) -> FindingDiff:
        history = self._load_history()
        
        if not history["runs"]:
            return FindingDiff(
                new_findings=current_findings,
                fixed_findings=[],
                persistent_findings=[]
            )
        
        if compare_to_run_id:
            previous_run = next(
                (r for r in history["runs"] if r["run_id"] == compare_to_run_id),
                None
            )
        else:
            previous_run = history["runs"][-1] if history["runs"] else None
        
        if not previous_run:
            return FindingDiff(
                new_findings=current_findings,
                fixed_findings=[],
                persistent_findings=[]
            )
        
        previous_sigs = set(previous_run["finding_signatures"])
        current_sigs = {self._finding_signature(f): f for f in current_findings}
        
        new_findings = []
        persistent_findings = []
        
        for sig, finding in current_sigs.items():
            if sig in previous_sigs:
                persistent_findings.append(finding)
            else:
                new_findings.append(finding)
        
        fixed_findings = []
        for sig in previous_sigs:
            if sig not in current_sigs:
                finding_data = history["findings"].get(sig, {}).get("finding_data", {})
                if finding_data:
                    fixed_findings.append(Finding(
                        id=f"fixed_{sig[:8]}",
                        severity=FindingSeverity(finding_data.get("severity", "info")),
                        title=finding_data.get("title", "Unknown"),
                        description=finding_data.get("description", ""),
                        location=finding_data.get("location"),
                        recommendation=finding_data.get("recommendation"),
                    ))
        
        return FindingDiff(
            new_findings=new_findings,
            fixed_findings=fixed_findings,
            persistent_findings=persistent_findings
        )

    def generate_diff_report(self, compare_to_run_id: Optional[str] = None) -> str:
        queue = TaskQueue(self.config)
        current_findings = queue.get_all_findings()
        queue.close()
        
        diff = self.compute_diff(current_findings, compare_to_run_id)
        
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Nightshift Diff Report</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            background: #0d1117; color: #c9d1d9; padding: 2rem;
        }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        h1 {{ color: #58a6ff; }}
        .summary {{ 
            background: #161b22; padding: 1.5rem; border-radius: 8px;
            margin-bottom: 2rem; border-left: 4px solid #58a6ff;
        }}
        .section {{ margin-bottom: 2rem; }}
        .section-header {{ 
            display: flex; align-items: center; gap: 0.5rem;
            margin-bottom: 1rem;
        }}
        .badge {{ 
            padding: 0.25rem 0.75rem; border-radius: 12px;
            font-size: 0.85rem; font-weight: 600;
        }}
        .badge-new {{ background: #f85149; }}
        .badge-fixed {{ background: #3fb950; color: #000; }}
        .badge-persistent {{ background: #d29922; color: #000; }}
        .finding {{
            background: #21262d; padding: 1rem; margin-bottom: 0.75rem;
            border-radius: 6px; border-left: 3px solid #30363d;
        }}
        .finding-title {{ font-weight: 600; margin-bottom: 0.25rem; }}
        .finding-location {{ color: #8b949e; font-size: 0.85rem; font-family: monospace; }}
        .empty {{ color: #8b949e; font-style: italic; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Differential Report</h1>
        <div class="summary">
            <strong>Summary:</strong> {diff.summary}
        </div>
        
        <div class="section">
            <div class="section-header">
                <span class="badge badge-new">NEW</span>
                <h2>{len(diff.new_findings)} New Issues</h2>
            </div>
            {"".join(self._render_finding(f) for f in diff.new_findings) or '<p class="empty">No new issues found</p>'}
        </div>
        
        <div class="section">
            <div class="section-header">
                <span class="badge badge-fixed">FIXED</span>
                <h2>{len(diff.fixed_findings)} Fixed Issues</h2>
            </div>
            {"".join(self._render_finding(f, fixed=True) for f in diff.fixed_findings) or '<p class="empty">No issues fixed since last run</p>'}
        </div>
        
        <div class="section">
            <div class="section-header">
                <span class="badge badge-persistent">PERSISTENT</span>
                <h2>{len(diff.persistent_findings)} Persistent Issues</h2>
            </div>
            {"".join(self._render_finding(f) for f in diff.persistent_findings) or '<p class="empty">No persistent issues</p>'}
        </div>
    </div>
</body>
</html>
"""
        return html

    def _render_finding(self, finding: Finding, fixed: bool = False) -> str:
        style = "text-decoration: line-through; opacity: 0.7;" if fixed else ""
        return f"""
        <div class="finding" style="{style}">
            <div class="finding-title">[{finding.severity.value.upper()}] {finding.title}</div>
            {f'<div class="finding-location">{finding.location}</div>' if finding.location else ''}
        </div>
        """
