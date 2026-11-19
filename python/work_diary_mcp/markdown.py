from work_diary_mcp.config import get_reviews_title
from work_diary_mcp.statuses import format_review_status, format_status


def _format_reminder_line(reminder: dict) -> str:
    """Render a reminder as a Markdown checkbox list item."""
    checkbox = "[x]" if reminder.get("completed", False) else "[ ]"
    due_date = reminder.get("dueDate")
    content = reminder.get("content", "")
    prefix = f"Due Date: {due_date} " if due_date else ""
    return f"- {checkbox} {prefix}{content}"


# --------------------------------------------------------------------------- #
# Renderer
# --------------------------------------------------------------------------- #


def _escape_table_cell(value: str) -> str:
    """Escape Markdown table cell content."""
    return (
        value.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", "<br>")
    )


def render_diary(state: dict) -> str:
    """
    Render a diary state dict as a Markdown string suitable for
    copy-pasting into Microsoft Loop.
    """
    from work_diary_mcp.diary import get_week_label

    week_key: str = state["weekKey"]
    reminders: list[dict] = state.get("reminders", [])
    projects: dict[str, str] = state.get("projects", {})
    project_notes: dict[str, str] = state.get("projectNotes", {})
    project_roles: dict[str, str] = state.get("projectRoles", {})
    reviews: dict[str, dict[str, str]] = state.get("reviews", {})
    notes: list[dict] = state.get("notes", [])

    label = get_week_label(week_key)
    lines: list[str] = []

    # Title
    lines.append(f"# Work Diary — Week of {label}")
    lines.append("")

    # Reminders
    lines.append("## Reminders for this week")
    lines.append("")

    if not reminders:
        lines.append("*(no reminders for this week)*")
    else:
        for reminder in reminders:
            lines.append(_format_reminder_line(reminder))

    lines.append("")

    # Project status table
    lines.append("## Project Status")
    lines.append("")
    lines.append("| Project | Role | Status | Notes |")
    lines.append("|---------|------|--------|-------|")

    if not projects:
        lines.append("| *(no projects yet)* | | — | |")
    else:
        for project, status in projects.items():
            note = project_notes.get(project, "")
            role = project_roles.get(project, "")
            lines.append(
                "| "
                f"{_escape_table_cell(project)} | "
                f"{_escape_table_cell(role)} | "
                f"{_escape_table_cell(format_status(status))} | "
                f"{_escape_table_cell(note)} |"
            )

    lines.append("")

    # Reviews (only rendered when something is being tracked)
    if reviews:
        lines.append(f"## {get_reviews_title()}")
        lines.append("")
        lines.append("| Story | My Role | Story Status | My Status |")
        lines.append("|-------|---------|--------------|-----------|")
        for item, entry in reviews.items():
            lines.append(
                "| "
                f"{_escape_table_cell(item)} | "
                f"{_escape_table_cell(entry.get('role', ''))} | "
                f"{_escape_table_cell(entry.get('storyStatus', ''))} | "
                f"{_escape_table_cell(format_review_status(entry.get('status', '')))} |"
            )
        lines.append("")

    # General notes
    lines.append("## Notes")
    lines.append("")

    if not notes:
        lines.append("*(no notes yet)*")
    else:
        for i, entry in enumerate(notes):
            content = entry.get("content", "")
            lines.append(f"- **[{i + 1}]** {content}")

    lines.append("")

    return "\n".join(lines)
