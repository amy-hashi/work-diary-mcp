import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from work_diary_mcp.config import get_data_dir
from work_diary_mcp.jira import linkify_jira_refs
from work_diary_mcp.statuses import is_completed

# --------------------------------------------------------------------------- #
# Types
# --------------------------------------------------------------------------- #

type DiaryState = dict  # {weekKey, projects, projectNotes, notes}


# --------------------------------------------------------------------------- #
# Week key helpers
# --------------------------------------------------------------------------- #


def get_monday_of(d: date) -> date:
    """Return the Monday of the week containing *d*."""
    return d - timedelta(days=d.weekday())  # weekday(): Mon=0 … Sun=6


def get_week_key(d: date | None = None) -> str:
    """Return a stable ISO week key (always a Monday), e.g. '2026-03-02'."""
    return get_monday_of(d or date.today()).isoformat()


def get_week_label(week_key: str) -> str:
    """Return a human-friendly label, e.g. 'Mar 2, 2026'."""
    d = date.fromisoformat(week_key)
    return d.strftime("%b %-d, %Y")


def parse_week_key(input_str: str) -> str:
    """
    Parse a date string into a week key.

    Accepts:
      - ISO dates:       '2026-03-02'
      - 'last week'
      - 'N weeks ago'   e.g. '2 weeks ago'
    """
    lowered = input_str.strip().lower()

    if lowered == "last week":
        return get_week_key(date.today() - timedelta(weeks=1))

    m = re.match(r"^(\d+)\s+weeks?\s+ago$", lowered)
    if m:
        n = int(m.group(1))
        return get_week_key(date.today() - timedelta(weeks=n))

    try:
        return get_week_key(date.fromisoformat(input_str.strip()))
    except ValueError:
        pass

    raise ValueError(
        f'Could not parse "{input_str}" as a date. '
        'Try a format like "2026-03-02", "last week", or "2 weeks ago".'
    )


# --------------------------------------------------------------------------- #
# File paths
# --------------------------------------------------------------------------- #


def _diary_path(week_key: str) -> Path:
    return get_data_dir() / f"{week_key}.json"


def _markdown_path(week_key: str) -> Path:
    return get_data_dir() / f"{week_key}.md"


# --------------------------------------------------------------------------- #
# State management
# --------------------------------------------------------------------------- #


def _empty_state(week_key: str) -> DiaryState:
    return {"weekKey": week_key, "projects": {}, "projectNotes": {}, "notes": []}


def _migrate_state(state: DiaryState) -> DiaryState:
    """Ensure older diary files load cleanly and have all fields linkified.

    Migrations applied (all idempotent):
    1. Add ``projectNotes`` if missing (legacy files pre-date that field).
    2. Linkify bare Jira ticket references in project keys, their associated
       notes, and general note contents so that files written before the
       auto-linking feature was introduced are upgraded on first load.
    """
    state.setdefault("projectNotes", {})

    # Linkify project keys and their notes.  We rebuild both dicts together so
    # the key used in projectNotes stays in sync with the key in projects.
    old_projects: dict[str, str] = state["projects"]
    old_notes: dict[str, str] = state["projectNotes"]
    new_projects: dict[str, str] = {}
    new_notes: dict[str, str] = {}
    for key, status in old_projects.items():
        new_key = linkify_jira_refs(key)
        new_projects[new_key] = status
        if key in old_notes:
            new_notes[new_key] = linkify_jira_refs(old_notes[key])
    state["projects"] = new_projects
    state["projectNotes"] = new_notes

    # Linkify general note contents.
    for entry in state.get("notes", []):
        entry["content"] = linkify_jira_refs(entry["content"])

    return state


def _load_state(week_key: str) -> DiaryState:
    path = _diary_path(week_key)
    if path.exists():
        return _migrate_state(json.loads(path.read_text(encoding="utf-8")))
    return _empty_state(week_key)


