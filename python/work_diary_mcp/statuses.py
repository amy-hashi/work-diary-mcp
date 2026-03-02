from __future__ import annotations

# --------------------------------------------------------------------------- #
# Status definitions — single source of truth
# --------------------------------------------------------------------------- #

# Maps lowercase status strings to their emoji-decorated display form.
STATUS_MAP: dict[str, str] = {
    "on track": "🟢 On Track",
    "at risk": "🟡 At Risk",
    "blocked": "🔴 Blocked",
    "done": "✅ Done",
    "complete": "✅ Complete",
    "completed": "✅ Completed",
    "in progress": "🔵 In Progress",
    "not started": "⚪ Not Started",
    "cancelled": "⛔ Cancelled",
    "canceled": "⛔ Canceled",
    "paused": "⏸️ Paused",
}

# Statuses that indicate a project is finished and should not be carried
# forward to a new week.  Derived directly from STATUS_MAP so the two can
# never drift apart: any key whose formatted value starts with "✅" or "⛔"
# is considered terminal.
COMPLETED_STATUSES: frozenset[str] = frozenset(
    key for key, display in STATUS_MAP.items() if display.startswith(("✅", "⛔"))
)


def format_status(status: str) -> str:
    """Return the emoji-decorated display string for a status, or the raw value."""
    return STATUS_MAP.get(status.strip().lower(), status)


def is_completed(status: str) -> bool:
    """Return True if *status* is a terminal (completed/cancelled) status."""
    return status.strip().lower() in COMPLETED_STATUSES
