from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from work_diary_mcp.diary import (
    add_note,
    bulk_update_projects,
    clear_project_note,
    delete_note,
    edit_note,
    get_diary_markdown,
    get_or_create_week_page,
    get_week_key,
    get_week_label,
    list_projects,
    list_week_keys,
    parse_week_key,
    remove_project,
    rename_project,
    update_project_status,
)

mcp = FastMCP(
    name="work-diary",
    instructions=(
        "This server manages a weekly work diary. "
        "Use it to track project statuses and log notes throughout the week. "
        "Each Monday a new diary page is created automatically, carrying forward "
        "projects from the prior week (excluding any projects marked as Done, "
        "Completed, Cancelled, or otherwise complete). Diary files are stored as "
        "Markdown and can be copied directly into Microsoft Loop.\n\n"
        "## Tone and style\n\n"
        "Before saving any note or project update, review the content and transform "
        "it into professional but authentic language. Preserve the writer's voice and "
        "personality — the goal is polished, not sterile. Keep all technical terms, "
        "Jira ticket references, and Markdown links exactly as provided. Remove or "
        "rephrase any language that would be inappropriate in a professional context "
        "(e.g. profanity, excessive frustration, dismissive phrasing) while retaining "
        "the underlying meaning and emotional tone where appropriate.\n\n"
        "## Completeness\n\n"
        "If a note or project update appears to be an incomplete thought, a fragment, "
        "or an unfinished message (e.g. trailing off, missing context, ambiguous "
        "references like 'that thing' or 'the issue'), ask the user a focused "
        "clarifying question before saving. Do not guess or fill in missing details.\n\n"
        "## Timestamps\n\n"
        "Do not add timestamps to notes automatically. Only include a date or time in "
        "a note if the user explicitly mentions one."
    ),
)


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def update_project_status_tool(
    project: Annotated[str, "The name of the project to update, e.g. 'Project Phoenix'"],
    status: Annotated[
        str,
        "The new status for the project, e.g. 'On Track', 'Blocked', 'Done'. "
        "Well-known statuses are automatically formatted with emoji.",
    ],
    note: Annotated[
        str | None,
        "Optional note to display alongside the project in the status table. "
        "Supports markdown, including hyperlinks e.g. '[ticket](https://...)'.",
    ] = None,
    append_note: Annotated[
        bool,
        "When True, the note is appended to any existing note (separated by ' — ') "
        "rather than replacing it. Has no effect when no prior note exists. "
        "Defaults to False.",
    ] = False,
) -> str:
    """Update (or add) a project's status in this week's work diary.

    Creates a new diary page if this is the first interaction of the week,
    carrying forward all non-completed projects from the prior week.
    """
    try:
        page = get_or_create_week_page()
        update_project_status(page["week_key"], project, status, note, append_note)

        prefix = (
            f"📅 Created new diary for the week of **{page['week_label']}**.\n\n"
            if page["is_new"]
            else ""
        )
        return (
            f"{prefix}✅ Updated **{project}** → `{status}` "
            f"in your diary for the week of **{page['week_label']}**."
        )
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def bulk_update_projects_tool(
    updates: Annotated[
        list[dict],
        "List of project updates. Each item must have 'project' (str) and "
        "'status' (str), and may optionally include 'note' (str) and "
        "'append_note' (bool, default false).",
    ],
) -> str:
    """Update multiple projects in a single operation.

    More efficient than calling update_project_status repeatedly when you
    have several projects to update at once, e.g. during a standup.
    Creates a new diary page if this is the first interaction of the week.
    """
    try:
        page = get_or_create_week_page()
        results = bulk_update_projects(page["week_key"], updates)

        prefix = (
            f"📅 Created new diary for the week of **{page['week_label']}**.\n\n"
            if page["is_new"]
            else ""
        )
        result_lines = "\n".join(f"- {r}" for r in results)
        return (
            f"{prefix}✅ Updated {len(results)} project(s) for the week of "
            f"**{page['week_label']}**:\n\n{result_lines}"
        )
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def rename_project_tool(
    old_name: Annotated[str, "The current name of the project to rename"],
    new_name: Annotated[str, "The new name for the project"],
) -> str:
    """Rename a project in this week's diary, preserving its status and note.

    Raises an error if the project is not found, or if the new name already
    belongs to a different project.
    """
    try:
        page = get_or_create_week_page()
        rename_project(page["week_key"], old_name, new_name)
        return (
            f"✏️ Renamed **{old_name}** → **{new_name}** "
            f"in your diary for the week of **{page['week_label']}**."
        )
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
def remove_project_tool(
    project: Annotated[str, "The name of the project to remove"],
) -> str:
    """Remove a project and its note from this week's diary.

    Use this when a project is no longer relevant for the current week.
    Raises an error if the project is not found.
    """
    try:
        page = get_or_create_week_page()
        remove_project(page["week_key"], project)
        return f"🗑️ Removed **{project}** from your diary for the week of **{page['week_label']}**."
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def clear_project_note_tool(
    project: Annotated[str, "The name of the project whose note should be cleared"],
) -> str:
    """Clear the note for a project in this week's diary.

    Leaves the project and its status intact. Raises an error if the
    project is not found.
    """
    try:
        page = get_or_create_week_page()
        clear_project_note(page["week_key"], project)
        return (
            f"🧹 Cleared note for **{project}** in your diary "
            f"for the week of **{page['week_label']}**."
        )
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations={"readOnlyHint": False})
def add_note_tool(
    content: Annotated[str, "The note content to add to this week's diary"],
) -> str:
    """Append a note to the general notes section of this week's work diary.

    Before calling this tool:
    - Transform the content into professional but authentic language, preserving
      the writer's voice, technical terms, Jira references, and Markdown links.
    - If the content appears to be an incomplete thought or fragment, ask the
      user a clarifying question instead of saving.
    - Do not add a timestamp. Only include a date or time if the user mentioned one.

    Creates a new diary page if this is the first interaction of the week,
    carrying forward all non-completed projects from the prior week.
    """
    try:
        page = get_or_create_week_page()
        add_note(page["week_key"], content)

        prefix = (
            f"📅 Created new diary for the week of **{page['week_label']}**.\n\n"
            if page["is_new"]
            else ""
        )
        return f"{prefix}📝 Added note to your diary for the week of **{page['week_label']}**."
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True})
def edit_note_tool(
    index: Annotated[
        int,
        "The 1-based index of the note to edit, as shown in the diary (e.g. 1 for [1]).",
    ],
    new_content: Annotated[str, "The replacement text for the note"],
) -> str:
    """Edit an existing note in this week's diary.

    Before calling this tool:
    - Transform the new content into professional but authentic language, preserving
      the writer's voice, technical terms, Jira references, and Markdown links.
    - If the new content appears to be an incomplete thought or fragment, ask the
      user a clarifying question instead of saving.
    - Do not add a timestamp. Only include a date or time if the user mentioned one.

    Use get_diary first to see the notes and their index numbers.
    Raises an error if the index is out of range.
    """
    try:
        page = get_or_create_week_page()
        edit_note(page["week_key"], index, new_content)
        return f"✏️ Updated note [{index}] in your diary for the week of **{page['week_label']}**."
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
def delete_note_tool(
    index: Annotated[
        int,
        "The 1-based index of the note to delete, as shown in the diary (e.g. 1 for [1]).",
    ],
) -> str:
    """Delete a note from this week's diary by its index number.

    Use get_diary first to see the notes and their index numbers.
    Raises an error if the index is out of range.
    """
    try:
        page = get_or_create_week_page()
        deleted = delete_note(page["week_key"], index)
        return (
            f"🗑️ Deleted note [{index}] from your diary "
            f"for the week of **{page['week_label']}**: '{deleted}'"
        )
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations={"readOnlyHint": True})
def get_diary(
    date: Annotated[
        str | None,
        "Optional date to retrieve a specific week's diary. "
        "Accepts ISO dates (e.g. '2026-03-02'), 'last week', or 'N weeks ago'. "
        "Defaults to the current week.",
    ] = None,
) -> str:
    """Retrieve the full Markdown content of a week's work diary.

    Returns the project status table and all notes. Also writes the
    rendered Markdown file to disk. Defaults to the current week.
    """
    try:
        week_key = parse_week_key(date) if date else get_week_key()
        week_label = get_week_label(week_key)
        markdown = get_diary_markdown(week_key)
        return f"Here is your work diary for the week of **{week_label}**:\n\n{markdown}"
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations={"readOnlyHint": True})
def list_projects_tool(
    date: Annotated[
        str | None,
        "Optional date to list projects for a specific week. "
        "Accepts ISO dates (e.g. '2026-03-02'), 'last week', or 'N weeks ago'. "
        "Defaults to the current week.",
    ] = None,
) -> str:
    """List all projects and their current statuses tracked in the diary.

    Defaults to the current week, but can show any week via the date parameter.
    """
    try:
        week_key = parse_week_key(date) if date else get_week_key()
        week_label = get_week_label(week_key)
        projects = list_projects(week_key)

        if not projects:
            return f"No projects tracked yet for the week of **{week_label}**."

        lines = [f"- **{p}**: {s}" for p, s in projects.items()]
        return f"Projects for the week of **{week_label}**:\n\n" + "\n".join(lines)
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations={"readOnlyHint": True})
def list_weeks() -> str:
    """List all weeks that have diary entries, sorted from oldest to newest.

    Use this to discover available weeks before calling get_diary with a
    specific date.
    """
    try:
        weeks = list_week_keys()

        if not weeks:
            return "No diary entries found yet."

        lines = [f"- {get_week_label(k)} (`{k}`)" for k in weeks]
        count = len(weeks)
        plural = "s" if count != 1 else ""
        return f"Found {count} week{plural} with diary entries:\n\n" + "\n".join(lines)
    except Exception as e:
        raise ToolError(str(e)) from e


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
