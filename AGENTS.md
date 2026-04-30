# AGENTS.md

This document gives coding agents and contributors practical guidance for working in `work-diary-mcp`.

## Purpose

`work-diary-mcp` is a Python-based [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for managing a weekly work diary. It supports:

- project status tracking
- general notes
- reminders for current and future weeks
- historical week edits
- Markdown rendering for copy/paste into tools like Microsoft Loop
- configurable Jira auto-linking

The Python implementation lives under `python/`.

---

## Repository layout

- `README.md` — top-level user-facing documentation
- `CHANGELOG.md` — notable changes and release history
- `.github/workflows/` — CI workflows
- `data/` — default diary/reminder storage location (gitignored runtime data)
- `python/README.md` — Python-specific documentation
- `python/pyproject.toml` — package metadata and tooling config
- `python/tests/test_diary.py` — test suite
- `python/work_diary_mcp/` — application code

### Important Python modules

- `config.py`
  - resolves data directory and Jira configuration
  - supports environment variables and settings file configuration
- `diary.py`
  - core state management
  - week-key parsing and normalization
  - reminder storage and locking
  - persistence and carry-forward behavior
- `jira.py`
  - Jira ticket auto-linking
- `markdown.py`
  - Markdown rendering for diary output
- `roles.py`
  - engagement role definitions and normalization
- `server.py`
  - FastMCP server and MCP tool definitions
- `statuses.py`
  - status formatting and completion semantics

---

## Development workflow

### Environment setup

From the repository root:

```bash
cd python
uv sync --group dev
```

### Run tests

```bash
cd python
uv run pytest -v
```

### Run lint and format checks

```bash
cd python
uv run ruff check .
uv run ruff format --check .
```

### Format code

```bash
cd python
uv run ruff format .
```

---

## Coding guidelines

### General
- Prefer small, focused changes.
- Keep behavior changes covered by tests.
- Update documentation when user-facing behavior changes.
- Preserve cross-platform behavior for:
  - macOS
  - Windows
  - Linux/CI environments where relevant

### Python style
- Target Python `3.11+`.
- Follow the existing style in the repo.
- Keep type annotations where practical.
- Prefer explicit, readable code over clever abstractions.
- Reuse existing helpers before introducing new ones.

### State and persistence
- Preserve the invariant that weekly diary files are keyed by the **Monday** of the week.
- Avoid creating future diary pages when working with reminders.
- Be careful around persistence code:
  - `diary.py` includes locking for week state and reminder state
  - avoid introducing unlocked read-modify-write flows

### Reminder behavior
- Reminders are stored separately from week diary JSON.
- Persisted week Markdown should reflect reminders for that week.
- Reminder updates should only refresh the affected week’s rendered Markdown.

### Jira behavior
- Do **not** reintroduce hardcoded organization-specific Jira URLs or prefixes.
- Jira configuration should remain driven by:
  - environment variables
  - settings file values
  - generic built-in defaults

---

## Testing expectations

When changing behavior, add or update tests in `python/tests/test_diary.py`.

Areas with existing regression coverage include:
- week key parsing and normalization
- carry-forward behavior
- historical week writes
- reminder storage and rendering
- Jira linkification
- Windows-specific path and lock behavior
- server-level target-week resolution

### Test hygiene
- Tests should remain isolated and should not touch real user directories or real diary data.
- Be cautious with:
  - `HOME`
  - `USERPROFILE`
  - Windows path simulation
- Keep tests portable across CI platforms.

---

## Documentation expectations

Update docs when changing:
- setup flow
- configuration
- MCP tools
- reminder behavior
- Jira behavior
- supported date formats
- persisted output structure

Relevant docs:
- `README.md`
- `python/README.md`
- `CHANGELOG.md`

### README organization
The READMEs are intentionally structured to keep:
- installation
- configuration
- tools
- usage

near the top, and:
- project structure
- internal/reference material

closer to the bottom.

Maintain that organization when editing docs.

---

## Configuration reference

### Environment variables
- `WORK_DIARY_DATA_DIR`
- `WORK_DIARY_JIRA_BASE_URL`
- `WORK_DIARY_JIRA_PREFIXES`
- `WORK_DIARY_FILE_LOCKS` — opt-in flag (`1`/`true`/`yes`/`on`) that additionally acquires filesystem locks for week and reminder writes. Off by default; in-process `threading.Lock`s are used in the common single-process case.

### Settings file
Platform-native settings file location:
- macOS / Linux: `~/.config/work-diary/settings.toml`
- Windows: `%APPDATA%\work-diary\settings.toml`

Supported settings keys:
- `data_dir`
- `jira_base_url`
- `jira_prefixes`

### Validation expectations
- `jira_base_url` must be a non-empty URL with a scheme such as `https://`
- `jira_prefixes` should be a list of strings
- data directory paths should be expanded and validated safely

---

## CI expectations

Current CI runs:
- lint checks
- pytest on Ubuntu
- pytest on Windows

Do not make changes that silently weaken Windows coverage unless there is a strong reason and the change is documented.

---

## Change management

For user-visible changes:
1. update tests
2. update documentation
3. update `CHANGELOG.md`

Use the `Unreleased` section in the changelog for ongoing work until release.

---

## Good first checks before submitting changes

From `python/`:

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
```

If behavior changed, also review:
- `README.md`
- `python/README.md`
- `CHANGELOG.md`

---

## Notes for future contributors

If you are changing anything related to:
- date parsing
- persisted diary file naming
- reminders
- locking
- Jira linkification
- config resolution

treat it as high-risk and verify both tests and docs carefully.

---

## ⚠️ CRITICAL SECURITY WARNING ⚠️

**THIS REPOSITORY IS PUBLIC ON GITHUB!**

**NEVER, EVER COMMIT:**
- Access tokens, API keys, or credentials of any kind
- Private email addresses or personal information
- AWS credentials, GitHub tokens, or OAuth secrets
- Anything that appears sensitive or private

**ALWAYS:**
- Check for sensitive data before any git commit
- Use `.example` files for configurations that may contain secrets
- Keep actual secrets in `.gitignore`d files like `~/.private-zshrc`
- Sanitize any private information before copying to `.example` files

When modifying configuration files that may contain secrets (for example, personal git configuration):
1. Make changes to the actual configuration or symlinked file
2. If it has a corresponding `.example` file (e.g., `config.example`), copy the non-secret parts of the changes there
3. **SANITIZE any private information** in the `.example` file (replace with placeholders like `AUTHORNAME`, `AUTHOREMAIL`)
4. Verify no secrets are present before committing
