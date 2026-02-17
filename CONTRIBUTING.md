# Contributing To Nightshift

Thanks for contributing.

## Maintenance Mode Expectations

Nightshift is in maintenance mode as of `v0.2.0` (February 17, 2026).

- Contributions are welcome, especially bug fixes, compatibility fixes, and documentation improvements.
- Maintainer review is best-effort and may be delayed.
- There is no guaranteed merge timeline or support SLA.

## Local Setup

```bash
git clone <your-fork-or-upstream-url>
cd nightshift
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
cd plugin && bun install && cd ..
```

## Recommended First Run

```bash
nightshift init
nightshift doctor
```

## Development Commands

```bash
python -m pytest -q
python -m compileall -q src tests
cd plugin && bun run typecheck
```

## Pull Requests

- Keep PRs focused and small when possible.
- Include validation notes (tests/checks run).
- Update docs when behavior or interfaces change.
- Prefer portable paths and avoid user-specific absolute paths.
- Include compatibility context when relevant (OpenCode CLI behavior changes, model command changes, etc.).

## Branch Naming

- Suggested: `codex/<short-description>` for feature branches.
