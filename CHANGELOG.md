# Changelog

All notable changes to `work-diary-mcp` will be documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows a simple versioned changelog structure.

## [0.2.0 - 03-28-2026]

### Added
- Project row reference support for existing projects, allowing updates by table position with references such as `project 2`.
- Bulk project update support for existing project row references, allowing bulk updates to target rows such as `project 2`.

### Changed
- Existing projects can now be referenced by row number in project update operations, including bulk updates, while ambiguous references require clarification instead of guessing.

### Fixed
- Added ambiguity detection for project row references so inputs like `project 2` do not silently target the wrong row when they could also refer to a literal project name.
- Ensured bulk project updates treat out-of-range row references as errors instead of creating unintended new projects.

### Documentation
- Updated both README files to document:
  - project row reference examples
- Reorganized both README files to:
  - add an index near the top
  - move installation, configuration, tools, and usage higher up
  - move project/reference information lower down
  - consolidate configuration guidance into a single section

## [0.1.0 - 03-23-2026]

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

## [Unreleased]
- Initial Python-based MCP server for managing weekly work diaries.
- Project status tracking with inline notes.
- General note capture.
- Carry-forward behavior for non-completed projects.
- Markdown rendering for easy reuse in Microsoft Loop.
- Jira auto-linking support.
- FastMCP-based stdio server implementation.