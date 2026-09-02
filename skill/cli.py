#!/usr/bin/env python3
"""
work-diary CLI — a thin command-line wrapper around the work-diary-mcp
library (~/work-diary-mcp/python/work_diary_mcp).

This exists so the work diary can be read/updated without going through the
MCP server/protocol. It imports the exact same business-logic modules the
MCP server uses (diary.py, config.py, roles.py, statuses.py, jira.py,
markdown.py), so behavior (week-key parsing, carry-forward, Jira
linkification, role/status formatting, auto-sync, file locking) is
identical to the MCP tools.

Usage examples:
    cli.py get-diary [--date DATE]
    cli.py list-projects [--date DATE]
    cli.py list-weeks
    cli.py update-status --project NAME --status STATUS [--note TEXT]
                          [--append-note] [--role ROLE] [--date DATE]
    cli.py bulk-update --json '[{"project": "...", "status": "..."}]' [--date DATE]
    cli.py set-role --project NAME --role ROLE [--date DATE]
    cli.py rename-project --old OLD --new NEW [--date DATE]
    cli.py remove-project --project NAME [--date DATE]
    cli.py clear-note --project NAME [--date DATE]
    cli.py add-note --content TEXT [--date DATE]
    cli.py edit-note --index N --content TEXT [--date DATE]
    cli.py delete-note --index N [--date DATE]
    cli.py add-reminder --content TEXT [--due-date DUE] [--date DATE]
    cli.py list-reminders [--date DATE]
    cli.py complete-reminder --index N [--date DATE]
    cli.py reopen-reminder --index N [--date DATE]
    cli.py push-sync [--date DATE]

All commands print a human-readable confirmation (or JSON, for list
commands with --json) and exit 0 on success, or print "Error: ..." to
stderr and exit 1 on failure.

Configuration (env vars, same as the MCP server):
    WORK_DIARY_DATA_DIR, WORK_DIARY_JIRA_BASE_URL, WORK_DIARY_JIRA_PREFIXES,
    WORK_DIARY_SYNC_PATH, WORK_DIARY_AUTO_SYNC
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Locate the work-diary-mcp library and add it to sys.path. The library has
# no third-party dependencies (fastmcp is only used by the server entrypoint),
# so plain stdlib Python 3.11+ is sufficient.
_LIB_DIR = Path.home() / "work-diary-mcp" / "python"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

try:
    from work_diary_mcp import diary
except ImportError as e:  # pragma: no cover
    print(
        f"Error: could not import work_diary_mcp from {_LIB_DIR} ({e}). "
        "Is ~/work-diary-mcp checked out?",
        file=sys.stderr,
    )
    sys.exit(1)


def _resolve_target_page(date: str | None) -> dict:
    """Mirror server._resolve_target_page: resolve/create the target week page."""
    if not date:
        return diary.get_or_create_week_page()
    week_key = diary.parse_week_key(date)
    return (
        diary.get_or_create_week_page()
        if week_key == diary.get_week_key()
        else diary.get_or_create_page_for_week(week_key)
    )


def _week_key_for(date: str | None) -> str:
    return diary.parse_week_key(date) if date else diary.get_week_key()


def _maybe_auto_sync(week_key: str) -> None:
    """Best-effort auto-sync, mirroring server._maybe_auto_sync."""
    from work_diary_mcp.config import get_auto_sync, get_sync_path

    try:
        if not get_auto_sync():
            return
        sync_path = get_sync_path()
        if sync_path is None:
            return
        _copy_week_to_sync_folder(week_key, sync_path)
    except Exception:
        pass


def _copy_week_to_sync_folder(week_key: str, sync_path: Path) -> Path:
    import os
    import tempfile

    if sync_path.exists() and not sync_path.is_dir():
        raise ValueError(f"Configured sync path `{sync_path}` exists but is not a directory.")
    sync_path.mkdir(parents=True, exist_ok=True)
    dest = sync_path / f"{week_key}.md"
    if dest.exists() and not dest.is_file():
        raise ValueError(f"Destination path `{dest}` exists but is not a file.")

    content = diary.get_diary_markdown(week_key)
    existing_mode = dest.stat().st_mode if dest.exists() else None
    fd, temp_path_str = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".tmp")
    temp_path = Path(temp_path_str)
    try:
        if existing_mode is not None and hasattr(os, "fchmod"):
            os.fchmod(fd, existing_mode & 0o777)
        with os.fdopen(fd, "w", encoding="utf-8-sig") as fh:
            fd = -1
            fh.write(content)
        temp_path.replace(dest)
    finally:
        if fd != -1:
            os.close(fd)
        temp_path.unlink(missing_ok=True)
    return dest


def cmd_get_diary(args):
    week_key = _week_key_for(args.date)
    label = diary.get_week_label(week_key)
    print(f"Work diary for the week of {label}:\n")
    print(diary.get_diary_markdown(week_key))


def cmd_list_projects(args):
    week_key = _week_key_for(args.date)
    label = diary.get_week_label(week_key)
    projects = diary.list_projects(week_key)
    if args.json:
        print(json.dumps(projects, indent=2))
        return
    if not projects:
        print(f"No projects tracked yet for the week of {label}.")
        return
    print(f"Projects for the week of {label}:\n")
    for p, s in projects.items():
        print(f"- {p}: {s}")


def cmd_list_weeks(args):
    weeks = diary.list_week_keys()
    if args.json:
        print(json.dumps(weeks, indent=2))
        return
    if not weeks:
        print("No diary entries found yet.")
        return
    print(f"Found {len(weeks)} week(s) with diary entries:\n")
    for k in weeks:
        print(f"- {diary.get_week_label(k)} ({k})")


def cmd_update_status(args):
    page = _resolve_target_page(args.date)
    diary.update_project_status(
        page["week_key"], args.project, args.status, args.note, args.append_note, args.role
    )
    _maybe_auto_sync(page["week_key"])
    prefix = f"Created new diary for the week of {page['week_label']}.\n" if page["is_new"] else ""
    print(f"{prefix}Updated {args.project} -> {args.status} for the week of {page['week_label']}.")


def cmd_bulk_update(args):
    updates = json.loads(args.json)
    page = _resolve_target_page(args.date)
    results = diary.bulk_update_projects(page["week_key"], updates)
    _maybe_auto_sync(page["week_key"])
    prefix = f"Created new diary for the week of {page['week_label']}.\n" if page["is_new"] else ""
    print(f"{prefix}Updated {len(results)} project(s) for the week of {page['week_label']}:")
    for r in results:
        print(f"- {r}")


def cmd_set_role(args):
    page = _resolve_target_page(args.date)
    resolved = diary.set_project_role(page["week_key"], args.project, args.role)
    _maybe_auto_sync(page["week_key"])
    verb = "Set role for" if args.role.strip() else "Cleared role for"
    print(f"{verb} {resolved} in the diary for the week of {page['week_label']}.")


def cmd_rename_project(args):
    page = _resolve_target_page(args.date)
    diary.rename_project(page["week_key"], args.old, args.new)
    _maybe_auto_sync(page["week_key"])
    print(f"Renamed {args.old} -> {args.new} in the diary for the week of {page['week_label']}.")


def cmd_remove_project(args):
    page = _resolve_target_page(args.date)
    diary.remove_project(page["week_key"], args.project)
    _maybe_auto_sync(page["week_key"])
    print(f"Removed {args.project} from the diary for the week of {page['week_label']}.")


def cmd_clear_note(args):
    page = _resolve_target_page(args.date)
    diary.clear_project_note(page["week_key"], args.project)
    _maybe_auto_sync(page["week_key"])
    print(f"Cleared note for {args.project} in the diary for the week of {page['week_label']}.")


def cmd_add_note(args):
    page = _resolve_target_page(args.date)
    diary.add_note(page["week_key"], args.content)
    _maybe_auto_sync(page["week_key"])
    prefix = f"Created new diary for the week of {page['week_label']}.\n" if page["is_new"] else ""
    print(f"{prefix}Added note to the diary for the week of {page['week_label']}.")


def cmd_edit_note(args):
    page = _resolve_target_page(args.date)
    diary.edit_note(page["week_key"], args.index, args.content)
    _maybe_auto_sync(page["week_key"])
    print(f"Updated note [{args.index}] in the diary for the week of {page['week_label']}.")


def cmd_delete_note(args):
    page = _resolve_target_page(args.date)
    deleted = diary.delete_note(page["week_key"], args.index)
    _maybe_auto_sync(page["week_key"])
    print(f"Deleted note [{args.index}] from the diary for the week of {page['week_label']}: '{deleted}'")


def cmd_add_reminder(args):
    week_key = _week_key_for(args.date)
    label = diary.get_week_label(week_key)
    diary.add_reminder(week_key, args.content, args.due_date)
    _maybe_auto_sync(week_key)
    print(f"Added a reminder for the week of {label}.")


def cmd_list_reminders(args):
    week_key = _week_key_for(args.date)
    label = diary.get_week_label(week_key)
    reminders = diary.list_reminders(week_key)
    if args.json:
        print(json.dumps(reminders, indent=2))
        return
    if not reminders:
        print(f"No reminders found for the week of {label}.")
        return
    print(f"Reminders for the week of {label}:\n")
    for i, r in enumerate(reminders, start=1):
        checkbox = "[x]" if r.get("completed", False) else "[ ]"
        due = r.get("dueDate")
        due_prefix = f"Due Date: {due} " if due else ""
        print(f"- [{i}] {checkbox} {due_prefix}{r.get('content', '')}")


def cmd_complete_reminder(args):
    week_key = _week_key_for(args.date)
    label = diary.get_week_label(week_key)
    diary.set_reminder_completed(week_key, args.index, True)
    _maybe_auto_sync(week_key)
    print(f"Marked reminder [{args.index}] complete for the week of {label}.")


def cmd_reopen_reminder(args):
    week_key = _week_key_for(args.date)
    label = diary.get_week_label(week_key)
    diary.set_reminder_completed(week_key, args.index, False)
    _maybe_auto_sync(week_key)
    print(f"Reopened reminder [{args.index}] for the week of {label}.")


def cmd_push_sync(args):
    from work_diary_mcp.config import get_sync_path

    sync_path = get_sync_path()
    if sync_path is None:
        raise ValueError(
            "No sync folder configured. Set WORK_DIARY_SYNC_PATH or the "
            "sync_path key in the settings file."
        )
    week_key = _week_key_for(args.date)
    label = diary.get_week_label(week_key)
    diary.get_or_create_page_for_week(week_key)
    dest = _copy_week_to_sync_folder(week_key, sync_path)
    print(f"Copied {label} diary to {dest}.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="work-diary", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    date_help = (
        "Target week: ISO date (e.g. 2026-03-02), 'last week', 'next week', "
        "'N weeks ago', 'N weeks from now', or 'in N weeks'. Defaults to current week."
    )

    def add_date(sp):
        sp.add_argument("--date", help=date_help)

    sp = sub.add_parser("get-diary", help="Print the full rendered Markdown diary for a week")
    add_date(sp)
    sp.set_defaults(func=cmd_get_diary)

    sp = sub.add_parser("list-projects", help="List projects and statuses for a week")
    add_date(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list_projects)

    sp = sub.add_parser("list-weeks", help="List all weeks with diary entries")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list_weeks)

    sp = sub.add_parser("update-status", help="Add or update a project's status")
    sp.add_argument("--project", required=True)
    sp.add_argument("--status", required=True)
    sp.add_argument("--note")
    sp.add_argument("--append-note", action="store_true")
    sp.add_argument("--role")
    add_date(sp)
    sp.set_defaults(func=cmd_update_status)

    sp = sub.add_parser("bulk-update", help="Update multiple projects at once")
    sp.add_argument(
        "--json",
        required=True,
        help='JSON list, e.g. \'[{"project": "X", "status": "On Track"}]\'',
    )
    add_date(sp)
    sp.set_defaults(func=cmd_bulk_update)

    sp = sub.add_parser("set-role", help="Set or clear a project's engagement role")
    sp.add_argument("--project", required=True)
    sp.add_argument("--role", required=True, help="Role name/emoji/shortcode, or '' to clear")
    add_date(sp)
    sp.set_defaults(func=cmd_set_role)

    sp = sub.add_parser("rename-project", help="Rename a project, preserving status/note/role")
    sp.add_argument("--old", required=True)
    sp.add_argument("--new", required=True)
    add_date(sp)
    sp.set_defaults(func=cmd_rename_project)

    sp = sub.add_parser("remove-project", help="Remove a project from a week")
    sp.add_argument("--project", required=True)
    add_date(sp)
    sp.set_defaults(func=cmd_remove_project)

    sp = sub.add_parser("clear-note", help="Clear a project's inline note")
    sp.add_argument("--project", required=True)
    add_date(sp)
    sp.set_defaults(func=cmd_clear_note)

    sp = sub.add_parser("add-note", help="Append a general note to a week")
    sp.add_argument("--content", required=True)
    add_date(sp)
    sp.set_defaults(func=cmd_add_note)

    sp = sub.add_parser("edit-note", help="Edit an existing note by 1-based index")
    sp.add_argument("--index", type=int, required=True)
    sp.add_argument("--content", required=True)
    add_date(sp)
    sp.set_defaults(func=cmd_edit_note)

    sp = sub.add_parser("delete-note", help="Delete a note by 1-based index")
    sp.add_argument("--index", type=int, required=True)
    add_date(sp)
    sp.set_defaults(func=cmd_delete_note)

    sp = sub.add_parser("add-reminder", help="Add a reminder for a week")
    sp.add_argument("--content", required=True)
    sp.add_argument("--due-date")
    add_date(sp)
    sp.set_defaults(func=cmd_add_reminder)

    sp = sub.add_parser("list-reminders", help="List reminders for a week")
    add_date(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list_reminders)

    sp = sub.add_parser("complete-reminder", help="Mark a reminder complete")
    sp.add_argument("--index", type=int, required=True)
    add_date(sp)
    sp.set_defaults(func=cmd_complete_reminder)

    sp = sub.add_parser("reopen-reminder", help="Mark a reminder incomplete")
    sp.add_argument("--index", type=int, required=True)
    add_date(sp)
    sp.set_defaults(func=cmd_reopen_reminder)

    sp = sub.add_parser("push-sync", help="Copy a week's diary Markdown to the configured sync folder")
    add_date(sp)
    sp.set_defaults(func=cmd_push_sync)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
