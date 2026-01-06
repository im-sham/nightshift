"""
Notification support for Nightshift.
Supports Slack webhooks and generic HTTP webhooks.
"""

import httpx
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from .models import NightshiftReport, FindingSeverity


@dataclass
class NotificationConfig:
    """Configuration for notifications."""
    slack_webhook_url: Optional[str] = None
    generic_webhook_url: Optional[str] = None
    notify_on_complete: bool = True
    notify_on_critical: bool = True
    notify_on_failure: bool = True


class NotificationManager:
    """Manages sending notifications for nightshift events."""
    
    def __init__(self, config: NotificationConfig):
        self.config = config
        self._client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
    
    async def notify_run_started(self, run_id: str, projects: list[str], duration_hours: float):
        """Send notification when a run starts."""
        message = {
            "event": "run_started",
            "run_id": run_id,
            "projects": projects,
            "duration_hours": duration_hours,
            "timestamp": datetime.now().isoformat(),
        }
        
        if self.config.slack_webhook_url:
            await self._send_slack(
                text=f":moon: *Nightshift Started*\nRun ID: `{run_id}`\nProjects: {', '.join(projects)}\nDuration: {duration_hours}h",
                color="#238636"
            )
        
        if self.config.generic_webhook_url:
            await self._send_webhook(message)
    
    async def notify_run_completed(self, report: NightshiftReport):
        """Send notification when a run completes."""
        if not self.config.notify_on_complete:
            return
        
        critical_count = sum(
            1 for f in report.all_findings 
            if f.severity == FindingSeverity.CRITICAL
        )
        high_count = sum(
            1 for f in report.all_findings 
            if f.severity == FindingSeverity.HIGH
        )
        
        message = {
            "event": "run_completed",
            "run_id": report.run_id,
            "duration_minutes": report.duration_minutes,
            "total_findings": len(report.all_findings),
            "critical_findings": critical_count,
            "high_findings": high_count,
            "tasks_completed": report.completed_tasks,
            "tasks_failed": report.failed_tasks,
            "timestamp": datetime.now().isoformat(),
        }
        
        if self.config.slack_webhook_url:
            severity_emoji = ":rotating_light:" if critical_count > 0 else ":white_check_mark:"
            await self._send_slack(
                text=f"{severity_emoji} *Nightshift Completed*\n"
                     f"Run ID: `{report.run_id}`\n"
                     f"Duration: {report.duration_minutes:.1f} minutes\n"
                     f"Findings: {len(report.all_findings)} total "
                     f"({critical_count} critical, {high_count} high)\n"
                     f"Tasks: {report.completed_tasks} completed, {report.failed_tasks} failed",
                color="#f85149" if critical_count > 0 else "#238636"
            )
        
        if self.config.generic_webhook_url:
            await self._send_webhook(message)
    
    async def notify_critical_finding(self, finding_title: str, project: str, run_id: str):
        """Send immediate notification for critical findings."""
        if not self.config.notify_on_critical:
            return
        
        message = {
            "event": "critical_finding",
            "run_id": run_id,
            "project": project,
            "finding_title": finding_title,
            "timestamp": datetime.now().isoformat(),
        }
        
        if self.config.slack_webhook_url:
            await self._send_slack(
                text=f":rotating_light: *Critical Finding Detected*\n"
                     f"Project: `{project}`\n"
                     f"Finding: {finding_title}",
                color="#f85149"
            )
        
        if self.config.generic_webhook_url:
            await self._send_webhook(message)
    
    async def notify_run_failed(self, run_id: str, error: str):
        """Send notification when a run fails."""
        if not self.config.notify_on_failure:
            return
        
        message = {
            "event": "run_failed",
            "run_id": run_id,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }
        
        if self.config.slack_webhook_url:
            await self._send_slack(
                text=f":x: *Nightshift Failed*\n"
                     f"Run ID: `{run_id}`\n"
                     f"Error: {error[:500]}",
                color="#f85149"
            )
        
        if self.config.generic_webhook_url:
            await self._send_webhook(message)
    
    async def _send_slack(self, text: str, color: str = "#238636"):
        """Send a Slack webhook notification."""
        if not self.config.slack_webhook_url:
            return
        
        payload = {
            "attachments": [{
                "color": color,
                "text": text,
                "mrkdwn_in": ["text"],
                "footer": "Nightshift",
                "ts": int(datetime.now().timestamp())
            }]
        }
        
        try:
            response = await self._client.post(
                self.config.slack_webhook_url,
                json=payload
            )
            response.raise_for_status()
        except Exception as e:
            print(f"Failed to send Slack notification: {e}")
    
    async def _send_webhook(self, message: dict):
        """Send a generic webhook notification."""
        if not self.config.generic_webhook_url:
            return
        
        try:
            response = await self._client.post(
                self.config.generic_webhook_url,
                json=message,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
        except Exception as e:
            print(f"Failed to send webhook notification: {e}")


def get_notification_manager(
    slack_webhook: Optional[str] = None,
    generic_webhook: Optional[str] = None
) -> NotificationManager:
    """Factory function to create a notification manager."""
    config = NotificationConfig(
        slack_webhook_url=slack_webhook,
        generic_webhook_url=generic_webhook
    )
    return NotificationManager(config)
