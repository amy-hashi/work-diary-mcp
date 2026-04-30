import copy
import json
import os
import re
import tempfile
import threading
from collections import OrderedDict
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import NotRequired, TypedDict

from work_diary_mcp.config import get_data_dir
from work_diary_mcp.jira import linkify_jira_refs
from work_diary_mcp.roles import format_role
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
    projectRoles: dict[str, str]
    notes: list[NoteEntry]


class ReminderState(TypedDict):
    reminders: dict[str, list[ReminderEntry]]


class ProjectUpdate(TypedDict):
    project: str
    status: str
    note: NotRequired[str | None]
    append_note: NotRequired[bool]
    role: NotRequired[str | None]


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
    return {
        "weekKey": week_key,
        "projects": {},
        "projectNotes": {},
        "projectRoles": {},
        "notes": [],
    }


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

    project_roles = state.get("projectRoles")
    if project_roles is None:
        project_roles = {}
        state["projectRoles"] = project_roles
    if not isinstance(project_roles, dict):
        raise ValueError("Diary state field 'projectRoles' must be an object.")
    for project, role in project_roles.items():
        if not isinstance(project, str) or not isinstance(role, str):
            raise ValueError("Diary state field 'projectRoles' must map strings to strings.")

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
    state.setdefault("projectRoles", {})

    # Linkify project keys and their notes.  We rebuild all three dicts
    # together so the key used in projectNotes and projectRoles stays in
    # sync with the key in projects.
    old_projects: dict[str, str] = state["projects"]
    old_notes: dict[str, str] = state["projectNotes"]
    old_roles: dict[str, str] = state["projectRoles"]
    new_projects: dict[str, str] = {}
    new_notes: dict[str, str] = {}
    new_roles: dict[str, str] = {}
    for key, status in old_projects.items():
        new_key = linkify_jira_refs(key)
        new_projects[new_key] = status
        if key in old_notes:
            new_notes[new_key] = linkify_jira_refs(old_notes[key])
        if key in old_roles:
            # Role values are normalized via format_role on write, but
            # re-normalize here so any legacy raw values left over from
            # earlier migrations end up in the canonical display form.
            new_roles[new_key] = format_role(old_roles[key])
    state["projects"] = new_projects
    state["projectNotes"] = new_notes
    state["projectRoles"] = new_roles

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


# --------------------------------------------------------------------------- #
# In-process caches and locks
# --------------------------------------------------------------------------- #

# Per-week threading locks use a fixed-size stripe array rather than a
# growing dict keyed by week_key. This bounds memory to a constant
# regardless of how many distinct historical weeks the server touches
# over its lifetime, and avoids the correctness pitfall of evicting a
# lock that another thread might still be holding (which would silently
# break mutual exclusion when a fresh lock instance is created for the
# same week_key).
#
# Two threads acting on the same week_key always map to the same stripe
# (mutual exclusion preserved). Two threads acting on different week_keys
# that hash to the same stripe will occasionally contend with each other,
# but this server's per-call work is sub-millisecond and concurrent tool
# invocations are rare, so the false-sharing cost is negligible.
_WEEK_LOCK_STRIPES: int = 64
_WEEK_THREADING_LOCKS: tuple[threading.Lock, ...] = tuple(
    threading.Lock() for _ in range(_WEEK_LOCK_STRIPES)
)
_REMINDER_THREADING_LOCK = threading.Lock()

# Guards all reads, writes, and eviction sweeps over ``_ENSURED_PAGES``.
# A dedicated lock keeps the short-circuit safe under concurrent tool
# calls without blocking on any per-week or reminder lock.
_ENSURED_PAGES_LOCK = threading.Lock()

