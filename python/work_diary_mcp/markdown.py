from work_diary_mcp.statuses import format_status

# --------------------------------------------------------------------------- #
# Renderer
# --------------------------------------------------------------------------- #


def render_diary(state: dict) -> str:
    """
    Render a diary state dict as a Markdown string suitable for
    copy-pasting into Microsoft Loop.
    """
    from work_diary_mcp.diary import get_week_label

    week_key: str = state["weekKey"]
    projects: dict[str, str] = state.get("projects", {})
    project_notes: dict[str, str] = state.get("projectNotes", {})
    notes: list[dict] = state.get("notes", [])

    label = get_week_label(week_key)
    lines: list[str] = []

    # Title
    lines.append(f"# Work Diary — Week of {label}")
    lines.append("")

    # Project status table
    lines.append("## Project Status")
    lines.append("")
    lines.append("| Project | Status | Notes |")
    lines.append("|---------|--------|-------|")

    if not projects:
        lines.append("| *(no projects yet)* | — | |")
    else:
        for project, status in projects.items():
            note = project_notes.get(project, "")
            lines.append(f"| {project} | {format_status(status)} | {note} |")

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
