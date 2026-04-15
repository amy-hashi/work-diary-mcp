import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import NotRequired, TypedDict

from work_diary_mcp.config import get_data_dir
from work_diary_mcp.jira import linkify_jira_refs
from work_diary_mcp.statuses import is_completed

# --------------------------------------------------------------------------- #
# Types
# --------------------------------------------------------------------------- #


class NoteEntry(TypedDict):
    content: str
    timestamp: NotRequired[str]


class ReminderEntry(TypedDict):
    content: str
    completed: bool
    dueDate: NotRequired[str]


class DiaryState(TypedDict):
    weekKey: str
    projects: dict[str, str]
    projectNotes: dict[str, str]
    notes: list[NoteEntry]


class ReminderState(TypedDict):
    reminders: dict[str, list[ReminderEntry]]


class ProjectUpdate(TypedDict):
    project: str
    status: str
    note: NotRequired[str | None]
    append_note: NotRequired[bool]


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
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def parse_week_key(input_str: str) -> str:
    """
    Parse a date string into a week key.

    Accepts:
      - ISO dates:       '2026-03-02'
      - 'last week'
      - 'next week'
      - 'N weeks ago'   e.g. '2 weeks ago'
      - 'N weeks from now' / 'in N weeks'
    """
    lowered = input_str.strip().lower()

    if lowered == "last week":
        return get_week_key(date.today() - timedelta(weeks=1))

    if lowered == "next week":
        return get_week_key(date.today() + timedelta(weeks=1))

    m = re.match(r"^(\d+)\s+weeks?\s+ago$", lowered)
    if m:
        n = int(m.group(1))
        return get_week_key(date.today() - timedelta(weeks=n))

    m = re.match(r"^(\d+)\s+weeks?\s+from\s+now$", lowered)
    if m:
        n = int(m.group(1))
        return get_week_key(date.today() + timedelta(weeks=n))

    m = re.match(r"^in\s+(\d+)\s+weeks?$", lowered)
    if m:
        n = int(m.group(1))
        return get_week_key(date.today() + timedelta(weeks=n))

    try:
        return get_week_key(date.fromisoformat(input_str.strip()))
    except ValueError:
        pass

    raise ValueError(
        f'Could not parse "{input_str}" as a date. '
        'Try a format like "2026-03-02", "last week", "next week", or "2 weeks ago".'
    )


# --------------------------------------------------------------------------- #
# File paths
# --------------------------------------------------------------------------- #


def _diary_path(week_key: str) -> Path:
    return get_data_dir() / f"{week_key}.json"


def _markdown_path(week_key: str) -> Path:
    return get_data_dir() / f"{week_key}.md"


def _reminders_path() -> Path:
    return get_data_dir() / "reminders.json"


# --------------------------------------------------------------------------- #
# State management
# --------------------------------------------------------------------------- #


def _empty_state(week_key: str) -> DiaryState:
    return {"weekKey": week_key, "projects": {}, "projectNotes": {}, "notes": []}


def _empty_reminder_state() -> ReminderState:
    return {"reminders": {}}


def _validate_state(state: DiaryState, week_key: str | None = None) -> DiaryState:
    """Validate and normalize the loaded diary state."""
    if not isinstance(state, dict):
        raise ValueError("Diary state must be a JSON object.")

    actual_week_key = state.get("weekKey")
    if not isinstance(actual_week_key, str):
        raise ValueError("Diary state is missing a valid 'weekKey' string.")
    if week_key is not None and actual_week_key != week_key:
        raise ValueError(
            f"Diary file week key mismatch: expected {week_key}, found {actual_week_key}."
        )

    projects = state.get("projects")
    if projects is None:
        projects = {}
        state["projects"] = projects
    if not isinstance(projects, dict):
        raise ValueError("Diary state field 'projects' must be an object.")
    for project, status in projects.items():
        if not isinstance(project, str) or not isinstance(status, str):
            raise ValueError("Diary state field 'projects' must map strings to strings.")

    project_notes = state.get("projectNotes")
    if project_notes is None:
        project_notes = {}
        state["projectNotes"] = project_notes
    if not isinstance(project_notes, dict):
        raise ValueError("Diary state field 'projectNotes' must be an object.")
    for project, note in project_notes.items():
        if not isinstance(project, str) or not isinstance(note, str):
            raise ValueError("Diary state field 'projectNotes' must map strings to strings.")

    notes = state.get("notes")
    if notes is None:
        notes = []
        state["notes"] = notes
    if not isinstance(notes, list):
        raise ValueError("Diary state field 'notes' must be a list.")
    for entry in notes:
        if not isinstance(entry, dict):
            raise ValueError("Each note entry must be an object.")
        content = entry.get("content")
        if not isinstance(content, str):
            raise ValueError("Each note entry must contain a string 'content' field.")

    return state


