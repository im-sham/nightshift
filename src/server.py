from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from pathlib import Path
import threading

from .config import get_config, NightshiftConfig, DEFAULT_PROJECTS
from .runner import NightshiftRunner
from .report_generator import ReportGenerator
from .model_manager import create_default_manager
from .diff_report import DiffReportGenerator
from .github_issues import GitHubIssueCreator
from .notifications import get_notification_manager
from .scheduler import ScheduleManager


DASHBOARD_HTML = Path(__file__).parent / "dashboard.html"


app = FastAPI(
    title="Nightshift API",
    description="Overnight autonomous research agent",
    version="0.1.0"
)


class StartRequest(BaseModel):
    projects: list[str]
    duration_hours: float = 8.0
    create_github_issues: bool = False
    priority_mode: str = "balanced"
    slack_webhook: Optional[str] = None
    webhook_url: Optional[str] = None


class RunStatus(BaseModel):
    run_id: Optional[str]
    status: str
    started_at: Optional[str]
    elapsed_minutes: float
    completed_tasks: int
    pending_tasks: int
    total_findings: int
    current_task: Optional[str]
    models_status: dict


class ScheduleRequest(BaseModel):
    projects: list[str]
    time: str
    days: str = "daily"
    duration_hours: float = 8.0
    priority_mode: str = "balanced"
    slack_webhook: Optional[str] = None


_current_runner: Optional[NightshiftRunner] = None
_runner_thread: Optional[threading.Thread] = None
_run_status = {"status": "idle", "run_id": None}
_schedule_manager: Optional[ScheduleManager] = None


def _get_schedule_manager() -> ScheduleManager:
    global _schedule_manager
    if _schedule_manager is None:
        config = NightshiftConfig()
        _schedule_manager = ScheduleManager(config.data_dir)
    return _schedule_manager


def _run_in_thread(runner: NightshiftRunner, create_issues: bool, slack_webhook: Optional[str] = None, webhook_url: Optional[str] = None):
    global _run_status
    import asyncio
    
    notifier = None
    if slack_webhook or webhook_url:
        notifier = get_notification_manager(slack_webhook, webhook_url)
    
    try:
        if not runner.run_id:
            runner.setup_tasks()

        _run_status["status"] = "running"
        _run_status["run_id"] = runner.run_id

        if notifier:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(notifier.notify_run_started(
                runner.run_id,
                [p.name for p in runner.config.projects],
                runner.config.max_duration_hours
            ))
            loop.close()
        
        report = runner.run()
        _run_status["status"] = "completed"
        _run_status["report_path"] = str(runner.report_generator.get_latest_report())
        
        if create_issues:
            issue_creator = GitHubIssueCreator()
            for finding in report.all_findings:
                if finding.severity.value in ("critical", "high"):
                    issue_creator.create_issue_for_finding(finding)
        
        if notifier:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(notifier.notify_run_completed(report))
            loop.run_until_complete(notifier.close())
            loop.close()
                    
    except Exception as e:
        _run_status["status"] = "failed"
        _run_status["error"] = str(e)
        
        if notifier:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(notifier.notify_run_failed(runner.run_id, str(e)))
            loop.run_until_complete(notifier.close())
            loop.close()


@app.post("/start")
async def start_run(request: StartRequest):
    global _current_runner, _runner_thread, _run_status
    
    if _run_status["status"] == "running":
        raise HTTPException(400, "A run is already in progress")
    
    config = get_config(
        request.projects,
        request.duration_hours,
        priority_mode=request.priority_mode,
        open_report_in_browser=False,
    )
    _current_runner = NightshiftRunner(config)
    _run_status = {
        "status": "starting",
        "run_id": None,
        "started_at": datetime.now().isoformat(),
    }
    
    _runner_thread = threading.Thread(
        target=_run_in_thread,
        args=(_current_runner, request.create_github_issues, request.slack_webhook, request.webhook_url),
        daemon=True
    )
    _runner_thread.start()
    
    return {"message": "Nightshift started", "projects": request.projects}


@app.post("/stop")
async def stop_run():
    global _current_runner, _run_status
    
    if _current_runner and _run_status["status"] == "running":
        _current_runner.stop()
        _run_status["status"] = "stopping"
        return {"message": "Stop requested"}
    
    raise HTTPException(400, "No run in progress")


