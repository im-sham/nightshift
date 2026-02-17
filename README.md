# 🌙 Nightshift

Nightshift is an overnight autonomous research agent designed for **OpenCode**. It performs deep analysis of codebases while you sleep, providing comprehensive audits, enhancement recommendations, and research reports by the time you start your next day.

[![npm version](https://img.shields.io/npm/v/nightshift-plugin.svg)](https://www.npmjs.com/package/nightshift-plugin)
[![Python version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Features

- **Autonomous Research**: Deep dives into codebases without manual intervention.
- **Multi-Model Failover**: Automatically discovers available OpenCode models and builds a resilient fallback chain.
- **Comprehensive Reports**: Generates detailed HTML research reports and differential reports comparing changes between runs.
- **OpenCode Integration**: A dedicated plugin that lets you control Nightshift directly from your editor.
- **Smart Scheduling**: Built-in support for daily research tasks using cron or macOS launchd.
- **GitHub Integration**: Automatically creates issues for critical findings.
- **Notifications**: Real-time alerts via Slack or custom webhooks.
- **Web Dashboard**: Interactive dashboard for monitoring runs and viewing findings.
- **Setup UX**: Built-in `nightshift init` and `nightshift doctor` commands for first-run setup and troubleshooting.

## Installation

### 1. Python Package

Install the core engine and CLI:

```bash
cd /path/to/nightshift
pip install -e .
```

### 2. OpenCode Plugin

Install the plugin dependencies:

```bash
cd /path/to/nightshift/plugin
bun install
```

To load the plugin in OpenCode, point your plugin configuration to the `plugin/index.ts` file or the compiled output.

## Quick Start

1. **Initialize local config**:
   ```bash
   nightshift init
   ```

2. **Validate setup**:
   ```bash
   nightshift doctor
   ```

3. **Start the API Server**:
   ```bash
   nightshift serve
   ```

4. **Run a Research Task**:
   ```bash
   nightshift start opsorchestra --duration 8.0
   ```

5. **View the Report**:
   ```bash
   nightshift report
   ```

## CLI Usage

The `nightshift` command provides several subcommands:

- `start [PROJECTS]...`: Start a research run on specified projects or paths.
- `init`: Create a starter `config.toml` in your Nightshift data directory.
- `doctor`: Validate OpenCode/GitHub/config/dependency setup and show fix hints.
- `serve`: Start the HTTP API server (default port: 7890).
- `status`: Show current run status and model availability.
- `report`: Open the latest research report in your browser.
- `diff`: Generate and open a differential report comparing to the previous run.
- `list`: List all historical reports.
- `clean`: Delete old data and reports.

## Web Dashboard

Once the server is running (`nightshift serve`), you can access the interactive dashboard at:
http://127.0.0.1:7890/

The dashboard allows you to:
- Monitor real-time task progress.
- View live findings and model performance.
- Manage scheduled runs.

## API Reference

Nightshift exposes a REST API on port 7890.

### Start a Run
```bash
curl -X POST http://127.0.0.1:7890/start \
     -H "Content-Type: application/json" \
     -d '{
       "projects": ["opsorchestra"],
       "duration_hours": 8.0,
       "create_github_issues": true,
       "priority_mode": "balanced"
     }'
```

### Check Status
```bash
curl http://127.0.0.1:7890/status
```

### Other Endpoints
- `GET /reports`: List all reports.
- `GET /report/latest`: View the latest HTML report.
- `GET /report/diff`: View the differential report.
- `GET /models`: Check model availability and rate limits.
- `POST /stop`: Stop the current run.

## Configuration

Nightshift stores its data in `~/.nightshift`.

### Config File

Nightshift reads optional user config from:

- `~/.nightshift/config.toml`
- or `NIGHTSHIFT_CONFIG_FILE` if set

Create a starter config with:

```bash
nightshift init
```

Example:

```toml
[defaults]
duration_hours = 8.0
priority_mode = "balanced"
open_report_in_browser = true

[projects]
backend = "/path/to/backend"
frontend = "/path/to/frontend"

[models]
preferred = ["openai/gpt-5.2", "google/antigravity-gemini-3-pro-high"]
```

### Environment Variables
- `NIGHTSHIFT_DATA_DIR`: Override the default data directory.
- `NIGHTSHIFT_CONFIG_FILE`: Override the default config path.
- `NIGHTSHIFT_PROJECT_OPSORCHESTRA`: Override default path for the `opsorchestra` alias.
- `NIGHTSHIFT_PROJECT_GHOST_SENTRY`: Override default path for the `ghost-sentry` alias.
- `SLACK_WEBHOOK_URL`: Default webhook for notifications.

See `.env.example` for a complete starter environment file.

### Model Selection

Nightshift tries to:
1. Use preferred models from `config.toml` (if set).
2. Keep only models available in your current OpenCode environment.
3. Auto-rank discovered models when preferred models are unavailable.

## Architecture

Nightshift consists of three main components:
1. **Core Engine (Python)**: Handles the task queue, model management, and research logic.
2. **API Server (FastAPI)**: Provides a bridge between the core engine and external tools.
3. **OpenCode Plugin (TypeScript)**: Exposes research tools directly within the developer environment.

For deeper implementation details, see `ARCHITECTURE.md`.

## Contributing

Forks and external contributions are welcome.
See `CONTRIBUTING.md` for local setup, dev commands, and PR expectations.

---
Built for autonomous engineering.