def _validate_reminder_state(state: ReminderState) -> ReminderState:
    """Validate and normalize the reminder state."""
    if not isinstance(state, dict):
        raise ValueError("Reminder state must be a JSON object.")

    reminders = state.get("reminders")
    if reminders is None:
        reminders = {}
        state["reminders"] = reminders
    if not isinstance(reminders, dict):
        raise ValueError("Reminder state field 'reminders' must be an object.")

    for week_key, entries in reminders.items():
        if not isinstance(week_key, str):
            raise ValueError("Reminder week keys must be strings.")
        if not isinstance(entries, list):
            raise ValueError("Reminder state must map week keys to lists.")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Each reminder entry must be an object.")
            content = entry.get("content")
            completed = entry.get("completed")
            due_date = entry.get("dueDate")
            if not isinstance(content, str):
                raise ValueError("Each reminder entry must contain a string 'content' field.")
            if not isinstance(completed, bool):
                raise ValueError("Each reminder entry must contain a boolean 'completed' field.")
            if due_date is not None and not isinstance(due_date, str):
                raise ValueError("Reminder entry field 'dueDate' must be a string if present.")

    return state


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


def _migrate_reminder_state(state: ReminderState) -> ReminderState:
    """Ensure reminder entries load cleanly and linkify reminder text."""
    state.setdefault("reminders", {})

    new_reminders: dict[str, list[ReminderEntry]] = {}
    for week_key, entries in state["reminders"].items():
        new_entries: list[ReminderEntry] = []
        for entry in entries:
            new_entry: ReminderEntry = {
                "content": linkify_jira_refs(entry["content"]),
                "completed": entry["completed"],
            }
            due_date = entry.get("dueDate")
            if due_date is not None:
                new_entry["dueDate"] = due_date
            new_entries.append(new_entry)
        new_reminders[week_key] = new_entries

    state["reminders"] = new_reminders
    return state


def _atomic_write_text(path: Path, content: str) -> None:
    """Atomically write text content to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = path.stat().st_mode if path.exists() else None
    fd, temp_path_str = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp_path = Path(temp_path_str)
    try:
        if existing_mode is not None and hasattr(os, "fchmod"):
            os.fchmod(fd, existing_mode & 0o777)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


@contextmanager
def _week_lock(week_key: str):
    """Take an exclusive filesystem lock for a week's diary state."""
    lock_path = get_data_dir() / f"{week_key}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        import msvcrt

        with lock_path.open("a+b") as lock_file:
            lock_file.seek(0)
            if lock_file.read(1) == b"":
                lock_file.seek(0)
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def _reminder_lock():
    """Take an exclusive filesystem lock for reminder state."""
    lock_path = get_data_dir() / "reminders.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        import msvcrt

        with lock_path.open("a+b") as lock_file:
            lock_file.seek(0)
            if lock_file.read(1) == b"":
                lock_file.seek(0)
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _load_state(week_key: str) -> DiaryState:
    path = _diary_path(week_key)
    if path.exists():
        raw_state = json.loads(path.read_text(encoding="utf-8"))
        validated = _validate_state(raw_state, week_key)
        return _migrate_state(validated)
    return _empty_state(week_key)


def _load_reminder_state() -> ReminderState:
    path = _reminders_path()
    if path.exists():
        raw_state = json.loads(path.read_text(encoding="utf-8"))
        validated = _validate_reminder_state(raw_state)
        return _migrate_reminder_state(validated)
    return _empty_reminder_state()


def _save_reminder_state(state: ReminderState, refresh_week_keys: set[str] | None = None) -> None:
    validated = _validate_reminder_state(state)
    json_content = json.dumps(validated, indent=2, ensure_ascii=False)
    _atomic_write_text(_reminders_path(), json_content)

    for week_key in refresh_week_keys or set():
        diary_path = _diary_path(week_key)
        if diary_path.exists():
            with _week_lock(week_key):
                _save_state(_load_state(week_key))


