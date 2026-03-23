# Changelog

All notable changes to `work-diary-mcp` will be documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows a simple versioned changelog structure.

## [Unreleased]

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
- Natural-language date targeting for write operations, including:
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
- GitHub Actions test coverage on both:
  - `ubuntu-latest`
  - `windows-latest`

### Changed
- Historical week pages are now created as empty diary pages rather than retroactively carrying forward state.
- Explicit ISO dates passed to historical page creation are normalized to that week’s Monday to preserve the one-file-per-week invariant.
- Jira linkification no longer depends on hardcoded organization-specific prefixes or URLs.
- Help text for date-targeting tool parameters now consistently documents all supported relative date formats.
- Persisted weekly Markdown now includes reminders when rendering `YYYY-MM-DD.md`.
- Reminder changes now regenerate persisted weekly Markdown for existing week pages.

### Fixed
- Preserved current-week carry-forward behavior when a caller explicitly supplies an ISO date that resolves to the current week.
- Ensured carry-forward only uses the most recent **prior** week, not a future-dated diary file.
- Guarded POSIX-only permission handling for cross-platform atomic writes.
- Prevented Windows lock files from growing indefinitely during repeated lock acquisition.
- Normalized Windows newlines in Markdown table cells to avoid stray carriage returns.
- Fixed reminder lookup so rendering a non-Monday date within a week still finds that week’s reminders.
- Cached the Jira ticket regex instead of recompiling it repeatedly during linkification.
- Regenerated persisted weekly Markdown when reminders are added or their completion state changes.
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
  - updated tool descriptions and usage examples

## [1.0.0]
- Initial Python-based MCP server for managing weekly work diaries.
- Project status tracking with inline notes.
- General note capture.
- Carry-forward behavior for non-completed projects.
- Markdown rendering for easy reuse in Microsoft Loop.
- Jira auto-linking support.
- FastMCP-based stdio server implementation.