@app.get("/status", response_model=RunStatus)
async def get_status():
    global _current_runner, _run_status
    
    if not _current_runner or _run_status["status"] == "idle":
        return RunStatus(
            run_id=None,
            status="idle",
            started_at=None,
            elapsed_minutes=0,
            completed_tasks=0,
            pending_tasks=0,
            total_findings=0,
            current_task=None,
            models_status={}
        )
    
    queue = _current_runner.task_queue
    stats = queue.get_statistics()
    
    elapsed = 0
    if _current_runner.start_time:
        elapsed = (datetime.now().timestamp() - _current_runner.start_time) / 60
    
    return RunStatus(
        run_id=_current_runner.run_id,
        status=_run_status["status"],
        started_at=_run_status.get("started_at"),
        elapsed_minutes=round(elapsed, 1),
        completed_tasks=stats.get("completed", 0),
        pending_tasks=stats.get("pending", 0),
        total_findings=len(queue.get_all_findings(run_id=_current_runner.run_id)),
        current_task=None,
        models_status=_current_runner.model_manager.get_status()
    )


@app.get("/report/latest")
async def get_latest_report():
    config = NightshiftConfig()
    generator = ReportGenerator(config.reports_dir)
    report_path = generator.get_latest_report()
    
    if report_path and report_path.exists():
        return FileResponse(report_path, media_type="text/html")
    
    raise HTTPException(404, "No reports found")


@app.get("/report/diff")
async def get_diff_report(compare_to: Optional[str] = None):
    config = NightshiftConfig()
    diff_gen = DiffReportGenerator(config)
    
    diff_html = diff_gen.generate_diff_report(compare_to_run_id=compare_to)
    return HTMLResponse(diff_html)


@app.get("/reports")
async def list_reports():
    config = NightshiftConfig()
    generator = ReportGenerator(config.reports_dir)
    reports = generator.list_reports()
    
    return {
        "reports": [
            {
                "path": str(p),
                "name": p.stem,
                "created": datetime.fromtimestamp(p.stat().st_mtime).isoformat()
            }
            for p in reports[:20]
        ]
    }


@app.get("/projects")
async def list_available_projects():
    return {
        "configured": {k: str(v) for k, v in DEFAULT_PROJECTS.items()},
    }


@app.get("/models")
async def get_model_status():
    manager = create_default_manager()
    return manager.get_status()


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/schedules")
async def list_schedules():
    manager = _get_schedule_manager()
    schedules = manager.list_all()
    return {
        "schedules": [
            {
                "id": s.id,
                "projects": s.projects,
                "time": s.time,
                "days": s.days,
                "duration_hours": s.duration_hours,
                "priority_mode": s.priority_mode,
                "enabled": s.enabled,
                "created_at": s.created_at
            }
            for s in schedules
        ]
    }


@app.post("/schedules")
async def add_schedule(request: ScheduleRequest):
    manager = _get_schedule_manager()
    schedule = manager.add(
        projects=request.projects,
        schedule_time=request.time,
        days=request.days,
        duration_hours=request.duration_hours,
        priority_mode=request.priority_mode,
        slack_webhook=request.slack_webhook
    )
    
    cron_line = manager.generate_cron_line(schedule)
    
    return {
        "message": "Schedule created",
        "schedule_id": schedule.id,
        "cron": cron_line,
        "hint": "Add the cron line to your crontab, or use launchd on macOS"
    }


@app.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    manager = _get_schedule_manager()
    if manager.remove(schedule_id):
        return {"message": "Schedule deleted"}
    raise HTTPException(404, "Schedule not found")


@app.post("/schedules/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str):
    manager = _get_schedule_manager()
    schedule = manager.toggle(schedule_id)
    if schedule:
        return {"message": f"Schedule {'enabled' if schedule.enabled else 'disabled'}", "enabled": schedule.enabled}
    raise HTTPException(404, "Schedule not found")


@app.get("/schedules/{schedule_id}/launchd")
async def get_launchd_plist(schedule_id: str):
    manager = _get_schedule_manager()
    schedule = manager.get(schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    
    plist = manager.generate_launchd_plist(schedule)
    return HTMLResponse(plist, media_type="application/xml")


@app.get("/")
async def dashboard():
    if DASHBOARD_HTML.exists():
        return FileResponse(DASHBOARD_HTML, media_type="text/html")
    raise HTTPException(404, "Dashboard not found")


def run_server(host: str = "127.0.0.1", port: int = 7890):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