def _save_state(state: DiaryState) -> None:
    from work_diary_mcp.markdown import render_diary  # avoid circular import

    validated = _validate_state(state)
    week_key = validated["weekKey"]
    reminder_state = _load_reminder_state()
    reminders = reminder_state["reminders"].get(week_key, [])

    json_content = json.dumps(validated, indent=2, ensure_ascii=False)
    markdown_content = render_diary(
        {
            **validated,
            "reminders": reminders,
        }
    )

    _atomic_write_text(_diary_path(week_key), json_content)
    _atomic_write_text(_markdown_path(week_key), markdown_content)


# --------------------------------------------------------------------------- #
# Carry-forward helper
# --------------------------------------------------------------------------- #


def _get_carry_forward_state(target_week_key: str | None = None) -> dict:
    """Return projects from the most recent prior week, if any.

    Projects whose status is considered complete (Done, Completed, Cancelled,
    etc.) are excluded so they don't clutter the new week's diary.

    Project notes are intentionally not carried forward — they are
    week-specific context and should start fresh each week.
    """
    weeks = list_week_keys()
    if target_week_key is not None:
        weeks = [week for week in weeks if week < target_week_key]
    if not weeks:
        return {"projects": {}, "projectNotes": {}}
    last = _load_state(weeks[-1])

    projects: dict[str, str] = {}
    for project, status in last["projects"].items():
        if not is_completed(status):
            projects[project] = status

    return {"projects": projects, "projectNotes": {}}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def list_reminders(week_key: str) -> list[ReminderEntry]:
    """Return reminders for the given week."""
    normalized_week_key = get_week_key(date.fromisoformat(week_key))
    state = _load_reminder_state()
    return list(state["reminders"].get(normalized_week_key, []))


def add_reminder(week_key: str, content: str, due_date: str | None = None) -> None:
    """Add a reminder for the specified week without creating a diary page."""
    normalized_week_key = get_week_key(date.fromisoformat(week_key))

    with _reminder_lock():
        state = _load_reminder_state()

        entry: ReminderEntry = {
            "content": linkify_jira_refs(content),
            "completed": False,
        }
        if due_date is not None:
            entry["dueDate"] = due_date

        state["reminders"].setdefault(normalized_week_key, []).append(entry)
        _save_reminder_state(state, refresh_week_keys={normalized_week_key})


def set_reminder_completed(week_key: str, index: int, completed: bool) -> None:
    """Set the completion state of a reminder by its 1-based index."""
    normalized_week_key = get_week_key(date.fromisoformat(week_key))

    with _reminder_lock():
        state = _load_reminder_state()
        reminders = state["reminders"].get(normalized_week_key, [])

        if not (1 <= index <= len(reminders)):
            raise ValueError(
                f"Reminder index {index} is out of range — "
                f"there {'is' if len(reminders) == 1 else 'are'} "
                f"{len(reminders)} reminder{'s' if len(reminders) != 1 else ''} "
                f"for the week of {get_week_label(normalized_week_key)}."
            )

        reminders[index - 1]["completed"] = completed
        _save_reminder_state(state, refresh_week_keys={normalized_week_key})


def _ensure_week_page(week_key: str, carry_forward: bool) -> dict:
    """
    Get or create a diary page for a specific week.

    Returns a dict with keys: week_key, week_label, is_new.
    When *carry_forward* is True, newly created pages inherit non-completed
    projects from the most recent prior week. When False, newly created pages
    start empty.
    """
    week_label = get_week_label(week_key)
    is_new = False

    with _week_lock(week_key):
        if not _diary_path(week_key).exists():
            initial_state = (
                _get_carry_forward_state(week_key)
                if carry_forward
                else {"projects": {}, "projectNotes": {}}
            )
            _save_state(
                {
                    "weekKey": week_key,
                    "projects": initial_state["projects"],
                    "projectNotes": initial_state["projectNotes"],
                    "notes": [],
                }
            )
            is_new = True

    return {"week_key": week_key, "week_label": week_label, "is_new": is_new}


def get_or_create_week_page() -> dict:
    """
    Get or create this week's diary page.

    Returns a dict with keys: week_key, week_label, is_new.
    On first call of the week, projects are carried forward from the prior week,
    excluding any projects with a completed status (Done, Completed, Cancelled, etc.).
    """
    return _ensure_week_page(get_week_key(), carry_forward=True)


