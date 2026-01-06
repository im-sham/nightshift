import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Schedule:
    id: str
    projects: list[str]
    time: str
    days: str
    duration_hours: float
    priority_mode: str
    enabled: bool = True
    slack_webhook: Optional[str] = None
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class ScheduleManager:
    def __init__(self, config_dir: Path):
        self.config_file = config_dir / "schedules.json"
        self.config_dir = config_dir
        self._schedules: list[Schedule] = []
        self._load()
    
    def _load(self):
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text())
                self._schedules = [Schedule(**s) for s in data.get("schedules", [])]
            except Exception:
                self._schedules = []
        else:
            self._schedules = []
    
    def _save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = {"schedules": [asdict(s) for s in self._schedules]}
        self.config_file.write_text(json.dumps(data, indent=2))
    
    def add(
        self,
        projects: list[str],
        schedule_time: str,
        days: str = "daily",
        duration_hours: float = 8.0,
        priority_mode: str = "balanced",
        slack_webhook: Optional[str] = None
    ) -> Schedule:
        schedule = Schedule(
            id=str(uuid.uuid4())[:8],
            projects=projects,
            time=schedule_time,
            days=days,
            duration_hours=duration_hours,
            priority_mode=priority_mode,
            slack_webhook=slack_webhook
        )
        self._schedules.append(schedule)
        self._save()
        return schedule
    
    def remove(self, schedule_id: str) -> bool:
        original_len = len(self._schedules)
        self._schedules = [s for s in self._schedules if s.id != schedule_id]
        if len(self._schedules) < original_len:
            self._save()
            return True
        return False
    
    def list_all(self) -> list[Schedule]:
        return self._schedules
    
    def get(self, schedule_id: str) -> Optional[Schedule]:
        for s in self._schedules:
            if s.id == schedule_id:
                return s
        return None
    
    def toggle(self, schedule_id: str) -> Optional[Schedule]:
        for s in self._schedules:
            if s.id == schedule_id:
                s.enabled = not s.enabled
                self._save()
                return s
        return None
    
    def get_due_schedules(self) -> list[Schedule]:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.strftime("%A").lower()
        
        due = []
        for s in self._schedules:
            if not s.enabled:
                continue
            
            if s.time != current_time:
                continue
            
            if s.days == "daily":
                due.append(s)
            elif s.days == "weekdays" and current_day not in ("saturday", "sunday"):
                due.append(s)
            elif s.days == "weekends" and current_day in ("saturday", "sunday"):
                due.append(s)
            elif current_day in s.days.lower():
                due.append(s)
        
        return due
    
    def generate_launchd_plist(self, schedule: Schedule) -> str:
        hour, minute = schedule.time.split(":")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nightshift.schedule.{schedule.id}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/curl</string>
        <string>-X</string>
        <string>POST</string>
        <string>-H</string>
        <string>Content-Type: application/json</string>
        <string>-d</string>
        <string>{{"projects": {json.dumps(schedule.projects)}, "duration_hours": {schedule.duration_hours}, "priority_mode": "{schedule.priority_mode}"}}</string>
        <string>http://127.0.0.1:7890/start</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{int(hour)}</integer>
        <key>Minute</key>
        <integer>{int(minute)}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{self.config_dir}/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>{self.config_dir}/launchd.error.log</string>
</dict>
</plist>"""
    
    def generate_cron_line(self, schedule: Schedule) -> str:
        hour, minute = schedule.time.split(":")
        projects_json = json.dumps(schedule.projects).replace('"', '\\"')
        
        day_spec = "*"
        if schedule.days == "weekdays":
            day_spec = "1-5"
        elif schedule.days == "weekends":
            day_spec = "0,6"
        
        return f'{minute} {hour} * * {day_spec} curl -X POST -H "Content-Type: application/json" -d \'{{"projects": {projects_json}, "duration_hours": {schedule.duration_hours}}}\' http://127.0.0.1:7890/start'
