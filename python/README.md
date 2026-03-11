# work-diary-mcp (Python)

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for managing a weekly work diary. Built with [FastMCP](https://gofastmcp.com) in Python.

Interact with your diary conversationally via the [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) or [Zed](https://zed.dev). The server writes Markdown files to disk that can be copied directly into Microsoft Loop (or any Markdown-compatible tool).

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
- **Jira auto-linking** — bare Jira ticket references (for supported prefixes such as `TF-34398` or `RDPR-1234`) are automatically converted to Markdown links
- **Markdown links** — use standard Markdown link syntax anywhere: `[text](url)`
- **Relative date support** — retrieve past diaries with `"last week"` or `"2 weeks ago"`
- **Configurable data directory** — store diary files in the repo default location or point the server at a custom directory

---

## Setup

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

By default, diary files are written to `data/` inside the repository. You can point the server at any directory using either of the methods below.

### Option 1 — Environment variable

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
      "args": [ "--directory", "/Users/yourname/work-diary-mcp/python", "run", "work-diary-mcp" ],
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

### Option 2 — Settings file

Create `~/.config/work-diary/settings.toml` with a `data_dir` key:

```toml
data_dir = "~/Documents/work-diary"
```

The path is expanded automatically and the directory is created on first use.

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
TF-34398 is now On Track
Add a note: opened TF-34398 and RDPR-1234 to track the rollout
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

The current default Jira base URL is:

- `https://hashicorp.atlassian.net/browse`

The currently supported ticket prefixes are:

- `TF`
- `RDPR`
- `TFDN`
- `SECGRC`
- `IND`
- `CAG`

Examples:

| You type | Stored as |
|----------|-----------|
| `TF-34398` | `[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)` |
| `blocked by RDPR-1234` | `blocked by [RDPR-1234](https://hashicorp.atlassian.net/browse/RDPR-1234)` |
| `[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)` | unchanged |

Ticket keys are uppercased in generated links. References that do not match a supported prefix are left as-is.

To customize auto-linking for your Jira instance, update `work_diary_mcp/jira.py`:

- **`_KNOWN_PREFIXES`** — the tuple of recognised project key prefixes
- **`JIRA_BASE_URL`** — your Jira instance's base browse URL

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
    ├── config.py              # Data directory resolution (env var / settings file)
    ├── diary.py               # State management, week helpers, persistence
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
