# work-diary-mcp

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for managing a weekly work diary. Built with [FastMCP](https://gofastmcp.com) in Python.

Interact with your diary conversationally via the [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) or [Zed](https://zed.dev). The server writes Markdown files to disk that can be copied directly into Microsoft Loop (or any Markdown-compatible tool).

---

## Features

- **Project status table** — track projects with a status and an optional inline note per project
- **General notes** — append notes throughout the week
- **Carry-forward** — on the first interaction of each new week, non-completed projects are automatically carried forward from the prior week, while project notes reset for the new week
- **Jira auto-linking** — bare Jira ticket references (e.g. `PROJ-1234`) are automatically converted to Markdown links
- **Markdown links** — use standard Markdown link syntax anywhere: `[text](url)`
- **Relative date support** — retrieve past diaries with `"last week"` or `"2 weeks ago"`

---

## Project Structure

```
work-diary-mcp/
├── .gitignore
├── README.md
├── data/                          # Diary files (gitignored) — default location
│   ├── YYYY-MM-DD.json            # Raw state for each week
│   └── YYYY-MM-DD.md              # Rendered Markdown, ready to copy into Loop
└── python/
    ├── README.md                  # Python-specific setup details
    ├── pyproject.toml
    ├── uv.lock
    └── work_diary_mcp/
        ├── config.py              # Data directory resolution (env var / settings file)
        ├── diary.py               # State management, week helpers, public API
        ├── jira.py                # Jira ticket auto-linking
        ├── markdown.py            # Markdown renderer
        ├── server.py              # FastMCP server and tool definitions
        └── statuses.py            # Status definitions (emoji map, completion set)
```

---

## Setup

### Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) — install via Homebrew: `brew install uv`

### Install dependencies

```bash
cd ~/work-diary-mcp/python
uv sync
```

### Register with Zed

Add to your Zed `settings.json` (`cmd+,`):

```json
{
  "context_servers": {
    "work-diary": {
      "command": "/opt/homebrew/bin/uv",
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

```bash
claude mcp add work-diary /opt/homebrew/bin/uv \
  --directory $HOME/work-diary-mcp/python run work-diary-mcp
```

---

## Configuration

By default, diary files are written to `data/` inside the repository. You can
point the server at any directory using either of the methods below.

### Option 1 — Environment variable

Set `WORK_DIARY_DATA_DIR` to an absolute (or `~`-prefixed) path:

```bash
export WORK_DIARY_DATA_DIR=~/Documents/work-diary
```

To make it permanent, add the export to your shell profile and pass it through
to the server in your MCP client config:

**Zed** — add an `env` entry:
```json
{
  "context_servers": {
    "work-diary": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["--directory", "/Users/yourname/work-diary-mcp/python", "run", "work-diary-mcp"],
      "env": { "WORK_DIARY_DATA_DIR": "/Users/yourname/Documents/work-diary" }
    }
  }
}
```

**Claude CLI** — add the env var when registering:
```bash
claude mcp add work-diary /opt/homebrew/bin/uv \
  --directory $HOME/work-diary-mcp/python run work-diary-mcp \
  --env WORK_DIARY_DATA_DIR=$HOME/Documents/work-diary
```

### Option 2 — Settings file

Create `~/.config/work-diary/settings.toml` with a `data_dir` key:

```toml
data_dir = "~/Documents/work-diary"
```

The path is expanded (so `~` works) and created automatically on first use.

### Resolution order

1. `WORK_DIARY_DATA_DIR` environment variable
2. `data_dir` in `~/.config/work-diary/settings.toml`
3. Built-in default: `<repo root>/data`

---

## Tools

| Tool | Description |
|------|-------------|
| `update_project_status` | Update or add a project's status, with an optional inline note. Pass `append_note: true` to append to an existing note instead of replacing it. |
| `bulk_update_projects` | Update multiple projects in a single operation — more efficient than calling `update_project_status` repeatedly. |
| `rename_project` | Rename a project, preserving its status and note. |
| `add_note` | Append a note to the general notes section. |
| `edit_note` | Replace the content of an existing note by its index number. |
| `delete_note` | Delete a note by its index number. |
| `get_diary` | Retrieve the full Markdown diary for the current or any past week. |
| `list_projects` | List all projects and their statuses for the current or any past week. |
| `list_weeks` | List all weeks that have diary entries, sorted oldest to newest. |
| `remove_project` | Remove a project and its note from this week's diary. |
| `clear_project_note` | Clear the inline note for a project, leaving its status intact. |

---

## Usage

Just talk naturally — your MCP client will call the right tool automatically:

```
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
Add a note: opened PROJ-1234 and PROJ-1235 to track the rollout
```

---

## Supported Status Values

Well-known statuses are automatically formatted with emoji. Any other string is stored as-is.

| Input | Rendered |
|-------|----------|
| On Track | 🟢 On Track |
| At Risk | 🟡 At Risk |
| Blocked | 🔴 Blocked |
| Done | ✅ Done |
| Complete / Completed | ✅ Complete |
| In Progress | 🔵 In Progress |
| Not Started | ⚪ Not Started |
| Cancelled / Canceled | ⛔ Cancelled |
| Paused | ⏸️ Paused |

---

## Jira Auto-Linking

Bare Jira ticket references are automatically converted to Markdown links whenever text is saved to the diary — in project names, inline notes, and general notes. Already-linked references are never double-linked.

To configure auto-linking for your Jira instance, update `python/work_diary_mcp/jira.py`:

- **`_KNOWN_PREFIXES`** — the tuple of recognised project key prefixes (e.g. `"PROJ"`, `"INFRA"`)
- **`JIRA_BASE_URL`** — your Jira instance's base browse URL (e.g. `"https://jira.example.com/browse"`)

| You type | Stored as |
|----------|-----------|
| `PROJ-1234` | `[PROJ-1234](https://jira.example.com/browse/PROJ-1234)` |
| `blocked by PROJ-1235` | `blocked by [PROJ-1235](https://jira.example.com/browse/PROJ-1235)` |
| `[PROJ-1234](https://jira.example.com/browse/PROJ-1234)` | unchanged |

Ticket keys are always uppercased in the generated link (e.g. `proj-1234` → `PROJ-1234`). Any prefix that doesn't match a known prefix is left as-is.

---

## Data Format

Each week's diary is stored as two files in `data/`, keyed by the Monday of that week:

**`data/2026-03-02.json`** — source of truth:
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

**`data/2026-03-02.md`** — rendered output:
```markdown
# Work Diary — Week of Mar 2, 2026

## Project Status

| Project | Status | Notes |
|---------|--------|-------|
| [Project Phoenix](https://jira.example.com/browse/PROJ-123) | 🟢 On Track | A few bugs found; [PROJ-124](https://jira.example.com/browse/PROJ-124) opened to track. |

## Notes

- **[1]** Kickoff meeting with TPM for Platform Infra.
```

---

## Data Location

Diary files are stored in the configured data directory (see [Configuration](#configuration) above).
Each week is represented by two files keyed on the Monday of that week:

- `YYYY-MM-DD.json` — source of truth (raw state)
- `YYYY-MM-DD.md` — rendered Markdown, ready to copy into Microsoft Loop

---

## Carry-Forward Behaviour

On the first interaction of each new week (Monday onward), a fresh diary page is created automatically. Projects and their inline notes are copied forward from the most recent prior week — so you never start from a blank slate. Status values carry forward unchanged; update them as the week progresses.

Projects with a terminal status (**Done**, **Complete**, **Completed**, **Cancelled**, **Canceled**) are **not** carried forward. Finished work stays in the week it was completed and won't clutter the new week's diary.