from pathlib import Path
from datetime import datetime
from typing import Optional
from jinja2 import Template
import webbrowser
import os

from .models import NightshiftReport, Finding, FindingSeverity, ProjectReport


REPORT_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nightshift Report - {{ report.started_at.strftime('%Y-%m-%d') }}</title>
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-tertiary: #21262d;
            --text-primary: #c9d1d9;
            --text-secondary: #8b949e;
            --border-color: #30363d;
            --critical: #f85149;
            --high: #db6d28;
            --medium: #d29922;
            --low: #3fb950;
            --info: #58a6ff;
            --accent: #238636;
        }
        
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 2rem;
        }
        
        .container { max-width: 1200px; margin: 0 auto; }
        
        header {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 2rem;
            margin-bottom: 2rem;
        }
        
        h1 { font-size: 2rem; margin-bottom: 0.5rem; }
        h2 { font-size: 1.5rem; margin-bottom: 1rem; color: var(--text-primary); }
        h3 { font-size: 1.2rem; margin-bottom: 0.75rem; }
        
        .meta { color: var(--text-secondary); font-size: 0.9rem; }
        .meta span { margin-right: 2rem; }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-top: 1.5rem;
        }
        
        .stat-card {
            background: var(--bg-tertiary);
            border-radius: 6px;
            padding: 1rem;
            text-align: center;
        }
        
        .stat-value { font-size: 2rem; font-weight: bold; }
        .stat-label { color: var(--text-secondary); font-size: 0.85rem; }
        
        .section {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        
        .severity-badge {
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .severity-critical { background: var(--critical); color: white; }
        .severity-high { background: var(--high); color: white; }
        .severity-medium { background: var(--medium); color: black; }
        .severity-low { background: var(--low); color: black; }
        .severity-info { background: var(--info); color: white; }
        
        .finding {
            background: var(--bg-tertiary);
            border-left: 4px solid var(--border-color);
            border-radius: 0 6px 6px 0;
            padding: 1rem;
            margin-bottom: 1rem;
        }
        
        .finding.critical { border-left-color: var(--critical); }
        .finding.high { border-left-color: var(--high); }
        .finding.medium { border-left-color: var(--medium); }
        .finding.low { border-left-color: var(--low); }
        .finding.info { border-left-color: var(--info); }
        
        .finding-header {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 0.5rem;
        }
        
        .finding-title { font-weight: 600; }
        .finding-location { color: var(--text-secondary); font-size: 0.85rem; font-family: monospace; }
        .finding-description { margin: 0.75rem 0; }
        .finding-recommendation { 
            background: var(--bg-primary);
            padding: 0.75rem;
            border-radius: 4px;
            margin-top: 0.75rem;
            font-size: 0.9rem;
        }
        .finding-recommendation strong { color: var(--accent); }
        
        details { margin-bottom: 0.5rem; }
        summary {
            cursor: pointer;
            padding: 0.75rem;
            background: var(--bg-tertiary);
            border-radius: 6px;
            font-weight: 500;
        }
        summary:hover { background: var(--border-color); }
        details[open] summary { margin-bottom: 1rem; }
        
        .project-stats {
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }
        
        .count-badge {
            padding: 0.3rem 0.8rem;
            border-radius: 4px;
            font-size: 0.85rem;
        }
        
        footer {
            text-align: center;
            color: var(--text-secondary);
            padding: 2rem;
            font-size: 0.85rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Nightshift Report</h1>
            <p class="meta">
                <span>Started: {{ report.started_at.strftime('%Y-%m-%d %H:%M') }}</span>
                {% if report.completed_at %}
                <span>Duration: {{ "%.1f"|format(report.duration_minutes) }} minutes</span>
                {% endif %}
                <span>Projects: {{ report.projects|length }}</span>
            </p>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value">{{ report.completed_tasks }}</div>
                    <div class="stat-label">Tasks Completed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ report.all_findings|length }}</div>
                    <div class="stat-label">Findings</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ critical_count }}</div>
                    <div class="stat-label" style="color: var(--critical)">Critical</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ high_count }}</div>
                    <div class="stat-label" style="color: var(--high)">High</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ "{:,}".format(report.total_tokens) }}</div>
                    <div class="stat-label">Tokens Used</div>
                </div>
            </div>
        </header>
        
        {% if executive_summary %}
        <section class="section">
            <h2>Executive Summary</h2>
            <p>{{ executive_summary }}</p>
        </section>
        {% endif %}
        
        {% for project in report.projects %}
        <section class="section">
            <h2>{{ project.name }}</h2>
            <p class="meta" style="margin-bottom: 1rem;">{{ project.path }}</p>
            
            <div class="project-stats">
                {% if project.critical_count > 0 %}
                <span class="count-badge severity-critical">{{ project.critical_count }} Critical</span>
                {% endif %}
                {% if project.high_count > 0 %}
                <span class="count-badge severity-high">{{ project.high_count }} High</span>
                {% endif %}
                {% if project.medium_count > 0 %}
                <span class="count-badge severity-medium">{{ project.medium_count }} Medium</span>
                {% endif %}
            </div>
            
            {% set critical_findings = project.findings|selectattr('severity.value', 'equalto', 'critical')|list %}
            {% if critical_findings %}
            <details open>
                <summary>Critical Findings ({{ critical_findings|length }})</summary>
                {% for finding in critical_findings %}
                <div class="finding critical">
                    <div class="finding-header">
                        <span class="severity-badge severity-critical">Critical</span>
                        <span class="finding-title">{{ finding.title }}</span>
                    </div>
                    {% if finding.location %}
                    <div class="finding-location">{{ finding.location }}</div>
                    {% endif %}
                    <div class="finding-description">{{ finding.description }}</div>
                    {% if finding.recommendation %}
                    <div class="finding-recommendation">
                        <strong>Recommendation:</strong> {{ finding.recommendation }}
                    </div>
                    {% endif %}
                </div>
                {% endfor %}
            </details>
            {% endif %}
            
            {% set high_findings = project.findings|selectattr('severity.value', 'equalto', 'high')|list %}
            {% if high_findings %}
            <details>
                <summary>High Priority Findings ({{ high_findings|length }})</summary>
                {% for finding in high_findings %}
                <div class="finding high">
                    <div class="finding-header">
                        <span class="severity-badge severity-high">High</span>
                        <span class="finding-title">{{ finding.title }}</span>
                    </div>
                    {% if finding.location %}
                    <div class="finding-location">{{ finding.location }}</div>
                    {% endif %}
                    <div class="finding-description">{{ finding.description }}</div>
                    {% if finding.recommendation %}
                    <div class="finding-recommendation">
                        <strong>Recommendation:</strong> {{ finding.recommendation }}
                    </div>
                    {% endif %}
                </div>
                {% endfor %}
            </details>
            {% endif %}
            
            {% set medium_findings = project.findings|selectattr('severity.value', 'equalto', 'medium')|list %}
            {% if medium_findings %}
            <details>
                <summary>Medium Priority Findings ({{ medium_findings|length }})</summary>
                {% for finding in medium_findings %}
                <div class="finding medium">
                    <div class="finding-header">
                        <span class="severity-badge severity-medium">Medium</span>
                        <span class="finding-title">{{ finding.title }}</span>
                    </div>
                    {% if finding.location %}
                    <div class="finding-location">{{ finding.location }}</div>
                    {% endif %}
                    <div class="finding-description">{{ finding.description }}</div>
                    {% if finding.recommendation %}
                    <div class="finding-recommendation">
                        <strong>Recommendation:</strong> {{ finding.recommendation }}
                    </div>
                    {% endif %}
                </div>
                {% endfor %}
            </details>
            {% endif %}
            
            {% set low_findings = project.findings|selectattr('severity.value', 'equalto', 'low')|list + project.findings|selectattr('severity.value', 'equalto', 'info')|list %}
            {% if low_findings %}
            <details>
                <summary>Low Priority / Info ({{ low_findings|length }})</summary>
                {% for finding in low_findings %}
                <div class="finding {{ finding.severity.value }}">
                    <div class="finding-header">
                        <span class="severity-badge severity-{{ finding.severity.value }}">{{ finding.severity.value }}</span>
                        <span class="finding-title">{{ finding.title }}</span>
                    </div>
                    {% if finding.location %}
                    <div class="finding-location">{{ finding.location }}</div>
                    {% endif %}
                    <div class="finding-description">{{ finding.description }}</div>
                    {% if finding.recommendation %}
                    <div class="finding-recommendation">
                        <strong>Recommendation:</strong> {{ finding.recommendation }}
                    </div>
                    {% endif %}
                </div>
                {% endfor %}
            </details>
            {% endif %}
        </section>
        {% endfor %}
        
        {% if report.tool_research_findings %}
        <section class="section">
            <h2>Tool Stack Research</h2>
            {% for finding in report.tool_research_findings %}
            <div class="finding {{ finding.severity.value }}">
                <div class="finding-header">
                    <span class="severity-badge severity-{{ finding.severity.value }}">{{ finding.severity.value }}</span>
                    <span class="finding-title">{{ finding.title }}</span>
                </div>
                <div class="finding-description">{{ finding.description }}</div>
                {% if finding.recommendation %}
                <div class="finding-recommendation">
                    <strong>Recommendation:</strong> {{ finding.recommendation }}
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </section>
        {% endif %}
        
        <footer>
            <p>Generated by Nightshift v0.1.0</p>
            <p>Models used: {{ report.models_used|join(', ') }}</p>
        </footer>
    </div>
