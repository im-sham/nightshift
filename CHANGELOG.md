# Changelog

All notable changes to this project are documented in this file.

## [0.2.0] - 2026-02-17

### Added
- `nightshift start --dry-run` to validate configuration and preview task plans without executing OpenCode agents.
- CI smoke workflow for pull requests:
  - `nightshift init --force --no-add-current-project`
  - `nightshift doctor`
  - `nightshift start . --duration 0.1 --priority-mode quick_scan --dry-run`
- Onboarding visuals and a guided "First 10 Minutes" section in the README.

### Changed
- Improved onboarding documentation to use portable project references and explicit setup validation steps.

## [0.1.0] - 2026-01-06

### Added
- Initial Nightshift release with OpenCode-integrated autonomous codebase research, dashboard, and plugin.
