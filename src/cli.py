import typer
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import subprocess
import shutil
import tempfile
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Nightshift - Overnight autonomous research agent")
console = Console()


@dataclass
class DoctorCheck:
    name: str
    status: str
    details: str
    action: str = ""


@app.command()
def start(
    projects: list[str] = typer.Argument(
        ...,
        help="Project names or paths to analyze (e.g., opsorchestra ghost-sentry)"
    ),
    duration: Optional[float] = typer.Option(
        None,
        "--duration", "-d",
        help="Maximum duration in hours (defaults to config file value if set)"
    ),
    priority_mode: Optional[str] = typer.Option(
        None,
        "--priority-mode", "-m",
        help="Task prioritization mode (defaults to config file value if set)",
    ),
):
    """Start a nightshift research run."""
    from .runner import run_nightshift
    
    console.print(f"[bold green]Starting Nightshift[/bold green]")
    console.print(f"Projects: {', '.join(projects)}")
    console.print(f"Max duration: {duration if duration is not None else 'config default'}")
    console.print(f"Priority mode: {priority_mode if priority_mode is not None else 'config default'}")
    console.print()
    
    try:
        report = run_nightshift(projects, duration, priority_mode=priority_mode)
        console.print(f"\n[bold green]Nightshift completed![/bold green]")
        console.print(f"Tasks completed: {report.completed_tasks}")
        console.print(f"Findings: {len(report.all_findings)}")
    except KeyboardInterrupt:
        console.print("\n[yellow]Nightshift interrupted[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def init(
    config_path: Optional[Path] = typer.Option(
        None,
        "--config-path",
        help="Custom path for config.toml",
    ),
    add_current_project: bool = typer.Option(
        True,
        "--add-current-project/--no-add-current-project",
        help="Add current working directory as a project alias",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing config without prompting",
    ),
):
    """Create a starter Nightshift config file."""
    from .config import get_config_path, render_default_config_toml

    target_path = get_config_path(config_path)
    current_project = Path.cwd() if add_current_project else None
    content = render_default_config_toml(current_project)

    if target_path.exists() and not force:
        if not typer.confirm(f"{target_path} already exists. Overwrite?"):
            console.print("[yellow]Init cancelled.[/yellow]")
            raise typer.Exit(1)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content)

    console.print(f"[green]Created config:[/green] {target_path}")
    if current_project:
        console.print(f"[green]Added project alias for:[/green] {current_project}")
    console.print("\nNext steps:")
    console.print("1. Edit the project aliases and defaults in config.toml")
    console.print("2. Run [bold]nightshift doctor[/bold] to validate setup")
    console.print("3. Start a run with [bold]nightshift start <project-alias>[/bold]")


def _status_label(status: str) -> str:
    if status == "pass":
        return "[green]PASS[/green]"
    if status == "warn":
        return "[yellow]WARN[/yellow]"
    return "[red]FAIL[/red]"


