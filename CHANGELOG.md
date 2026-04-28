# Changelog

All notable changes to `work-diary-mcp` will be documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows a simple versioned changelog structure.

## [Unreleased]

### Added
- New terminal project statuses **Shipped** and **GA**, both rendered with the 🚀 emoji and excluded from carry-forward.
- New non-terminal project status **In Planning**, rendered with the 💡 emoji.
- Opt-in `WORK_DIARY_FILE_LOCKS` environment variable that re-enables filesystem-based week and reminder locks for multi-process deployments. Disabled by default; in-process `threading.Lock`s are used in the common single-process case.

### Changed
- Reduced per-tool-call latency by:
  - Dropping `os.fsync` from `_atomic_write_text`. Tempfile + rename still provides application-level atomicity; fsync was the dominant per-call cost on macOS APFS.
  - Caching parsed `DiaryState` and `ReminderState` keyed by file mtime so repeated reads within a process avoid re-parsing and re-validating JSON. The cache invalidates automatically when the underlying file's mtime changes.
  - Memoizing `_ensure_week_page` results by `(today, week_key)` so subsequent same-day tool calls skip the lock acquisition and existence check once the page is known to exist.
  - Replacing the unconditional `flock` / `msvcrt.locking` calls with in-process `threading.Lock`s, with the filesystem locks now opt-in via `WORK_DIARY_FILE_LOCKS`.
  - Re-introducing an `lru_cache` on the compiled Jira ticket regex, keyed on the resolved prefix tuple so configuration changes still produce a fresh pattern.

### Fixed
- Week-write paths now acquire `_reminder_lock` before `_week_lock` via a new `_week_write` helper, establishing a single canonical lock ordering across week-write and reminder-write code paths. This closes both a race where a concurrent reminder write could leave the persisted Markdown out of sync and an AB/BA deadlock that would have occurred if `_save_state` acquired the reminder lock from underneath the week lock. `_save_state` now requires reminders to be supplied by the caller so the dangerous fallback path cannot be reintroduced.
- `get_or_create_page_for_week` now applies carry-forward when the supplied ISO date resolves to the current week, preventing direct callers from silently creating an empty current-week page.
- `list_projects` now normalizes the supplied week key to that week's Monday, matching `list_reminders` and `get_diary_markdown`.

### Documentation
- Reformatted `CHANGELOG.md` to follow Keep a Changelog conventions: `[Unreleased]` lives at the top, version headers use `## [X.Y.Z] - YYYY-MM-DD`, and the redundant trailing `[Unreleased]` block has been removed.

## [0.2.0] - 2026-03-28

### Added
- Project row reference support for existing projects across update, bulk update, rename, remove, and clear-note operations, allowing references such as `project 2` to target a project by table position.

### Changed
- Existing projects can now be referenced by row number in project update, bulk update, rename, remove, and clear-note operations, while ambiguous references require clarification instead of guessing.
- Row references such as `project 2` resolve to existing project rows when in range; non-positive row references fail, and out-of-range positive references continue to fall back to literal project names for update operations.

### Fixed
- Added ambiguity detection for project row references so inputs like `project 2` do not silently target the wrong row when they could also refer to a literal project name.
- Improved handling and documentation of row-reference edge cases so non-positive indices fail with clear errors, including when a literal project named `Project 0` exists, while out-of-range positive references can still be treated as literal project names.
- Improved row-reference error messaging so singular and plural project counts use correct grammar.

### Documentation
- Updated both README files to document:
  - project row reference examples
- Reorganized both README files to:
  - add an index near the top
  - move installation, configuration, tools, and usage higher up
  - move project/reference information lower down
  - consolidate configuration guidance into a single section

## [0.1.0] - 2026-03-23

### Added
- Support for writing to previous diary weeks across write operations, including:
  - `update_project_status`
  - `bulk_update_projects`
  - `rename_project`
  - `remove_project`
  - `clear_project_note`
  - `add_note`
  - `edit_note`
  - `delete_note`
- Natural-language date targeting for write operations and reminders, including:
  - `last week`
  - `next week`
  - `N weeks ago`
  - `N weeks from now`
  - `in N weeks`
  - ISO dates such as `2026-03-02`
- Reminder support for current and future weeks with new reminder tools:
  - `add_reminder`
  - `list_reminders`
  - `complete_reminder`
  - `reopen_reminder`
- Separate reminder storage in `reminders.json` so future reminders do not create future diary pages.
- Reminder rendering in a dedicated `Reminders for this week` section before `Project Status`.
- Checkbox-based reminder rendering with completion state:
  - `- [ ]`
  - `- [x]`
- Optional reminder due dates rendered in the format:
  - `Due Date: <date>`
- Configurable Jira auto-linking via:
  - environment variables:
    - `WORK_DIARY_JIRA_BASE_URL`
    - `WORK_DIARY_JIRA_PREFIXES`
  - settings file keys:
    - `jira_base_url`
    - `jira_prefixes`
- Generic built-in Jira defaults for reusable out-of-the-box behavior:
  - base URL: `https://jira.example.com/browse`
  - prefixes: `PROJ`, `INFRA`, `ENG`, `OPS`, `SEC`, `DATA`
- Expanded automated test coverage for:
  - historical week writes
  - reminders
  - Jira configuration
  - Windows behavior
  - tool-layer week resolution
  - persisted Markdown regeneration for reminder updates
  - reminder locking and refresh scoping
- GitHub Actions test coverage on both:
  - `ubuntu-latest`
  - `windows-latest`

### Changed
- Historical week pages are now created as empty diary pages rather than retroactively carrying forward state.
- Explicit ISO dates passed to historical page creation are normalized to that week’s Monday to preserve the one-file-per-week invariant.
- Jira linkification no longer depends on hardcoded organization-specific prefixes or URLs.
- Help text for date-targeting tool parameters now consistently documents all supported relative date formats.
- Persisted weekly Markdown now includes reminders when rendering `YYYY-MM-DD.md`.
- Reminder changes now regenerate persisted weekly Markdown for the affected existing week page only.

### Fixed
- Preserved current-week carry-forward behavior when a caller explicitly supplies an ISO date that resolves to the current week.
- Ensured carry-forward only uses the most recent **prior** week, not a future-dated diary file.
- Guarded POSIX-only permission handling for cross-platform atomic writes.
- Prevented Windows lock files from growing indefinitely during repeated lock acquisition.
- Normalized Windows newlines in Markdown table cells to avoid stray carriage returns.
- Fixed reminder lookup so rendering a non-Monday date within a week still finds that week’s reminders.
- Cached the Jira ticket regex instead of recompiling it repeatedly during linkification.
- Regenerated persisted weekly Markdown when reminders are added or their completion state changes.
- Added reminder locking and protected reminder-driven week Markdown refreshes with week locks to avoid concurrent stale rewrites.
- Corrected idempotency hints for non-idempotent write tools.
- Improved Windows config path handling and test portability.
- Aligned typed diary structures with runtime behavior, including:
  - required project update fields
  - optional legacy note timestamps

### Documentation
- Updated both README files to document:
  - previous-week write support
  - reminder support
  - future reminder behavior
  - configurable Jira auto-linking
  - Windows settings file location
  - expanded relative date examples
  - reminder Markdown refresh behavior
  - updated tool descriptions and usage examples
- Added a top-level `CHANGELOG.md` and linked it from both README files.