</body>
</html>
"""


class ReportGenerator:
    def __init__(self, reports_dir: Path):
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, report: NightshiftReport, open_browser: bool = True) -> Path:
        template = Template(REPORT_TEMPLATE)
        
        critical_count = sum(
            1 for f in report.all_findings 
            if f.severity == FindingSeverity.CRITICAL
        )
        high_count = sum(
            1 for f in report.all_findings 
            if f.severity == FindingSeverity.HIGH
        )
        
        executive_summary = self._generate_executive_summary(report, critical_count, high_count)
        
        html = template.render(
            report=report,
            critical_count=critical_count,
            high_count=high_count,
            executive_summary=executive_summary,
        )
        
        filename = f"nightshift_{report.started_at.strftime('%Y%m%d_%H%M%S')}.html"
        report_path = self.reports_dir / filename
        
        report_path.write_text(html)
        
        latest_link = self.reports_dir / "latest.html"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(report_path.name)
        
        if open_browser:
            webbrowser.open(f"file://{report_path}")
        
        return report_path

    def _generate_executive_summary(
        self, 
        report: NightshiftReport, 
        critical_count: int, 
        high_count: int
    ) -> str:
        total_findings = len(report.all_findings)
        project_names = ", ".join(p.name for p in report.projects)
        
        if critical_count > 0:
            urgency = f"Found {critical_count} critical issue(s) requiring immediate attention."
        elif high_count > 0:
            urgency = f"Found {high_count} high-priority issue(s) to address soon."
        else:
            urgency = "No critical or high-priority issues found."
        
        return (
            f"Analyzed {len(report.projects)} project(s) ({project_names}) over "
            f"{report.duration_minutes:.0f} minutes. Completed {report.completed_tasks} tasks "
            f"and identified {total_findings} finding(s). {urgency}"
        )

    def get_latest_report(self) -> Optional[Path]:
        latest_link = self.reports_dir / "latest.html"
        if latest_link.exists():
            return latest_link.resolve()
        return None

    def open_latest_report(self) -> bool:
        report_path = self.get_latest_report()
        if report_path and report_path.exists():
            webbrowser.open(f"file://{report_path}")
            return True
        return False

    def list_reports(self) -> list[Path]:
        return sorted(
            self.reports_dir.glob("nightshift_*.html"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
