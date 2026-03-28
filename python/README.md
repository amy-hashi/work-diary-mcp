# work-diary-mcp (Python)

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for managing a weekly work diary. Built with [FastMCP](https://gofastmcp.com) in Python.

Interact with your diary conversationally via the [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) or [Zed](https://zed.dev). The server writes Markdown files to disk that can be copied directly into Microsoft Loop (or any Markdown-compatible tool).

See the [project changelog](../CHANGELOG.md) for release history and in-progress changes.

---

## Index

- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Tools](#tools)
- [Usage](#usage)
- [Why Python?](#why-python)
- [Features](#features)
- [Supported Status Values](#supported-status-values)
- [Jira Auto-Linking](#jira-auto-linking)
- [Project Structure](#project-structure)
- [Data Format](#data-format)
- [Carry-Forward Behaviour](#carry-forward-behaviour)
- [Testing](#testing)

---

## Quick Start

### 1. Install `uv`

Install `uv` using the instructions for your platform in the official docs:

<https://docs.astral.sh/uv/getting-started/installation/>

This project is intended to work on both **macOS** and **Windows**. The examples below use Unix-style paths where needed; on Windows, use the equivalent local paths and `uv` executable location for your environment.

### 2. Install dependencies

```bash
cd ~/work-diary-mcp/python
uv sync
```

### 3. Register with Claude CLI

Use whatever `uv` executable path is correct for your platform:

```bash
claude mcp add work-diary /path/to/uv \
  --directory $HOME/work-diary-mcp/python run work-diary-mcp
```

### 4. Register with Zed

Add to your Zed `settings.json` (`cmd+,`). This example shows a macOS-style path for `uv`; on Windows, use the path to `uv.exe` or another command that resolves to `uv` in your environment:

```json
{
  "context_servers": {
    "work-diary": {
      "command": "/path/to/uv",
      "args": [
        "--directory",
        "/Users/yourname/work-diary-mcp/python",
        "run",
        "work-diary-mcp"
      ],
      "env": {}
    }
  }
}
```

---

## Configuration

By default, diary files are written to `data/` inside the repository. You can point the server at any directory and configure Jira auto-linking using either environment variables or the settings file.

### Environment variables

#### Data directory

Set `WORK_DIARY_DATA_DIR` to an absolute (or `~`-prefixed) path:

```bash
export WORK_DIARY_DATA_DIR=~/Documents/work-diary
```

To make it permanent, add the export to your shell profile and pass it through to the server in your MCP client config.

**Zed** — add an `env` entry:

```json
{
  "context_servers": {
    "work-diary": {
      "command": "/path/to/uv",
      "args": ["--directory", "/Users/yourname/work-diary-mcp/python", "run", "work-diary-mcp"],
      "env": {
        "WORK_DIARY_DATA_DIR": "/Users/yourname/Documents/work-diary"
      }
    }
  }
}
```

**Claude CLI** — add the env var when registering:

```bash
claude mcp add work-diary /path/to/uv \
  --directory $HOME/work-diary-mcp/python run work-diary-mcp \
  --env WORK_DIARY_DATA_DIR=$HOME/Documents/work-diary
```

On Windows, use Windows-style paths for both the `uv` executable and `WORK_DIARY_DATA_DIR`.

#### Jira auto-linking

You can also configure Jira linkification via environment variables:

- `WORK_DIARY_JIRA_BASE_URL`
- `WORK_DIARY_JIRA_PREFIXES`

Example:

```bash
export WORK_DIARY_JIRA_BASE_URL=https://jira.example.com/browse
export WORK_DIARY_JIRA_PREFIXES=PROJ,INFRA,ENG
```

`WORK_DIARY_JIRA_BASE_URL` must be a non-empty absolute URL with a scheme such as `https://`.

### Settings file

Create a settings file with any combination of the following keys:

- **macOS / Linux:** `~/.config/work-diary/settings.toml`
- **Windows:** `%APPDATA%\work-diary\settings.toml`

```toml
data_dir = "~/Documents/work-diary"
jira_base_url = "https://jira.example.com/browse"
jira_prefixes = ["PROJ", "INFRA", "ENG", "OPS", "SEC", "DATA"]
```

Settings file keys:

- `data_dir` — where diary files and reminder storage should live
- `jira_base_url` — the base browse URL for your Jira instance
- `jira_prefixes` — the list of Jira project key prefixes that should be linkified

`jira_base_url` must be a non-empty absolute URL and include a scheme such as `https://`.

The configured path is expanded automatically and the directory is created on first use.

### Resolution order

#### Data directory
1. `WORK_DIARY_DATA_DIR` environment variable
2. `data_dir` in the platform-native settings file
3. Built-in default: `<repo root>/data`

#### Jira auto-linking
1. `WORK_DIARY_JIRA_BASE_URL` / `WORK_DIARY_JIRA_PREFIXES` environment variables
2. `jira_base_url` / `jira_prefixes` in the platform-native settings file
3. Built-in defaults:
   - `https://jira.example.com/browse`
   - `["PROJ", "INFRA", "ENG", "OPS", "SEC", "DATA"]`

---

## Tools

| Tool | Description |
|------|-------------|
| `update_project_status` | Update or add a project's status, with an optional inline note. Pass `append_note: true` to append to an existing note instead of replacing it. You can also target a specific week with `date`. Existing projects can also be referenced by row number, for example `project 2`. |
| `bulk_update_projects` | Update multiple projects in a single operation — more efficient than calling `update_project_status` repeatedly. You can also target a specific week with `date`. |
| `rename_project` | Rename a project, preserving its status and note. You can also target a specific week with `date`. Existing projects can also be referenced by row number, for example `project 2`. |
| `add_note` | Append a note to the general notes section. You can also target a specific week with `date`. |
| `edit_note` | Replace the content of an existing note by its index number. You can also target a specific week with `date`. |
| `delete_note` | Delete a note by its index number. You can also target a specific week with `date`. |
| `add_reminder` | Add a reminder for the current week or a future week without creating a future diary page. Supports an optional `date` to target a specific week and an optional `due_date` to render before the reminder text. |
| `list_reminders` | List all reminders for the target week. Supports an optional `date` to target a specific week. |
| `complete_reminder` | Mark a reminder as complete for the target week. Supports an optional `date` to target a specific week. |
| `reopen_reminder` | Mark a completed reminder as incomplete for the target week. Supports an optional `date` to target a specific week. |
| `get_diary` | Retrieve the full Markdown diary for the current or any past week. |
| `list_projects` | List all projects and their statuses for the current or any past week. |
| `list_weeks` | List all weeks that have diary entries, sorted oldest to newest. |
| `remove_project` | Remove a project and its note from the target week. You can also target a specific week with `date`. Existing projects can also be referenced by row number, for example `project 2`. |
| `clear_project_note` | Clear the inline note for a project, leaving its status intact. You can also target a specific week with `date`. Existing projects can also be referenced by row number, for example `project 2`. |

---

## Usage

Just talk naturally — your MCP client will call the right tool automatically:

```text
Update Project Phoenix to On Track
Platform Infra is now blocked — waiting on the infra team
Add a note: had a productive all-hands today, big Q3 roadmap updates
Show me this week's diary
What projects am I tracking this week?
Show me my diary from last week
Show me my diary from 2 weeks ago
What weeks do I have diary entries for?
Remove Project Phoenix from this week
Clear the note on Platform Infra
Update [Project Phoenix](https://jira.example.com/PROJ-123) to At Risk with a note: blocked on dependency
Rename Project Phoenix to Phoenix Rewrite
Update all my projects: Phoenix Rewrite is On Track, Platform Infra is Blocked, Auth Service is Done
Append a note to Platform Infra: dependency resolved, unblocked as of Friday
Edit note 2: corrected — the all-hands covered Q3 and Q4 roadmap
Delete note 3
PROJ-1234 is now On Track
Add a note: opened PROJ-1234 and INFRA-5678 to track the rollout
Add a note to last week's diary: followed up on rollout issues
Edit note 2 in last week's diary: corrected the deployment summary
Delete note 1 from 2 weeks ago
Update Stacks on TFE to Blocked in last week's diary
Update project 2 to Done
Clear the note on project 3
Rename project 1 to Phoenix Rewrite
Add a reminder for next week: follow up with the perf testing team
Add a reminder for 2 weeks from now with due date Friday: confirm rollout checklist
List reminders for next week
Complete reminder 1 for this week
Reopen reminder 2 for last week
```

---

## Why Python?

- **No build step** — edit the server code and restart the process; changes take effect immediately
- **Simple dependency management** — `uv` handles environments and dependencies cleanly
- **FastMCP** — plain Python functions become MCP tools with minimal ceremony

---

## Features

- **Project status table** — track projects with a status and an optional inline note per project
- **General notes** — append notes throughout the week
- **Carry-forward** — on the first interaction of each new week, non-completed projects are automatically carried forward from the prior week, while project notes reset for the new week
- **Jira auto-linking** — bare Jira ticket references (for supported prefixes such as `PROJ-1234` or `INFRA-5678`) are automatically converted to Markdown links
- **Markdown links** — use standard Markdown link syntax anywhere: `[text](url)`
- **Relative date support** — target diary weeks with ISO dates and natural language such as `"last week"`, `"next week"`, `"2 weeks ago"`, `"2 weeks from now"`, or `"in 4 weeks"`
- **Previous-week write support** — add notes and update projects in a past week using natural language such as `"add a note to last week's diary"`
- **Project row references** — refer to existing projects by table row using phrases like `"project 2"` when updating, renaming, or clearing project notes
- **Weekly reminders** — store reminders for the current week or future weeks without creating future diary pages, render them with checkboxes, and mark them complete as work is finished
- **Configurable data directory** — store diary files in the repo default location or point the server at a custom directory

---

## Supported Status Values

Well-known statuses are automatically formatted with emoji. Any other string is stored as-is.

| Input | Rendered |
|-------|----------|
| On Track | 🟢 On Track |
| At Risk | 🟡 At Risk |
| Blocked | 🔴 Blocked |
| Done | ✅ Done |
| Complete | ✅ Complete |
| Completed | ✅ Completed |
| In Progress | 🔵 In Progress |
| Not Started | ⚪ Not Started |
| Cancelled | ⛔ Cancelled |
| Canceled | ⛔ Canceled |
| Paused | ⏸️ Paused |

Terminal statuses are used to decide what should not be carried forward into a new week.

---

## Jira Auto-Linking

Bare Jira ticket references are automatically converted to Markdown links whenever text is saved to the diary — in project names, inline notes, and general notes. Already-linked references are never double-linked.

The default Jira configuration is:

- **Base URL:** `https://jira.example.com/browse`
- **Prefixes:** `PROJ`, `INFRA`, `ENG`, `OPS`, `SEC`, `DATA`

You can override these through either:

- environment variables:
  - `WORK_DIARY_JIRA_BASE_URL` — must be a non-empty absolute URL with a scheme such as `https://`
  - `WORK_DIARY_JIRA_PREFIXES` (comma-separated, for example `PROJ,INFRA,ENG`)
- the settings file:
  - `jira_base_url` — must be a non-empty absolute URL with a scheme such as `https://`
  - `jira_prefixes`

Examples:

| You type | Stored as |
|----------|-----------|
| `PROJ-1234` | `[PROJ-1234](https://jira.example.com/browse/PROJ-1234)` |
| `blocked by INFRA-5678` | `blocked by [INFRA-5678](https://jira.example.com/browse/INFRA-5678)` |
| `[PROJ-1234](https://jira.example.com/browse/PROJ-1234)` | unchanged |

Ticket keys are uppercased in generated links. References that do not match a supported prefix are left as-is.

---

## Project Structure

```text
python/
├── README.md
├── pyproject.toml
├── uv.lock
├── tests/
│   ├── __init__.py
│   └── test_diary.py
└── work_diary_mcp/
    ├── __init__.py
    ├── config.py              # Data directory resolution and Jira configuration
    ├── diary.py               # State management, reminders, week helpers, persistence
    ├── jira.py                # Jira ticket auto-linking
    ├── markdown.py            # Markdown renderer
    ├── server.py              # FastMCP server and tool definitions
    └── statuses.py            # Status definitions (emoji map, completion set)
```

---

## Data Format

Each week's diary is stored as two files in the configured data directory, keyed by the Monday of that week.

**`YYYY-MM-DD.json`** — source of truth:

```json
{
  "weekKey": "2026-03-02",
  "projects": {
    "[Project Phoenix](https://jira.example.com/browse/PROJ-123)": "On Track"
  },
  "projectNotes": {
    "[Project Phoenix](https://jira.example.com/browse/PROJ-123)": "A few bugs found; [PROJ-124](https://jira.example.com/browse/PROJ-124) opened to track."
  },
  "notes": [
    {
      "content": "Kickoff meeting with TPM for Platform Infra."
    }
  ]
}
```

**`YYYY-MM-DD.md`** — rendered output:

```markdown
# Work Diary — Week of Mar 2, 2026

## Reminders for this week

- [ ] Due Date: 2026-03-05 Follow up with the perf testing team
- [x] Confirm rollout checklist

## Project Status

| Project | Status | Notes |
|---------|--------|-------|
| [Project Phoenix](https://jira.example.com/browse/PROJ-123) | 🟢 On Track | A few bugs found; [PROJ-124](https://jira.example.com/browse/PROJ-124) opened to track. |

## Notes

- **[1]** Kickoff meeting with TPM for Platform Infra.
```

---

## Carry-Forward Behaviour

On the first interaction of each new week, a fresh diary page is created automatically. Non-terminal projects are copied forward from the most recent prior week so you never start from a blank slate.

If you write to a past week that does not exist yet, the server creates an empty diary page for that week instead of carrying state forward retroactively.

Reminders are stored separately from weekly diary pages, so you can add them for the current week or for future weeks without creating future diary files. When a week is rendered, reminders for that week appear in a `Reminders for this week` section before `Project Status`. If a reminder includes a due date, it is rendered first in the reminder text as `Due Date: <date>`. When reminders change for an existing week, the server refreshes that week's rendered Markdown file without creating diary pages for other weeks.

Carry-forward behavior is currently:

- **Project statuses are carried forward**
- **Project inline notes are not carried forward**
- **General notes are not carried forward**
- **Completed or cancelled projects are not carried forward**

Projects with a terminal status such as **Done**, **Complete**, **Completed**, **Cancelled**, or **Canceled** stay in the week they were finished and will not clutter the new week's diary.

---

## Testing

Run the test suite from `python/`:

```bash
uv run --group dev pytest -v
```
