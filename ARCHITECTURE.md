# Architecture

Nightshift has three primary layers:

1. `src/cli.py`: local command interface (`nightshift ...`).
2. `src/server.py`: FastAPI server and dashboard/API bridge.
3. `src/runner.py` + `src/task_queue.py`: execution loop and persistence.

## Runtime Flow

1. A run is started via CLI (`nightshift start ...`) or API (`POST /start`).
2. `NightshiftRunner` creates a run in sqlite and generates task rows.
3. Tasks are prioritized (`SmartPrioritizer`) and executed in order.
4. Agent calls are sent through `OpencodeAgentClient`.
5. Findings/errors are persisted in sqlite and rendered into reports.
6. Report and diff artifacts are written under `~/.nightshift/reports`.

## Persistence Model

- Database: `~/.nightshift/nightshift.db` (or `NIGHTSHIFT_DATA_DIR` override).
- Core tables:
  - `runs`
  - `tasks` (scoped by `run_id`)
  - `findings`

Run scoping is important: status, reports, and diffs should query by run context to avoid cross-run leakage.

## Configuration Sources

Order of precedence:

1. Explicit command/API arguments
2. Environment variables
3. `config.toml` (`~/.nightshift/config.toml` by default)
4. Built-in defaults

Key config behavior is implemented in `src/config.py`.

## Model Selection

`src/model_manager.py` resolves the failover chain by:

1. Taking configured preferred models.
2. Discovering currently available OpenCode models (`opencode models`).
3. Keeping preferred models that exist.
4. Falling back to a ranked discovered chain when needed.

## Frontend

`src/dashboard.html` is a static UI served from `/` by FastAPI.
It polls `/status`, `/models`, `/reports`, and `/schedules`.
