# work-diary-mcp (Python)

An MCP server for managing your weekly work diary, built with FastMCP.

## Why Python?

- **No build step** — edit `server.py` and restart the server; changes take effect immediately
- **Simpler setup** — `uv` manages dependencies with no `node_modules`
- **FastMCP** — decorators turn plain Python functions directly into MCP tools

## Features

- **Project status table** — track projects with a status and an optional inline note per project
- **General notes** — append timestamped notes throughout the week
- **Carry-forward** — non-completed projects and their notes are automatically carried forward each new week
- **Jira auto-linking** — bare ticket references (e.g. `TF-34398`) are automatically converted to Markdown links
- **Markdown links** — use standard Markdown link syntax anywhere: `[text](url)`
- **Relative date support** — retrieve past diaries with `"last week"` or `"2 weeks ago"`

## Setup

### 1. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install dependencies

```bash
cd ~/work-diary-mcp/python
uv sync
```

### 3. Register with Claude CLI

```bash
claude mcp add work-diary uv --directory $HOME/work-diary-mcp/python run work-diary-mcp
```

### 4. Register with Zed

Add to your Zed `settings.json` (`cmd+,`):

```json
{
  "context_servers": {
    "work-diary": {
      "command": "/opt/homebrew/bin/uv",
      "args": [
        "--directory",
        "/Users/amy/work-diary-mcp/python",
        "run",
        "work-diary-mcp"
      ],
      "env": {}
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `update_project_status` | Update or add a project's status, with an optional inline note. Pass `append_note: true` to append to an existing note instead of replacing it. |
| `bulk_update_projects` | Update multiple projects in a single operation — more efficient than calling `update_project_status` repeatedly. |
| `rename_project` | Rename a project, preserving its status and note. |
| `add_note` | Append a timestamped note to this week's general notes. |
| `edit_note` | Replace the content of an existing note by its index number, preserving its timestamp. |
| `delete_note` | Delete a note by its index number. |
| `get_diary` | Retrieve the full Markdown diary for any week. |
| `list_projects` | List all projects and statuses for any week. |
| `list_weeks` | List all weeks that have diary entries. |
| `remove_project` | Remove a project from this week's diary. |
| `clear_project_note` | Clear just the inline note for a project. |

## Usage

Just talk naturally in Claude — it will call the right tool:

```
Update Project Phoenix to On Track
TFE on Z is blocked — waiting on infra team
Add a note: had a productive all-hands today
Show me this week's diary
What projects am I tracking this week?
Show me my diary from last week
What weeks do I have diary entries for?
Remove Project Phoenix from this week
Clear the note on TFE on Z
Rename Project Phoenix to Phoenix Rewrite
Update all my projects: Phoenix Rewrite is On Track, TFE on Z is Blocked, Platform Infra is Done
Append a note to TFE on Z: dependency resolved, unblocked as of Friday
Edit note 2: corrected — the all-hands covered Q3 and Q4 roadmap
Delete note 3
Update TF-34398 to Blocked with a note: waiting on review
Add a note: opened TF-34398 and RDPR-1234 to track the infra work
```

## Jira Auto-Linking

Bare Jira ticket references are automatically converted to Markdown links wherever
text is saved — in project names, inline notes, and general notes.

| You type | Stored as |
|----------|-----------|
| `TF-34398` | `[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)` |
| `blocked by RDPR-1234` | `blocked by [RDPR-1234](https://hashicorp.atlassian.net/browse/RDPR-1234)` |

References that are already formatted as Markdown links are left untouched — you
will never end up with a double-linked ticket.

**Supported prefixes:** `TF`, `RDPR`, `TFDN`, `SECGRC`, `IND`, `CAG`

A ticket reference must have at least four digits (e.g. `TF-1234`) to be matched.
Add new prefixes to `_KNOWN_PREFIXES` in `work_diary_mcp/jira.py`.

## Supported Status Values

| Input | Rendered |
|-------|----------|
| On Track | 🟢 On Track |
| At Risk | 🟡 At Risk |
| Blocked | 🔴 Blocked |
| Done / Complete | ✅ Done |
| In Progress | 🔵 In Progress |
| Not Started | ⚪ Not Started |
| Cancelled | ⛔ Cancelled |
| Paused | ⏸️ Paused |

Any other status string is stored and displayed as-is.

## Project Structure

```
work_diary_mcp/
├── config.py      # Data directory resolution (env var / settings file)
├── diary.py       # State management, week helpers, public API
├── jira.py        # Jira ticket auto-linking
├── markdown.py    # Markdown renderer
├── server.py      # FastMCP server and tool definitions
└── statuses.py    # Status definitions (emoji map, completion set)
```

## Testing

```bash
uv run --group dev pytest -v
```

## Configuration

By default, diary files are written to `data/` inside the repository. You can
point the server at any directory using either of the methods below.

### Option 1 — Environment variable

Set `WORK_DIARY_DATA_DIR` to an absolute (or `~`-prefixed) path:

```bash
export WORK_DIARY_DATA_DIR=~/Documents/work-diary
```

To pass it through to the server in your MCP client config:

**Zed** — add an `env` entry:
```json
{
  "context_servers": {
    "work-diary": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["--directory", "/Users/amy/work-diary-mcp/python", "run", "work-diary-mcp"],
      "env": { "WORK_DIARY_DATA_DIR": "/Users/amy/Documents/work-diary" }
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

## Data

Diary files are written to the configured data directory:

- `YYYY-MM-DD.json` — raw state (week key is always the Monday)
- `YYYY-MM-DD.md` — rendered Markdown, ready to copy into Microsoft Loop

## Carry-Forward

On the first interaction of each new week (Monday onward), a new diary page is
created automatically. Non-completed projects and their inline notes are carried
forward from the most recent prior week so you never start from a blank slate.

Projects with a terminal status (**Done**, **Complete**, **Completed**,
**Cancelled**, **Canceled**) are **not** carried forward. Finished work stays
in the week it was completed and won't clutter the new week's diary.