# Parsed-state caches keyed by file path. The cached value is a tuple of
# ``(fingerprint, deep-copied state)`` where ``fingerprint`` is
# ``(st_mtime_ns, st_size)``. Entries are returned as deep copies so
# callers can freely mutate the returned dict without corrupting the
# cache, and the cache is invalidated when either field changes — which
# catches both ordinary external edits (mtime bumps) and the realistic
# defense-in-depth case where a tool preserves or restores mtime
# (``cp -p``, ``rsync --times``, restoring from backup, ``os.utime``,
# etc.) but the replacement file's size differs.
#
# Each cache is an ``OrderedDict`` used as an LRU: on every access (read
# hit or write) the entry is moved to the most-recently-used end, and
# inserts beyond the configured maximum evict the least-recently-used
# entry. This bounds memory usage on long-running servers that touch
# many historical weeks. Reminder state has only ever one entry in
# practice (a single ``reminders.json``) but uses the same machinery for
# symmetry. All access is serialized by ``_STATE_CACHE_LOCK`` /
# ``_REMINDER_STATE_CACHE_LOCK`` so the LRU ordering and eviction stay
# consistent under concurrent tool calls.
_STATE_CACHE_MAX_ENTRIES: int = 32
_REMINDER_STATE_CACHE_MAX_ENTRIES: int = 4
_StateFingerprint = tuple[int, int]
_STATE_CACHE: "OrderedDict[Path, tuple[_StateFingerprint, DiaryState]]" = OrderedDict()
_REMINDER_STATE_CACHE: "OrderedDict[Path, tuple[_StateFingerprint, ReminderState]]" = OrderedDict()
_STATE_CACHE_LOCK = threading.Lock()
_REMINDER_STATE_CACHE_LOCK = threading.Lock()


def _stat_fingerprint(path: Path) -> _StateFingerprint | None:
    """Return a ``(mtime_ns, size)`` fingerprint for *path*, or None on error."""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


# Memoized "this page already exists on disk" results for
# :func:`_ensure_week_page`, keyed by ``(today's ISO date, week_key)``.
# Avoids re-acquiring locks and re-stat'ing the diary file on every tool
# call within the same day.
_ENSURED_PAGES: dict[tuple[str, str], dict] = {}


def _file_locks_enabled() -> bool:
    """Return True if filesystem locks should be acquired in addition to
    in-process threading locks.

    Off by default for performance. Set ``WORK_DIARY_FILE_LOCKS=1`` (or
    any truthy value) to enable, which is needed only when multiple
    processes may write to the same data directory.
    """
    raw = os.environ.get("WORK_DIARY_FILE_LOCKS", "").strip().lower()
    return raw not in ("", "0", "false", "no", "off")


def _get_week_threading_lock(week_key: str) -> threading.Lock:
    """Return the per-week in-process lock for *week_key*.

    Uses a fixed-size lock-stripe array indexed by ``hash(week_key)`` so
    the lock registry never grows. Two calls with the same ``week_key``
    always return the same lock object, preserving mutual exclusion.
    Different ``week_key`` values may occasionally collide on the same
    stripe; given sub-millisecond per-call work and effectively no
    concurrent tool invocations on this server, the resulting false
    sharing is negligible.
    """
    return _WEEK_THREADING_LOCKS[hash(week_key) % _WEEK_LOCK_STRIPES]


def _reset_caches() -> None:
    """Clear all in-process caches.

    Stripe locks are not reset — they are stateless when not held, and
    re-creating them mid-test could break mutual exclusion if any code
    were holding a reference to the old instance.

    Intended for tests that swap data directories between cases.
    """
    with _STATE_CACHE_LOCK:
        _STATE_CACHE.clear()
    with _REMINDER_STATE_CACHE_LOCK:
        _REMINDER_STATE_CACHE.clear()
    with _ENSURED_PAGES_LOCK:
        _ENSURED_PAGES.clear()