@app.command()
def doctor():
    """Validate local Nightshift/OpenCode setup and print fixes."""
    from .config import get_config_path, get_data_dir, load_user_config, get_default_project_aliases

    checks: list[DoctorCheck] = []

    opencode_path = shutil.which("opencode")
    if opencode_path:
        checks.append(DoctorCheck("OpenCode CLI", "pass", f"Found at {opencode_path}"))
    else:
        checks.append(DoctorCheck("OpenCode CLI", "fail", "Not installed", "Install OpenCode and ensure `opencode` is on PATH"))

    if opencode_path:
        try:
            models_result = subprocess.run(
                ["opencode", "models"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            models = [line.strip() for line in models_result.stdout.splitlines() if "/" in line]
            if models_result.returncode == 0 and models:
                checks.append(DoctorCheck("OpenCode models", "pass", f"{len(models)} model(s) available"))
            elif models_result.returncode == 0:
                checks.append(DoctorCheck("OpenCode models", "warn", "No models detected", "Run `opencode auth` and configure at least one provider"))
            else:
                details = models_result.stderr.strip().splitlines()[:1]
                checks.append(DoctorCheck("OpenCode models", "fail", details[0] if details else "Command failed", "Run `opencode auth` and retry"))
        except subprocess.TimeoutExpired:
            checks.append(DoctorCheck("OpenCode models", "warn", "Timed out while checking models", "Retry later or run `opencode models` manually"))

    gh_path = shutil.which("gh")
    if gh_path:
        try:
            gh_status = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if gh_status.returncode == 0:
                checks.append(DoctorCheck("GitHub CLI auth", "pass", "Authenticated"))
            else:
                checks.append(DoctorCheck("GitHub CLI auth", "warn", "Not authenticated", "Run `gh auth login` to enable issue/PR workflows"))
        except subprocess.TimeoutExpired:
            checks.append(DoctorCheck("GitHub CLI auth", "warn", "Timed out", "Run `gh auth status` manually"))
    else:
        checks.append(DoctorCheck("GitHub CLI", "warn", "Not installed", "Install `gh` if you want auto issue/PR workflows"))

    data_dir = get_data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data_dir, prefix=".doctor_", delete=True):
            pass
        checks.append(DoctorCheck("Data directory", "pass", str(data_dir)))
    except Exception as e:
        checks.append(DoctorCheck("Data directory", "fail", f"{data_dir} is not writable: {e}", "Set `NIGHTSHIFT_DATA_DIR` to a writable location"))

    config_path = get_config_path()
    if config_path.exists():
        cfg = load_user_config(config_path)
        aliases = get_default_project_aliases(user_config=cfg)
        checks.append(
            DoctorCheck(
                "Config file",
                "pass",
                f"{config_path} ({len(aliases)} project alias(es))",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                "Config file",
                "warn",
                f"Missing {config_path}",
                "Run `nightshift init` to generate a starter config",
            )
        )

    plugin_dir = Path(__file__).resolve().parent.parent / "plugin"
    if (plugin_dir / "package.json").exists():
        if (plugin_dir / "node_modules").exists():
            checks.append(DoctorCheck("Plugin dependencies", "pass", "Installed"))
        else:
            checks.append(DoctorCheck("Plugin dependencies", "warn", "Not installed", f"Run `cd {plugin_dir} && bun install`"))

    table = Table(title="Nightshift Doctor")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Details", style="white")
    table.add_column("Action", style="dim")

    for item in checks:
        table.add_row(item.name, _status_label(item.status), item.details, item.action)

    console.print(table)

    has_failures = any(item.status == "fail" for item in checks)
    if has_failures:
        raise typer.Exit(1)


@app.command()
def report(
    open_browser: bool = typer.Option(
        True,
        "--open/--no-open",
        help="Open report in browser"
    ),
):
    """Open the latest nightshift report."""
    from .config import NightshiftConfig
    from .report_generator import ReportGenerator
    
    config = NightshiftConfig()
    generator = ReportGenerator(config.reports_dir)
    
    report_path = generator.get_latest_report()
    if report_path:
        console.print(f"[green]Latest report:[/green] {report_path}")
        if open_browser:
            generator.open_latest_report()
    else:
        console.print("[yellow]No reports found[/yellow]")


@app.command("list")
def list_reports():
    """List all available reports."""
    from .config import NightshiftConfig
    from .report_generator import ReportGenerator
    
    config = NightshiftConfig()
    generator = ReportGenerator(config.reports_dir)
    
    reports = generator.list_reports()
    
    if not reports:
        console.print("[yellow]No reports found[/yellow]")
        return
    
    table = Table(title="Nightshift Reports")
    table.add_column("Date", style="cyan")
    table.add_column("Path", style="dim")
    
    for report_path in reports[:10]:
        name = report_path.stem
        date_str = name.replace("nightshift_", "")
        table.add_row(date_str, str(report_path))
    
    console.print(table)


@app.command()
def status():
    """Show current nightshift status."""
    from .config import NightshiftConfig
    from .task_queue import TaskQueue
    from .config import get_preferred_models
    from .model_manager import create_default_manager
    
    config = NightshiftConfig()
    
    if not config.db_path.exists():
        console.print("[yellow]No active or previous runs found[/yellow]")
        return
    
    queue = TaskQueue(config)
    stats = queue.get_statistics()
    
    table = Table(title="Task Status")
    table.add_column("Status", style="cyan")
    table.add_column("Count", justify="right")
    
    for status, count in stats.items():
        if status != "total_tokens":
            table.add_row(status.replace("_", " ").title(), str(count))
    
    table.add_row("Total Tokens", f"{stats.get('total_tokens', 0):,}")
    
    console.print(table)
    
    manager = create_default_manager(preferred_models=get_preferred_models())
    model_status = manager.get_status()
    
    model_table = Table(title="Model Status")
    model_table.add_column("Model", style="cyan")
    model_table.add_column("Available", justify="center")
    
    for model, info in model_status.items():
        available = "[green]Yes[/green]" if info["available"] else f"[red]No ({info.get('retry_after_seconds', 0)}s)[/red]"
        model_table.add_row(model, available)
    
    console.print(model_table)
    queue.close()


@app.command()
def clean():
    """Clean up old data and reports."""
    from .config import NightshiftConfig
    import shutil
    
    config = NightshiftConfig()
    
    if typer.confirm("This will delete all nightshift data. Continue?"):
        if config.data_dir.exists():
            shutil.rmtree(config.data_dir)
            console.print("[green]Cleaned up nightshift data[/green]")
        else:
            console.print("[yellow]No data to clean[/yellow]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(7890, "--port", "-p", help="Port to bind"),
):
    """Start the nightshift HTTP API server."""
    console.print(f"[bold green]Starting Nightshift API Server[/bold green]")
    console.print(f"Listening on http://{host}:{port}")
    console.print(f"API docs: http://{host}:{port}/docs")
    console.print()
    
    from .server import run_server
    run_server(host, port)


@app.command()
def diff():
    """Show differential report comparing to last run."""
    from .config import NightshiftConfig
    from .diff_report import DiffReportGenerator
    import webbrowser
    import tempfile
    
    config = NightshiftConfig()
    diff_gen = DiffReportGenerator(config)
    
    html = diff_gen.generate_diff_report()
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
        f.write(html)
        console.print(f"[green]Diff report:[/green] {f.name}")
        webbrowser.open(f"file://{f.name}")


if __name__ == "__main__":
    app()