def _save_state(state: DiaryState) -> None:
    from work_diary_mcp.markdown import render_diary  # avoid circular import

    week_key = state["weekKey"]
    _diary_path(week_key).write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _markdown_path(week_key).write_text(render_diary(state), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Carry-forward helper
# --------------------------------------------------------------------------- #


def _get_carry_forward_state() -> dict:
    """Return projects/projectNotes from the most recent prior week, if any.

    Projects whose status is considered complete (Done, Completed, Cancelled,
    etc.) are excluded so they don't clutter the new week's diary.
    """
    weeks = list_week_keys()
    if not weeks:
        return {"projects": {}, "projectNotes": {}}
    last = _load_state(weeks[-1])

    projects: dict[str, str] = {}
    project_notes: dict[str, str] = {}
    for project, status in last["projects"].items():
        if not is_completed(status):
            projects[project] = status
            if project in last["projectNotes"]:
                project_notes[project] = last["projectNotes"][project]

    return {"projects": projects, "projectNotes": project_notes}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def get_or_create_week_page() -> dict:
    """
    Get or create this week's diary page.

    Returns a dict with keys: week_key, week_label, is_new.
    On first call of the week, projects are carried forward from the prior week,
    excluding any projects with a completed status (Done, Completed, Cancelled, etc.).
    """
    week_key = get_week_key()
    week_label = get_week_label(week_key)
    is_new = False

    if not _diary_path(week_key).exists():
        carried = _get_carry_forward_state()
        _save_state(
            {
                "weekKey": week_key,
                "projects": carried["projects"],
                "projectNotes": carried["projectNotes"],
                "notes": [],
            }
        )
        is_new = True

    return {"week_key": week_key, "week_label": week_label, "is_new": is_new}


def update_project_status(
    week_key: str,
    project: str,
    status: str,
    note: str | None = None,
    append_note: bool = False,
) -> None:
    """Update (or add) a project's status, and optionally its inline note.

    Args:
        week_key:    The week to update.
        project:     Project name (case-insensitive match against existing keys).
        status:      New status string.
        note:        Note text to set or append.
        append_note: When True and a note already exists, the new note is
                     appended (separated by " — ") rather than replacing it.
                     Has no effect when no prior note exists.
    """
    state = _load_state(week_key)

    # Case-insensitive match on existing keys to avoid duplicates
    existing_key = next(
        (k for k in state["projects"] if k.lower() == project.lower()), None
    )
    key = existing_key or linkify_jira_refs(project)
    state["projects"][key] = status

    if note is not None:
        linkified_note = linkify_jira_refs(note)
        if append_note and key in state["projectNotes"]:
            state["projectNotes"][key] = (
                state["projectNotes"][key] + " — " + linkified_note
            )
        else:
            state["projectNotes"][key] = linkified_note

    _save_state(state)


def rename_project(week_key: str, old_name: str, new_name: str) -> None:
    """Rename a project, preserving its status and note.

    Raises ValueError if *old_name* is not found, or if *new_name* already
    exists (case-insensitive) as a different project.
    """
    state = _load_state(week_key)

    old_key = next(
        (k for k in state["projects"] if k.lower() == old_name.lower()), None
    )
    if old_key is None:
        raise ValueError(
            f'Project "{old_name}" not found in the diary for the week of '
            f"{get_week_label(week_key)}."
        )

    # Prevent collisions with an existing different project
    collision = next(
        (
            k
            for k in state["projects"]
            if k.lower() == new_name.lower() and k != old_key
        ),
        None,
    )
    if collision is not None:
        raise ValueError(
            f'A project named "{collision}" already exists in the diary for '
            f"the week of {get_week_label(week_key)}."
        )

    # Rebuild dicts preserving insertion order, swapping the key in-place
    linked_new_name = linkify_jira_refs(new_name)
    state["projects"] = {
        (linked_new_name if k == old_key else k): v
        for k, v in state["projects"].items()
    }
    state["projectNotes"] = {
        (linked_new_name if k == old_key else k): v
        for k, v in state["projectNotes"].items()
    }

    _save_state(state)


def bulk_update_projects(
    week_key: str,
    updates: list[dict],
) -> list[str]:
    """Update multiple projects in a single read-modify-write cycle.

    Each item in *updates* must have:
        project     (str)           — project name
        status      (str)           — new status
        note        (str | None)    — optional note (default: None)
        append_note (bool)          — append vs. replace note (default: False)

    Returns a list of human-readable result strings, one per project.
    """
    state = _load_state(week_key)
    results: list[str] = []

    for item in updates:
        project = item["project"]
        status = item["status"]
        note = item.get("note")
        append_note = bool(item.get("append_note", False))

        existing_key = next(
            (k for k in state["projects"] if k.lower() == project.lower()), None
        )
        key = existing_key or linkify_jira_refs(project)
        state["projects"][key] = status

        if note is not None:
            linkified_note = linkify_jira_refs(note)
            if append_note and key in state["projectNotes"]:
                state["projectNotes"][key] = (
                    state["projectNotes"][key] + " — " + linkified_note
                )
            else:
                state["projectNotes"][key] = linkified_note

        results.append(f"{key} → {status}")

    _save_state(state)
    return results


def remove_project(week_key: str, project: str) -> None:
    """Remove a project and its note from the diary."""
    state = _load_state(week_key)

    existing_key = next(
        (k for k in state["projects"] if k.lower() == project.lower()), None
    )
    if existing_key is None:
        raise ValueError(
            f'Project "{project}" not found in the diary for the week of '
            f"{get_week_label(week_key)}."
        )

    del state["projects"][existing_key]
    state["projectNotes"].pop(existing_key, None)
    _save_state(state)


def clear_project_note(week_key: str, project: str) -> None:
    """Clear the inline note for a project, leaving its status intact."""
    state = _load_state(week_key)

    existing_key = next(
        (k for k in state["projects"] if k.lower() == project.lower()), None
    )
    if existing_key is None:
        raise ValueError(
            f'Project "{project}" not found in the diary for the week of '
            f"{get_week_label(week_key)}."
        )

    state["projectNotes"].pop(existing_key, None)
    _save_state(state)


def add_note(week_key: str, content: str) -> None:
    """Append a timestamped note to the general notes section."""
    state = _load_state(week_key)
    state["notes"].append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": linkify_jira_refs(content),
        }
    )
    _save_state(state)