def _cache_state(path: Path, state: DiaryState) -> None:
    """Refresh the parsed-state cache after a successful save.

    Marks the entry as most-recently-used and evicts the
    least-recently-used entry if the cache would exceed
    ``_STATE_CACHE_MAX_ENTRIES``.

    Note: this fingerprints *path* after the rename has already landed.
    Under the documented single-writer assumption (the default; see
    ``WORK_DIARY_FILE_LOCKS`` for multi-writer deployments) the file on
    disk corresponds exactly to *state*. If a concurrent external writer
    were to replace the file between the rename and this stat call, the
    cached fingerprint could end up associated with their content rather
    than ours; defending against that fully would require holding a
    file lock around the entire write+stat sequence, which is exactly
    what enabling ``WORK_DIARY_FILE_LOCKS`` provides.
    """
    fingerprint = _stat_fingerprint(path)
    if fingerprint is None:
        return
    snapshot = copy.deepcopy(state)
    with _STATE_CACHE_LOCK:
        _STATE_CACHE[path] = (fingerprint, snapshot)
        _STATE_CACHE.move_to_end(path)
        while len(_STATE_CACHE) > _STATE_CACHE_MAX_ENTRIES:
            _STATE_CACHE.popitem(last=False)


def _cache_reminder_state(path: Path, state: ReminderState) -> None:
    """Refresh the parsed reminder-state cache after a successful save.

    Marks the entry as most-recently-used and evicts the
    least-recently-used entry if the cache would exceed
    ``_REMINDER_STATE_CACHE_MAX_ENTRIES``.

    The same single-writer assumption documented on :func:`_cache_state`
    applies here: this fingerprints *path* after the rename, and under
    multi-writer deployments callers should enable
    ``WORK_DIARY_FILE_LOCKS`` so the entire write+stat sequence is
    serialized at the filesystem level.
    """
    fingerprint = _stat_fingerprint(path)
    if fingerprint is None:
        return
    snapshot = copy.deepcopy(state)
    with _REMINDER_STATE_CACHE_LOCK:
        _REMINDER_STATE_CACHE[path] = (fingerprint, snapshot)
        _REMINDER_STATE_CACHE.move_to_end(path)
        while len(_REMINDER_STATE_CACHE) > _REMINDER_STATE_CACHE_MAX_ENTRIES:
            _REMINDER_STATE_CACHE.popitem(last=False)


