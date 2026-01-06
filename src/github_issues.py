import subprocess
import json
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from .models import Finding, FindingSeverity


@dataclass
class GitHubIssueCreator:
    repo: Optional[str] = None
    dry_run: bool = False
    created_issues: list[str] = None
    
    def __post_init__(self):
        self.created_issues = []
        if not self.repo:
            self.repo = self._detect_repo()

    def _detect_repo(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _issue_exists(self, title: str) -> bool:
        if not self.repo:
            return False
        try:
            result = subprocess.run(
                ["gh", "issue", "list", "--repo", self.repo, "--search", f'"{title}" in:title', "--json", "number"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                issues = json.loads(result.stdout)
                return len(issues) > 0
        except Exception:
            pass
        return False

    def create_issue_for_finding(self, finding: Finding, project_name: Optional[str] = None) -> Optional[str]:
        if finding.severity not in (FindingSeverity.CRITICAL, FindingSeverity.HIGH):
            return None
        
        title = f"[Nightshift] {finding.title}"
        
        if self._issue_exists(title):
            return None
        
        labels = ["nightshift", finding.severity.value]
        
        body_parts = [
            f"## {finding.severity.value.upper()} Finding",
            "",
            finding.description,
            "",
        ]
        
        if finding.location:
            body_parts.extend([
                "### Location",
                f"`{finding.location}`",
                "",
            ])
        
        if finding.recommendation:
            body_parts.extend([
                "### Recommendation", 
                finding.recommendation,
                "",
            ])
        
        body_parts.extend([
            "---",
            "*This issue was automatically created by Nightshift overnight analysis.*"
        ])
        
        body = "\n".join(body_parts)
        
        if self.dry_run:
            print(f"[DRY RUN] Would create issue: {title}")
            return f"dry-run-{finding.id}"
        
        if not self.repo:
            print(f"[WARNING] No repo detected, cannot create issue: {title}")
            return None
        
        try:
            result = subprocess.run(
                [
                    "gh", "issue", "create",
                    "--repo", self.repo,
                    "--title", title,
                    "--body", body,
                    "--label", ",".join(labels)
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                issue_url = result.stdout.strip()
                self.created_issues.append(issue_url)
                print(f"[Nightshift] Created issue: {issue_url}")
                return issue_url
            else:
                print(f"[ERROR] Failed to create issue: {result.stderr}")
                
        except Exception as e:
            print(f"[ERROR] Exception creating issue: {e}")
        
        return None

    def create_issues_for_findings(
        self, 
        findings: list[Finding],
        max_issues: int = 5
    ) -> list[str]:
        critical = [f for f in findings if f.severity == FindingSeverity.CRITICAL]
        high = [f for f in findings if f.severity == FindingSeverity.HIGH]
        
        to_create = (critical + high)[:max_issues]
        
        created = []
        for finding in to_create:
            url = self.create_issue_for_finding(finding)
            if url:
                created.append(url)
        
        return created
