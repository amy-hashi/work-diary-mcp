---
name: work-diary
description: Track weekly work status, project notes, and reminders in a personal work diary (equivalent to the work-diary-mcp server). Use when the user asks to update a project's status, add a note or reminder to their work diary, view their diary/standup notes, list tracked projects, or push the diary to a synced cloud folder — without using the work-diary MCP server directly.
---

# Work Diary

This skill drives the same work-diary logic as `~/work-diary-mcp` (its
`work_diary_mcp` Python library), but through a local CLI script instead of
the MCP server/protocol. It reads and writes the exact same data files, so
it is fully interchangeable with the MCP tools.

Run all commands via:

```
python3 ~/.agents/skills/work-diary/cli.py <command> [options]
```

Run `python3 ~/.agents/skills/work-diary/cli.py <command> --help` for exact
flags. Every command accepts `--date` to target a specific week (ISO date,
`"last week"`, `"next week"`, `"N weeks ago"`, `"N weeks from now"`, or
`"in N weeks"`); omit it for the current week.

## Commands

- `get-diary [--date D]` — print the full rendered Markdown diary (reminders, project status table, notes).
- `list-projects [--date D] [--json]` — list tracked projects and statuses.
- `list-weeks [--json]` — list all weeks that have diary entries.
- `update-status --project NAME --status STATUS [--note TEXT] [--append-note] [--role ROLE] [--date D]` — add/update a project's status. Creates the project if it doesn't exist yet.
- `bulk-update --json '[{"project":"X","status":"On Track","note":"...","role":"..."}]' [--date D]` — update several projects in one call (e.g. after a standup).
- `set-role --project NAME --role ROLE [--date D]` — set/clear a project's engagement role (empty string clears). Roles: Sponsor, Guide, Catcher, Advisor, Catalyst, Participant (also accepts emoji or shortcodes like `:rocket:`).
- `rename-project --old OLD --new NEW [--date D]`
- `remove-project --project NAME [--date D]`
- `clear-note --project NAME [--date D]` — clears a project's inline note, keeps its status.
- `add-note --content TEXT [--date D]` — append a general diary note.
- `edit-note --index N --content TEXT [--date D]` — 1-based index, see `get-diary` for indices.
- `delete-note --index N [--date D]`
- `add-reminder --content TEXT [--due-date DUE] [--date D]`
- `list-reminders [--date D] [--json]`
- `complete-reminder --index N [--date D]`
- `reopen-reminder --index N [--date D]`
- `push-sync [--date D]` — copy the week's Markdown to the configured cloud-sync folder (`WORK_DIARY_SYNC_PATH` env var or `sync_path` in the settings file). Errors if not configured.

Project references also accept row form, e.g. `--project "project 2"`.

## Behavior notes (inherited from the underlying library — do not reimplement)

- **Statuses & roles are auto-formatted** with emoji (e.g. `"on track"` → `🟢 On Track`, `"sponsor"` → `🚀 Sponsor`). Pass plain text; don't add emoji yourself.
- **Jira ticket refs are auto-linkified.** Bare keys matching configured prefixes (default `PROJ, INFRA, ENG, OPS, SEC, DATA`; configurable via `WORK_DIARY_JIRA_PREFIXES`) are turned into Markdown links automatically on save — do not manually wrap them in links.
- **New weeks carry forward** non-completed projects (and their roles) and uncompleted reminders from the prior week automatically the first time a week is touched.
- **Data location**: resolved from `WORK_DIARY_DATA_DIR` env var, else a settings file (`~/.config/work-diary/settings.toml`), else `~/work-diary-mcp/data`. Don't override unless the user asks — it should already point at their real diary data.
- **Persisted settings**: `~/.config/work-diary/settings.toml` carries this user's configuration (same file the MCP server reads), so both the skill and server stay in sync automatically:
  - `data_dir` — diary data location
  - `jira_base_url` = `https://hashicorp.atlassian.net/`
  - `jira_prefixes` = `PROJ, INFRA, ENG, OPS, SEC, DATA`
  - `sync_path` = `~/CloudStorage/Box/work-diary`
  - `auto_sync` = `true` (every write auto-copies the week's Markdown to `sync_path`, so `push-sync` is rarely needed manually)
  Corresponding env vars (`WORK_DIARY_DATA_DIR`, `WORK_DIARY_JIRA_BASE_URL`, `WORK_DIARY_JIRA_PREFIXES`, `WORK_DIARY_SYNC_PATH`, `WORK_DIARY_AUTO_SYNC`) override the settings file if ever set, but normally shouldn't need to be.

## Tone and content guidance (mirrors the MCP server's instructions)

Before saving any note or project update:
- Rewrite the content into professional but authentic language — preserve the user's voice/personality, don't sterilize it. Preserve technical terms, Jira ticket IDs, and any existing Markdown links as-is.
- Do **not** manually convert bare Jira keys into links — the CLI/library does this automatically on save.
- Remove or rephrase anything inappropriate for a professional context (profanity, excessive frustration) while keeping the underlying meaning/tone.
- If a note or update reads like an incomplete thought or fragment (trailing off, vague references like "that thing"), ask the user a clarifying question before saving instead of guessing.
- Do not add timestamps to notes automatically — only include a date/time if the user explicitly mentioned one.

## Example

```
python3 ~/.agents/skills/work-diary/cli.py update-status \
  --project "Project Phoenix" --status "At Risk" \
  --note "Blocked on PROJ-1234" --role sponsor

python3 ~/.agents/skills/work-diary/cli.py add-reminder \
  --content "Follow up with security team" --due-date 2026-04-10

python3 ~/.agents/skills/work-diary/cli.py get-diary
```
