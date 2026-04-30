# work-diary-mcp

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for managing a weekly work diary. Built with [FastMCP](https://gofastmcp.com) in Python.

Interact with your diary conversationally via the [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) or [Zed](https://zed.dev). The server writes Markdown files to disk that can be copied directly into Microsoft Loop (or any Markdown-compatible tool).

For a running summary of changes, see [CHANGELOG.md](CHANGELOG.md).

---

## Index

- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Tools](#tools)
- [Usage](#usage)
- [Features](#features)
- [Supported Status Values](#supported-status-values)
- [Supported Role Values](#supported-role-values)
- [Jira Auto-Linking](#jira-auto-linking)
- [Data Format](#data-format)
- [Data Location](#data-location)
- [Carry-Forward Behaviour](#carry-forward-behaviour)
- [Project Structure](#project-structure)
- [Testing](#testing)

---

## Quick Start

### Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) — install it using the instructions for your platform in the official docs: <https://docs.astral.sh/uv/getting-started/installation/>

This project is intended to work on both **macOS** and **Windows**. The examples below use Unix-style paths where needed; on Windows, use the equivalent local paths and `uv` executable location for your environment.

### Install dependencies

```bash
cd ~/work-diary-mcp/python
uv sync
```

### Register with Zed

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

### Register with Claude CLI

Use whatever `uv` executable path is correct for your platform:

```bash
claude mcp add work-diary /path/to/uv \
  --directory $HOME/work-diary-mcp/python run work-diary-mcp
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

`WORK_DIARY_JIRA_BASE_URL` must be a non-empty URL and must include a scheme such as `https://`.

#### Multi-process safety

By default, `work-diary-mcp` uses in-process `threading.Lock`s to coordinate writes. This is safe for the common case where a single MCP server process is the only writer to the data directory, and avoids per-call `flock` / `msvcrt.locking` overhead.

If you run multiple processes that write to the same data directory, set `WORK_DIARY_FILE_LOCKS=1` to additionally acquire filesystem locks for week and reminder writes:

```bash
export WORK_DIARY_FILE_LOCKS=1
```

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

`jira_base_url` must be a non-empty URL and must include a scheme such as `https://`.

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
| `update_project_status` | Update or add a project's status, with an optional inline note and an optional role. Pass `append_note: true` to append to an existing note instead of replacing it. For `role`, pass `null` (or omit it) to leave any existing role unchanged, an empty string to clear it, or any accepted role value to set it. Supports an optional `date` to target a specific week. Existing projects can also be referenced by row number, for example `project 2`. Ambiguous row references raise an error, `project 0` is always invalid, and out-of-range positive references are treated as literal project names rather than raising. |
| `bulk_update_projects` | Update multiple projects in a single operation — more efficient than calling `update_project_status` repeatedly. Each entry may optionally include a `role`, with the same `null`/`""`/value semantics as `update_project_status`. Supports an optional `date` to target a specific week. Existing projects can also be referenced by row number, for example `project 2`. Ambiguous row references raise an error, `project 0` is always invalid, and out-of-range positive references are treated as literal project names rather than raising. |
| `set_project_role` | Set or clear the role for an existing project. Accepts canonical role names (`Sponsor`, `Guide`, `Catcher`, `Advisor`, `Catalyst`, `Participant`), emoji shortcodes (`:rocket:`, `:world_map:`, `:fire_extinguisher:`, `:compass:`, `:test_tube:`, `:raising_hand:`), bare emoji, or already-formatted display values. Pass an empty string to clear the role. Supports an optional `date` to target a specific week. |
| `rename_project` | Rename a project, preserving its status and note. Supports an optional `date` to target a specific week. Existing projects can also be referenced by row number, for example `project 2`. Ambiguous row references raise an error, `project 0` is always invalid, and row references must be in range for rename operations. |
| `add_note` | Append a note to the general notes section. Supports an optional `date` to target a specific week. |
| `edit_note` | Replace the content of an existing note by its index number. Supports an optional `date` to target a specific week. |
| `delete_note` | Delete a note by its index number. Supports an optional `date` to target a specific week. |
| `add_reminder` | Add a reminder for the current or a future week without creating a future diary page. Supports an optional `due_date` and `date`. |
| `list_reminders` | List reminders for the target week, including checkbox state and any due date. |
| `complete_reminder` | Mark a reminder as completed for the target week. Supports an optional `date`. |
| `reopen_reminder` | Mark a completed reminder as incomplete for the target week. Supports an optional `date`. |
| `get_diary` | Retrieve the full Markdown diary for the current or any past week. |
| `list_projects` | List all projects and their statuses for the current or any past week. |
| `list_weeks` | List all weeks that have diary entries, sorted oldest to newest. |
| `remove_project` | Remove a project and its note from the target week. Supports an optional `date` to target a specific week. Existing projects can also be referenced by row number, for example `project 2`. Ambiguous row references raise an error, `project 0` is always invalid, and row references must be in range for removal. |
| `clear_project_note` | Clear the inline note for a project, leaving its status intact. Supports an optional `date` to target a specific week. Existing projects can also be referenced by row number, for example `project 2`. Ambiguous row references raise an error, `project 0` is always invalid, and row references must be in range for note clearing. |

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
Add a note to last week's diary: wrapped up the migration checklist
Edit note 2 in last week's diary: corrected the rollout status
Delete note 1 from 2 weeks ago
Update Stacks on TFE to Blocked in last week's diary with a note: waiting on dependency
Update project 2 to Done
Clear the note on project 3
Rename project 1 to Phoenix Rewrite
Add a reminder for next week: follow up with the perf team
Add a reminder for next week with due date Friday: confirm rollout checklist
Add a reminder in 4 weeks: prepare rollout notes
List reminders for next week
Complete reminder 1 for next week
Reopen reminder 1 for next week
```

---

## Features

- **Project status table** — track projects with a status, an optional inline note, and an optional engagement role per project
- **Engagement roles** — tag each project with a Principal Engineer–style engagement role (Sponsor, Guide, Catcher, Advisor, Catalyst, Participant) rendered with emoji in a dedicated `Role` column. Roles are carried forward week-over-week alongside the project itself.
- **General notes** — append notes throughout the week
- **Carry-forward** — on the first interaction of each new week, non-completed projects are automatically carried forward from the prior week, while project notes reset for the new week
- **Jira auto-linking** — bare Jira ticket references (for supported prefixes such as `PROJ-1234` or `INFRA-5678`) are automatically converted to Markdown links
- **Markdown links** — use standard Markdown link syntax anywhere: `[text](url)`
- **Relative date support** — target weeks with ISO dates and natural language such as `"last week"`, `"next week"`, `"2 weeks ago"`, `"2 weeks from now"`, or `"in 4 weeks"`
- **Previous-week write support** — add notes and update projects in a past week by specifying a date such as `"last week"` or `"2026-03-02"`
- **Project row references** — refer to existing projects by table row using phrases like `"project 2"` when updating, bulk updating, renaming, removing, or clearing project notes. If a reference like `"project 2"` could also mean a literal project named `Project 2`, the server raises an ambiguity error instead of guessing. `project 0` is always invalid, even if a literal project with that name exists. Out-of-range positive references are treated as literal project names.
- **Reminders** — store reminders for the current or future weeks without creating future diary pages, render them in a dedicated section, and mark them complete with checkboxes
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
| Shipped | 🚀 Shipped |
| GA | 🚀 GA |
| In Planning | 💡 In Planning |

Terminal statuses are used to decide what should not be carried forward into a new week.

---

## Supported Role Values

Project roles are inspired by the Principal Engineer role framework. Each project may optionally have a role assigned alongside its status; the role is rendered in a dedicated `Role` column in the diary's project table.

| Input | Rendered |
|-------|----------|
| Sponsor / `:rocket:` / 🚀 | 🚀 Sponsor |
| Guide / `:world_map:` / 🗺️ | 🗺️ Guide |
| Catcher / `:fire_extinguisher:` / 🧯 | 🧯 Catcher |
| Advisor / `:compass:` / 🧭 | 🧭 Advisor |
| Catalyst / `:test_tube:` / 🧪 | 🧪 Catalyst |
| Participant / `:raising_hand:` / 🙋 | 🙋 Participant |

Roles are case-insensitive on input and accept canonical names, emoji shortcodes, bare emoji, or already-formatted display values. Pass an empty string to clear a previously-set role. Unknown values are stored as-is so callers can use arbitrary role labels if they want to.

---

## Jira Auto-Linking

Bare Jira ticket references are automatically converted to Markdown links whenever text is saved to the diary — in project names, inline notes, and general notes. Already-linked references are never double-linked.

The default Jira configuration is:

- **Base URL:** `https://jira.example.com/browse`
- **Prefixes:** `PROJ`, `INFRA`, `ENG`, `OPS`, `SEC`, `DATA`

You can override these through either:
- environment variables:
  - `WORK_DIARY_JIRA_BASE_URL`
  - `WORK_DIARY_JIRA_PREFIXES` (comma-separated, for example `PROJ,INFRA,ENG`)
- the settings file:
  - `jira_base_url`
  - `jira_prefixes`

Examples:

| You type | Stored as |
|----------|-----------|
| `PROJ-1234` | `[PROJ-1234](https://jira.example.com/browse/PROJ-1234)` |
| `blocked by INFRA-5678` | `blocked by [INFRA-5678](https://jira.example.com/browse/INFRA-5678)` |
| `[PROJ-1234](https://jira.example.com/browse/PROJ-1234)` | unchanged |

Ticket keys are uppercased in generated links. References that do not match a supported prefix are left as-is.

`WORK_DIARY_JIRA_BASE_URL` / `jira_base_url` must be a non-empty URL and must include a scheme such as `https://`.

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
  "projectRoles": {
    "[Project Phoenix](https://jira.example.com/browse/PROJ-123)": "🚀 Sponsor"
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

- [ ] Due Date: 2026-03-06 Follow up with the perf team
- [x] Confirm rollout checklist

## Project Status

| Project | Role | Status | Notes |
|---------|------|--------|-------|
| [Project Phoenix](https://jira.example.com/browse/PROJ-123) | 🚀 Sponsor | 🟢 On Track | A few bugs found; [PROJ-124](https://jira.example.com/browse/PROJ-124) opened to track. |

## Notes

- **[1]** Kickoff meeting with TPM for Platform Infra.
```

---

## Data Location

Diary files are stored in the configured data directory described in [Configuration](#configuration).

Each week is represented by two files keyed on the Monday of that week:

- `YYYY-MM-DD.json` — source of truth (raw state)
- `YYYY-MM-DD.md` — rendered Markdown, ready to copy into Microsoft Loop

Reminders are stored separately in:

- `reminders.json` — source of truth for reminders across current and future weeks

Write operations default to the current week, but can also target a specific week using a relative date or ISO date, including `"last week"`, `"next week"`, `"N weeks ago"`, `"N weeks from now"`, `"in N weeks"`, or values such as `"2026-03-02"`. If a past week does not yet exist, the server creates an empty diary page for that week instead of carrying forward state. Future reminders do not create future diary pages.

---

## Carry-Forward Behaviour

On the first interaction of each new week, a fresh diary page is created automatically. Non-terminal projects are copied forward from the most recent prior week so you never start from a blank slate.

Carry-forward behavior is currently:

- **Project statuses are carried forward**
- **Project roles are carried forward**
- **Project inline notes are not carried forward**
- **General notes are not carried forward**
- **Completed or cancelled projects are not carried forward**
- **Reminders for that week are rendered in the new diary page without creating future diary pages ahead of time**
- **When reminders change for an existing week, that week's persisted Markdown is regenerated**

Projects with a terminal status such as **Done**, **Complete**, **Completed**, **Cancelled**, **Canceled**, **Shipped**, or **GA** stay in the week they were finished and will not clutter the new week's diary.

---

## Project Structure

```text
work-diary-mcp/
├── .gitignore
├── README.md
├── CHANGELOG.md
├── data/                          # Diary files (gitignored) — default location
│   ├── YYYY-MM-DD.json            # Raw state for each week
│   └── YYYY-MM-DD.md              # Rendered Markdown, ready to copy into Loop
└── python/
    ├── README.md                  # Python-specific setup details
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
        ├── roles.py               # Engagement role definitions and normalization
        ├── server.py              # FastMCP server and tool definitions
        └── statuses.py            # Status definitions (emoji map, completion set)
```

---

## Testing

From `python/`:

```bash
uv run --group dev pytest -v
```