def _atomic_write_text(path: Path, content: str) -> None:
    """Atomically write text content to *path*.

    Uses a tempfile + rename for application-level atomicity. We do not
    call ``os.fsync`` here: the diary is a personal productivity tool, and
    the rename already protects against partial writes for the failure
    modes we actually care about (process crash, concurrent reads). The
    fsync was previously the dominant per-call latency on macOS APFS.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = path.stat().st_mode if path.exists() else None
    fd, temp_path_str = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp_path = Path(temp_path_str)
    try:
        if existing_mode is not None and hasattr(os, "fchmod"):
            os.fchmod(fd, existing_mode & 0o777)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        temp_path.replace(path)
    finally:
        # Use missing_ok=True so a race with an external cleanup (or the
        # successful rename above, which moves temp_path away) does not
        # raise here. This avoids a TOCTOU window between exists() and
        # unlink() that could otherwise surface as a spurious error.
        temp_path.unlink(missing_ok=True)


@contextmanager
def _week_lock(week_key: str):
    """Take an exclusive lock for a week's diary state.

    Always acquires the in-process per-week threading lock. Additionally
    acquires a filesystem lock when ``WORK_DIARY_FILE_LOCKS`` is enabled,
    which is needed only for multi-process safety.
    """
    threading_lock = _get_week_threading_lock(week_key)
    threading_lock.acquire()
    try:
        if not _file_locks_enabled():
            yield
            return

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
    finally:
        threading_lock.release()


@contextmanager
def _reminder_lock():
    """Take an exclusive lock for reminder state.

    Always acquires the in-process reminder threading lock. Additionally
    acquires a filesystem lock when ``WORK_DIARY_FILE_LOCKS`` is enabled.
    """
    _REMINDER_THREADING_LOCK.acquire()
    try:
        if not _file_locks_enabled():
            yield
            return

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
    finally:
        _REMINDER_THREADING_LOCK.release()


def _load_state(week_key: str) -> DiaryState:
    path = _diary_path(week_key)
    if not path.exists():
        # Drop any stale cache entry whose underlying file has been
        # deleted externally so the cache cannot grow indefinitely with
        # references to no-longer-existing weeks.
        with _STATE_CACHE_LOCK:
            _STATE_CACHE.pop(path, None)
        return _empty_state(week_key)

    pre_read_fingerprint = _stat_fingerprint(path)

    with _STATE_CACHE_LOCK:
        cached = _STATE_CACHE.get(path)
        if (
            cached is not None
            and pre_read_fingerprint is not None
            and cached[0] == pre_read_fingerprint
        ):
            _STATE_CACHE.move_to_end(path)
            return copy.deepcopy(cached[1])

    raw_state = json.loads(path.read_text(encoding="utf-8"))
    validated = _validate_state(raw_state, week_key)
    migrated = _migrate_state(validated)

    # Re-stat after the read and only cache when the fingerprint is
    # stable across the read. Otherwise the file could have been
    # rewritten between our pre-read stat and the read itself, which
    # would associate the pre-read fingerprint with content that
    # actually came from a later revision and let a subsequent reader
    # get a cache hit on a fingerprint that does not correspond to the
    # cached state. Skipping the cache populate in that case is safe:
    # the next call will re-read and try again.
    post_read_fingerprint = _stat_fingerprint(path)
    if (
        pre_read_fingerprint is not None
        and post_read_fingerprint is not None
        and pre_read_fingerprint == post_read_fingerprint
    ):
        snapshot = copy.deepcopy(migrated)
        with _STATE_CACHE_LOCK:
            _STATE_CACHE[path] = (post_read_fingerprint, snapshot)
            _STATE_CACHE.move_to_end(path)
            while len(_STATE_CACHE) > _STATE_CACHE_MAX_ENTRIES:
                _STATE_CACHE.popitem(last=False)
    return migrated


def _load_reminder_state() -> ReminderState:
    path = _reminders_path()
    if not path.exists():
        with _REMINDER_STATE_CACHE_LOCK:
            _REMINDER_STATE_CACHE.pop(path, None)
        return _empty_reminder_state()

    pre_read_fingerprint = _stat_fingerprint(path)

    with _REMINDER_STATE_CACHE_LOCK:
        cached = _REMINDER_STATE_CACHE.get(path)
        if (
            cached is not None
            and pre_read_fingerprint is not None
            and cached[0] == pre_read_fingerprint
        ):
            _REMINDER_STATE_CACHE.move_to_end(path)
            return copy.deepcopy(cached[1])

    raw_state = json.loads(path.read_text(encoding="utf-8"))
    validated = _validate_reminder_state(raw_state)
    migrated = _migrate_reminder_state(validated)

    # Re-stat after the read and only cache when the fingerprint is
    # stable across the read; see _load_state for the rationale.
    post_read_fingerprint = _stat_fingerprint(path)
    if (
        pre_read_fingerprint is not None
        and post_read_fingerprint is not None
        and pre_read_fingerprint == post_read_fingerprint
    ):
        snapshot = copy.deepcopy(migrated)
        with _REMINDER_STATE_CACHE_LOCK:
            _REMINDER_STATE_CACHE[path] = (post_read_fingerprint, snapshot)
            _REMINDER_STATE_CACHE.move_to_end(path)
            while len(_REMINDER_STATE_CACHE) > _REMINDER_STATE_CACHE_MAX_ENTRIES:
                _REMINDER_STATE_CACHE.popitem(last=False)
    return migrated


def _save_reminder_state(state: ReminderState, refresh_week_keys: set[str] | None = None) -> None:
    validated = _validate_reminder_state(state)
    # Cache the migrated form so cache hits return the same shape as a
    # fresh disk load (which always passes through ``_migrate_reminder_state``).
    # Without this, a cached read could return a structurally different state
    # than a non-cached read of the same data.
    migrated = _migrate_reminder_state(validated)
    json_content = json.dumps(migrated, indent=2, ensure_ascii=False)
    reminders_path = _reminders_path()
    _atomic_write_text(reminders_path, json_content)
    _cache_reminder_state(reminders_path, migrated)

    for week_key in refresh_week_keys or set():
        diary_path = _diary_path(week_key)
        if diary_path.exists():
            with _week_lock(week_key):
                reminders_for_week = migrated["reminders"].get(week_key, [])
                _save_state(_load_state(week_key), reminders=reminders_for_week)


def _save_state(state: DiaryState, reminders: list[ReminderEntry]) -> None:
    """Persist diary state and rendered Markdown for a week.

    *reminders* must be supplied by the caller. Callers acquiring both the
    reminder and week locks must do so via :func:`_week_write` (or in the
    canonical reminder→week order) to avoid deadlock with reminder-driven
    refresh paths.
    """
    from work_diary_mcp.markdown import render_diary  # avoid circular import

    validated = _validate_state(state)
    # Cache the migrated form so cache hits return the same shape as a
    # fresh disk load (which always passes through ``_migrate_state``).
    migrated = _migrate_state(validated)
    week_key = migrated["weekKey"]

    json_content = json.dumps(migrated, indent=2, ensure_ascii=False)
    markdown_content = render_diary(
        {
            **migrated,
            "reminders": reminders,
        }
    )

    diary_path = _diary_path(week_key)
    _atomic_write_text(diary_path, json_content)
    _atomic_write_text(_markdown_path(week_key), markdown_content)
    _cache_state(diary_path, migrated)


@contextmanager
def _week_write(week_key: str):
    """Acquire both the reminder and week locks in canonical order.

    Always takes ``_reminder_lock`` before ``_week_lock(week_key)`` so that
    week-update paths and reminder-update paths share a single global lock
    ordering. This eliminates the AB/BA deadlock that would otherwise occur
    if a week-write tried to acquire the reminder lock from underneath the
    week lock while a concurrent reminder-write held the locks in the
    opposite order.

    Yields the reminders snapshot for *week_key*, loaded under the reminder
    lock, so callers can pass it directly to :func:`_save_state` without
    re-reading reminder state.
    """
    with _reminder_lock():
        reminder_state = _load_reminder_state()
        reminders = list(reminder_state["reminders"].get(week_key, []))
        with _week_lock(week_key):
            yield reminders


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
        return {"projects": {}, "projectNotes": {}, "projectRoles": {}}
    last = _load_state(weeks[-1])

    projects: dict[str, str] = {}
    project_roles: dict[str, str] = {}
    last_roles = last.get("projectRoles", {})
    for project, status in last["projects"].items():
        if not is_completed(status):
            projects[project] = status
            if project in last_roles:
                project_roles[project] = last_roles[project]

    return {"projects": projects, "projectNotes": {}, "projectRoles": project_roles}


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

    Uses an in-process cache keyed by ``(today, week_key)`` so repeated tool
    calls within the same day skip the lock acquisition and existence
    check entirely once the page is known to exist. The cache is validated
    against the diary file on disk on each lookup so external deletions are
    handled correctly, and entries from prior days are evicted whenever a
    new entry is recorded so the cache cannot grow without bound across
    long-running server sessions.
    """
    week_label = get_week_label(week_key)
    today_iso = date.today().isoformat()
    cache_key = (today_iso, week_key)

    with _ENSURED_PAGES_LOCK:
        cached = _ENSURED_PAGES.get(cache_key)
        if cached is not None:
            # Defensive re-check: if the diary file was deleted externally
            # since we cached this entry, fall through and recreate the
            # page rather than returning a stale "exists" result.
            if _diary_path(week_key).exists():
                return dict(cached)
            _ENSURED_PAGES.pop(cache_key, None)

    is_new = False

    with _week_write(week_key) as reminders:
        if not _diary_path(week_key).exists():
            initial_state = (
                _get_carry_forward_state(week_key)
                if carry_forward
                else {"projects": {}, "projectNotes": {}, "projectRoles": {}}
            )
            _save_state(
                {
                    "weekKey": week_key,
                    "projects": initial_state["projects"],
                    "projectNotes": initial_state["projectNotes"],
                    "projectRoles": initial_state.get("projectRoles", {}),
                    "notes": [],
                },
                reminders=reminders,
            )
            is_new = True

    result = {"week_key": week_key, "week_label": week_label, "is_new": is_new}
    with _ENSURED_PAGES_LOCK:
        # Evict any entries from prior days before recording today's entry
        # so the cache stays bounded to at most one entry per active week
        # for the current day.
        stale_keys = [key for key in _ENSURED_PAGES if key[0] != today_iso]
        for key in stale_keys:
            _ENSURED_PAGES.pop(key, None)
        # Subsequent same-day calls should report ``is_new=False`` because
        # the page now exists on disk; cache that form rather than the
        # first-call result.
        _ENSURED_PAGES[cache_key] = {**result, "is_new": False}
    return result


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

    Historical weeks are created empty rather than carrying forward state. If
    the supplied week resolves to the current week, carry-forward behavior is
    applied so direct callers don't accidentally bypass it.
    """
    normalized_week_key = get_week_key(date.fromisoformat(week_key))
    carry_forward = normalized_week_key == get_week_key()
    return _ensure_week_page(normalized_week_key, carry_forward=carry_forward)


def _project_row_reference_index(project_ref: str) -> int | None:
    """Return the 1-based row index for a project reference like 'project 2'."""
    match = re.fullmatch(r"\s*project\s+(\d+)\s*", project_ref, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _project_index_out_of_range_error(
    week_key: str, row_index: int, project_count: int
) -> ValueError:
    """Build a consistent out-of-range error for project row references."""
    return ValueError(
        f"Project index {row_index} is out of range — "
        f"there {'is' if project_count == 1 else 'are'} "
        f"{project_count} project{'s' if project_count != 1 else ''} "
        f"in the diary for the week of {get_week_label(week_key)}."
    )


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

    if row_index is not None and row_index < 1:
        raise _project_index_out_of_range_error(week_key, row_index, len(project_keys))

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
        raise _project_index_out_of_range_error(week_key, row_index, len(project_keys))

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

    if row_index is not None and row_index < 1:
        raise _project_index_out_of_range_error(week_key, row_index, len(project_keys))

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
    role: str | None = None,
) -> None:
    """Update (or add) a project's status, and optionally its inline note or role.

    Args:
        week_key:    The week to update.
        project:     Project name or row reference (e.g. 'project 2').
        status:      New status string.
        note:        Note text to set or append.
        append_note: When True and a note already exists, the new note is
                     appended (separated by " — ") rather than replacing it.
                     Has no effect when no prior note exists.
        role:        Role for the project (e.g. 'Sponsor', ':rocket:', '🚀').
                     Pass an empty string to clear a previously-set role.
                     Pass ``None`` (the default) to leave any existing role
                     untouched.
    """
    with _week_write(week_key) as reminders:
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

        if role is not None:
            formatted_role = format_role(role)
            if formatted_role:
                state["projectRoles"][key] = formatted_role
            else:
                state["projectRoles"].pop(key, None)

        _save_state(state, reminders=reminders)


def rename_project(week_key: str, old_name: str, new_name: str) -> None:
    """Rename a project, preserving its status and note.

    Raises ValueError if *old_name* is not found, or if *new_name* already
    exists (case-insensitive) as a different project.
    """
    with _week_write(week_key) as reminders:
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
        state["projectRoles"] = {
            (linked_new_name if k == old_key else k): v for k, v in state["projectRoles"].items()
        }

        _save_state(state, reminders=reminders)


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
    with _week_write(week_key) as reminders:
        state = _load_state(week_key)
        results: list[str] = []

        for item in updates:
            project = item["project"]
            status = item["status"]
            note = item.get("note")
            append_note = bool(item.get("append_note", False))
            role = item.get("role")

            existing_key = _resolve_project_key_for_update(state, week_key, project)
            key = existing_key or linkify_jira_refs(project)

            state["projects"][key] = status

            if note is not None:
                linkified_note = linkify_jira_refs(note)
                if append_note and key in state["projectNotes"]:
                    state["projectNotes"][key] = state["projectNotes"][key] + " — " + linkified_note
                else:
                    state["projectNotes"][key] = linkified_note

            if role is not None:
                formatted_role = format_role(role)
                if formatted_role:
                    state["projectRoles"][key] = formatted_role
                else:
                    state["projectRoles"].pop(key, None)

            results.append(f"{key} → {status}")

        _save_state(state, reminders=reminders)
        return results


def remove_project(week_key: str, project: str) -> None:
    """Remove a project and its note from the diary."""
    with _week_write(week_key) as reminders:
        state = _load_state(week_key)

        existing_key = _resolve_existing_project_key(state, week_key, project)

        del state["projects"][existing_key]
        state["projectNotes"].pop(existing_key, None)
        state["projectRoles"].pop(existing_key, None)
        _save_state(state, reminders=reminders)


def set_project_role(week_key: str, project: str, role: str) -> None:
    """Set or clear the role for an existing project.

    Args:
        week_key: The week to update.
        project:  Project name or row reference (e.g. 'project 2'). The
                  project must already exist in the target week.
        role:     Role label. Accepts canonical names (``'Sponsor'``),
                  emoji shortcodes (``':rocket:'``), bare emoji
                  (``'🚀'``), or already-formatted display values
                  (``'🚀 Sponsor'``). Pass an empty string to clear a
                  previously-set role.
    """
    with _week_write(week_key) as reminders:
        state = _load_state(week_key)
        existing_key = _resolve_existing_project_key(state, week_key, project)

        formatted_role = format_role(role)
        if formatted_role:
            state["projectRoles"][existing_key] = formatted_role
        else:
            state["projectRoles"].pop(existing_key, None)

        _save_state(state, reminders=reminders)


def clear_project_note(week_key: str, project: str) -> None:
    """Clear the inline note for a project, leaving its status intact."""
    with _week_write(week_key) as reminders:
        state = _load_state(week_key)

        existing_key = _resolve_existing_project_key(state, week_key, project)

        state["projectNotes"].pop(existing_key, None)
        _save_state(state, reminders=reminders)


def add_note(week_key: str, content: str) -> None:
    """Append a note to the general notes section.

    No automatic timestamp is stored. If the content contains an explicit
    date or time reference it is preserved as-is within the content string.
    """
    with _week_write(week_key) as reminders:
        state = _load_state(week_key)
        entry: NoteEntry = {"content": linkify_jira_refs(content)}
        state["notes"].append(entry)
        _save_state(state, reminders=reminders)


def edit_note(week_key: str, index: int, new_content: str) -> None:
    """Replace the content of an existing note.

    *index* is 1-based (as shown to the user).  Raises ValueError if out
    of range.  Any legacy ``timestamp`` field on the entry is left intact
    so that old diary files can be loaded and saved without losing data.
    """
    with _week_write(week_key) as reminders:
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
        _save_state(state, reminders=reminders)


def delete_note(week_key: str, index: int) -> str:
    """Delete a note by its 1-based index.

    Returns the content of the deleted note.  Raises ValueError if the
    index is out of range.
    """
    with _week_write(week_key) as reminders:
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
        _save_state(state, reminders=reminders)
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
    """Return the projects dict for the given week.

    The supplied week key may be any ISO date within the target week; it is
    normalized to that week's Monday before lookup.
    """
    normalized_week_key = get_week_key(date.fromisoformat(week_key))
    return _load_state(normalized_week_key)["projects"]


def list_week_keys() -> list[str]:
    """Return all week keys found in the data directory, sorted ascending."""
    return sorted(
        p.stem for p in get_data_dir().glob("*.json") if re.match(r"^\d{4}-\d{2}-\d{2}$", p.stem)
    )
