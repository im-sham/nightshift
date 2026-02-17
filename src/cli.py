import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Nightshift - Overnight autonomous research agent")
console = Console()


@app.command()
def start(
    projects: list[str] = typer.Argument(
        ...,
        help="Project names or paths to analyze (e.g., opsorchestra ghost-sentry)"
    ),
    duration: float = typer.Option(
        8.0,
        "--duration", "-d",
        help="Maximum duration in hours"
    ),
    priority_mode: str = typer.Option(
        "balanced",
        "--priority-mode", "-m",
        help="Task prioritization mode: balanced, security_first, research_heavy, quick_scan",
    ),
):
    """Start a nightshift research run."""
    from .runner import run_nightshift
    
    console.print(f"[bold green]Starting Nightshift[/bold green]")
    console.print(f"Projects: {', '.join(projects)}")
    console.print(f"Max duration: {duration} hours")
    console.print(f"Priority mode: {priority_mode}")
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
    
    manager = create_default_manager()
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