def get_or_create_page_for_week(week_key: str) -> dict:
    """
    Get or create a diary page for a specific week.

    The supplied week key may be any ISO date within the target week; it is
    normalized to that week's Monday before the page is created or loaded.

    Historical weeks are created empty rather than carrying forward state from
    adjacent weeks.
    """
    normalized_week_key = get_week_key(date.fromisoformat(week_key))
    return _ensure_week_page(normalized_week_key, carry_forward=False)


def _project_row_reference_index(project_ref: str) -> int | None:
    """Return the 1-based row index for a project reference like 'project 2'."""
    match = re.fullmatch(r"\s*project\s+(\d+)\s*", project_ref, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _resolve_existing_project_key(state: DiaryState, week_key: str, project_ref: str) -> str:
    """Resolve a project reference to an existing project key.

    Supports:
    - case-insensitive project name matching
    - row references of the form ``project N``

    Raises:
        ValueError: If the project reference is ambiguous, out of range, or
        does not resolve to an existing project.
    """
    exact_match = next(
        (key for key in state["projects"] if key.lower() == project_ref.lower()),
        None,
    )

    row_index = _project_row_reference_index(project_ref)
    row_match: str | None = None
    project_keys = list(state["projects"].keys())
    if row_index is not None and 1 <= row_index <= len(project_keys):
        row_match = project_keys[row_index - 1]

    if exact_match is not None and row_match is not None and exact_match != row_match:
        raise ValueError(
            f'Project reference "{project_ref}" is ambiguous in the diary for the week of '
            f"{get_week_label(week_key)}. It matches both the literal project name "
            f'"{exact_match}" and row {row_index} ("{row_match}"). Please clarify which '
            "project you meant."
        )

    resolved = exact_match or row_match
    if resolved is not None:
        return resolved

    if row_index is not None:
        raise ValueError(
            f"Project index {row_index} is out of range — "
            f"there {'is' if len(project_keys) == 1 else 'are'} "
            f"{len(project_keys)} project{'s' if len(project_keys) != 1 else ''} "
            f"in the diary for the week of {get_week_label(week_key)}."
        )

    raise ValueError(
        f'Project "{project_ref}" not found in the diary for the week of '
        f"{get_week_label(week_key)}."
    )


def _resolve_project_key_for_update(
    state: DiaryState, week_key: str, project_ref: str
) -> str | None:
    """Resolve a project reference for update operations.

    Returns an existing key when one can be resolved. Returns ``None`` when the
    reference does not identify an existing project and should be treated as a
    new literal project name, including positive out-of-range row-style
    references such as ``project 9``.

    Raises:
        ValueError: If the project reference is ambiguous or if a row reference
        is non-positive, such as ``project 0``.
    """
    exact_match = next(
        (key for key in state["projects"] if key.lower() == project_ref.lower()),
        None,
    )
    row_index = _project_row_reference_index(project_ref)
    project_keys = list(state["projects"].keys())

    if exact_match is not None:
        row_match: str | None = None
        if row_index is not None and 1 <= row_index <= len(project_keys):
            row_match = project_keys[row_index - 1]
        if row_match is not None and row_match != exact_match:
            raise ValueError(
                f'Project reference "{project_ref}" is ambiguous in the diary for the week of '
                f"{get_week_label(week_key)}. It matches both the literal project name "
                f'"{exact_match}" and row {row_index} ("{row_match}"). Please clarify which '
                "project you meant."
            )
        return exact_match

    if row_index is not None:
        if row_index < 1:
            raise ValueError(
                f"Project index {row_index} is out of range — "
                f"there {'is' if len(project_keys) == 1 else 'are'} "
                f"{len(project_keys)} project{'s' if len(project_keys) != 1 else ''} "
                f"in the diary for the week of {get_week_label(week_key)}."
            )
        if row_index <= len(project_keys):
            return project_keys[row_index - 1]
        return None

    return None


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
        project:     Project name or row reference (e.g. 'project 2').
        status:      New status string.
        note:        Note text to set or append.
        append_note: When True and a note already exists, the new note is
                     appended (separated by " — ") rather than replacing it.
                     Has no effect when no prior note exists.
    """
    with _week_lock(week_key):
        state = _load_state(week_key)

        existing_key = _resolve_project_key_for_update(state, week_key, project)
        key = existing_key or linkify_jira_refs(project)
        state["projects"][key] = status

        if note is not None:
            linkified_note = linkify_jira_refs(note)
            if append_note and key in state["projectNotes"]:
                state["projectNotes"][key] = state["projectNotes"][key] + " — " + linkified_note
            else:
                state["projectNotes"][key] = linkified_note

        _save_state(state)


def rename_project(week_key: str, old_name: str, new_name: str) -> None:
    """Rename a project, preserving its status and note.

    Raises ValueError if *old_name* is not found, or if *new_name* already
    exists (case-insensitive) as a different project.
    """
    with _week_lock(week_key):
        state = _load_state(week_key)

        old_key = _resolve_existing_project_key(state, week_key, old_name)

        # Prevent collisions with an existing different project
        collision = next(
            (k for k in state["projects"] if k.lower() == new_name.lower() and k != old_key),
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
            (linked_new_name if k == old_key else k): v for k, v in state["projects"].items()
        }
        state["projectNotes"] = {
            (linked_new_name if k == old_key else k): v for k, v in state["projectNotes"].items()
        }

        _save_state(state)


def bulk_update_projects(
    week_key: str,
    updates: list[ProjectUpdate],
) -> list[str]:
    """Update multiple projects in a single read-modify-write cycle.

    Each item in *updates* must have:
        project     (str)           — project name
        status      (str)           — new status
        note        (str | None)    — optional note (default: None)
        append_note (bool)          — append vs. replace note (default: False)

    Returns a list of human-readable result strings, one per project.
    """
    with _week_lock(week_key):
        state = _load_state(week_key)
        results: list[str] = []

        for item in updates:
            project = item["project"]
            status = item["status"]
            note = item.get("note")
            append_note = bool(item.get("append_note", False))

            existing_key = _resolve_project_key_for_update(state, week_key, project)
            key = existing_key or linkify_jira_refs(project)

            state["projects"][key] = status

            if note is not None:
                linkified_note = linkify_jira_refs(note)
                if append_note and key in state["projectNotes"]:
                    state["projectNotes"][key] = state["projectNotes"][key] + " — " + linkified_note
                else:
                    state["projectNotes"][key] = linkified_note

            results.append(f"{key} → {status}")

        _save_state(state)
        return results


def remove_project(week_key: str, project: str) -> None:
    """Remove a project and its note from the diary."""
    with _week_lock(week_key):
        state = _load_state(week_key)

        existing_key = _resolve_existing_project_key(state, week_key, project)

        del state["projects"][existing_key]
        state["projectNotes"].pop(existing_key, None)
        _save_state(state)


def clear_project_note(week_key: str, project: str) -> None:
    """Clear the inline note for a project, leaving its status intact."""
    with _week_lock(week_key):
        state = _load_state(week_key)

        existing_key = _resolve_existing_project_key(state, week_key, project)

        state["projectNotes"].pop(existing_key, None)
        _save_state(state)


def add_note(week_key: str, content: str) -> None:
    """Append a note to the general notes section.

    No automatic timestamp is stored. If the content contains an explicit
    date or time reference it is preserved as-is within the content string.
    """
    with _week_lock(week_key):
        state = _load_state(week_key)
        entry: NoteEntry = {"content": linkify_jira_refs(content)}
        state["notes"].append(entry)
        _save_state(state)


def edit_note(week_key: str, index: int, new_content: str) -> None:
    """Replace the content of an existing note.

    *index* is 1-based (as shown to the user).  Raises ValueError if out
    of range.  Any legacy ``timestamp`` field on the entry is left intact
    so that old diary files can be loaded and saved without losing data.
    """
    with _week_lock(week_key):
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
    with _week_lock(week_key):
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
    """Render the diary as Markdown and return it without writing files."""
    from work_diary_mcp.markdown import render_diary

    normalized_week_key = get_week_key(date.fromisoformat(week_key))
    state = _load_state(normalized_week_key)
    reminder_state = _load_reminder_state()
    reminders = reminder_state["reminders"].get(normalized_week_key, [])
    render_state = {
        **state,
        "reminders": reminders,
    }
    return render_diary(render_state)


def list_projects(week_key: str) -> dict[str, str]:
    """Return the projects dict for the given week."""
    return _load_state(week_key)["projects"]


def list_week_keys() -> list[str]:
    """Return all week keys found in the data directory, sorted ascending."""
    return sorted(
        p.stem for p in get_data_dir().glob("*.json") if re.match(r"^\d{4}-\d{2}-\d{2}$", p.stem)
    )
