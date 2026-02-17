# Contributing To Nightshift

Thanks for contributing.

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

## Branch Naming

- Suggested: `codex/<short-description>` for feature branches.