def edit_note(week_key: str, index: int, new_content: str) -> None:
    """Replace the content of an existing note, preserving its timestamp.

    *index* is 1-based (as shown to the user).  Raises ValueError if out
    of range.
    """
    state = _load_state(week_key)
    notes = state["notes"]

    if not (1 <= index <= len(notes)):
        raise ValueError(
            f"Note index {index} is out of range — "
            f"there {'is' if len(notes) == 1 else 'are'} "
            f"{len(notes)} note{'s' if len(notes) != 1 else ''} "
            f"in the diary for the week of {get_week_label(week_key)}."
        )

    notes[index - 1]["content"] = linkify_jira_refs(new_content)
    _save_state(state)


def delete_note(week_key: str, index: int) -> str:
    """Delete a note by its 1-based index.

    Returns the content of the deleted note.  Raises ValueError if the
    index is out of range.
    """
    state = _load_state(week_key)
    notes = state["notes"]

    if not (1 <= index <= len(notes)):
        raise ValueError(
            f"Note index {index} is out of range — "
            f"there {'is' if len(notes) == 1 else 'are'} "
            f"{len(notes)} note{'s' if len(notes) != 1 else ''} "
            f"in the diary for the week of {get_week_label(week_key)}."
        )

    removed = notes.pop(index - 1)
    _save_state(state)
    return removed["content"]


def get_diary_markdown(week_key: str) -> str:
    """Render and persist the diary as Markdown, then return it."""
    from work_diary_mcp.markdown import render_diary

    state = _load_state(week_key)
    md = render_diary(state)
    _markdown_path(week_key).write_text(md, encoding="utf-8")
    return md


def list_projects(week_key: str) -> dict[str, str]:
    """Return the projects dict for the given week."""
    return _load_state(week_key)["projects"]


def list_week_keys() -> list[str]:
    """Return all week keys found in the data directory, sorted ascending."""
    return sorted(
        p.stem
        for p in get_data_dir().glob("*.json")
        if re.match(r"^\d{4}-\d{2}-\d{2}$", p.stem)
    )
