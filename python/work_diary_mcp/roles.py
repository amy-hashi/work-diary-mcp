from __future__ import annotations

# --------------------------------------------------------------------------- #
# Role definitions — single source of truth
#
# Roles describe the engagement mode an engineer is taking on a project,
# inspired by the Principal Engineer role framework: Sponsor, Guide,
# Catcher, Advisor, Catalyst, Participant.
# --------------------------------------------------------------------------- #

# Maps lowercase role names to their canonical emoji-decorated display form.
ROLE_MAP: dict[str, str] = {
    "sponsor": "🚀 Sponsor",
    "guide": "🗺️ Guide",
    "catcher": "🧯 Catcher",
    "advisor": "🧭 Advisor",
    "catalyst": "🧪 Catalyst",
    "participant": "🙋 Participant",
}

# Maps known emoji shortcodes (e.g. ":rocket:") to the canonical role name.
# Both the "primary" emoji used in display form and reasonable aliases are
# accepted so users can paste the variants surfaced by different chat
# clients (Slack, GitHub, etc.) without surprises.
_SHORTCODE_TO_ROLE: dict[str, str] = {
    ":rocket:": "sponsor",
    ":world_map:": "guide",
    ":map:": "guide",
    ":fire_extinguisher:": "catcher",
    ":compass:": "advisor",
    ":test_tube:": "catalyst",
    ":raising_hand:": "participant",
    ":raised_hand:": "participant",
    ":person_raising_hand:": "participant",
}

# Maps known bare emoji to the canonical role name.
_EMOJI_TO_ROLE: dict[str, str] = {
    "🚀": "sponsor",
    "🗺️": "guide",
    "🗺": "guide",
    "🧯": "catcher",
    "🧭": "advisor",
    "🧪": "catalyst",
    "🙋": "participant",
    "🙋‍♀️": "participant",
    "🙋‍♂️": "participant",
}


def format_role(role: str | None) -> str:
    """Return the emoji-decorated display string for a role.

    Accepts any of the following spellings (case-insensitive) and
    normalizes them to the canonical display form (e.g. ``"🚀 Sponsor"``):

    - bare role name: ``"sponsor"``, ``"Sponsor"``, ``"SPONSOR"``
    - emoji shortcode: ``":rocket:"``
    - bare emoji: ``"🚀"``
    - already-formatted display: ``"🚀 Sponsor"`` (or its shortcode equivalent)

    Unknown values — including a known shortcode/emoji prefix followed by an
    unrecognized custom label such as ``":rocket: Architect"`` — are returned
    trimmed but otherwise unchanged so callers can still set arbitrary role
    labels if they want to. ``None`` and empty/whitespace input return ``""``.
    """
    if role is None:
        return ""

    cleaned = role.strip()
    if not cleaned:
        return ""

    lowered = cleaned.lower()

    # Direct hit on the canonical role-name map.
    if lowered in ROLE_MAP:
        return ROLE_MAP[lowered]

    # Emoji shortcode, either bare or followed by the matching canonical
    # role name. Any other suffix (e.g. ":rocket: Architect") is treated as
    # a custom label and preserved as-is rather than silently rewritten.
    for shortcode, canonical in _SHORTCODE_TO_ROLE.items():
        if lowered == shortcode:
            return ROLE_MAP[canonical]
        if lowered.startswith(shortcode + " "):
            suffix = lowered[len(shortcode) + 1 :].strip()
            if suffix == "" or suffix == canonical:
                return ROLE_MAP[canonical]
            # Custom suffix — fall through to preserve the user's label.

    # Bare emoji, either alone or followed by the matching canonical role
    # name. Same suffix-preservation rule as for shortcodes above.
    for emoji, canonical in _EMOJI_TO_ROLE.items():
        if cleaned == emoji:
            return ROLE_MAP[canonical]
        if cleaned.startswith(emoji + " "):
            suffix = cleaned[len(emoji) + 1 :].strip().lower()
            if suffix == "" or suffix == canonical:
                return ROLE_MAP[canonical]
            # Custom suffix — fall through to preserve the user's label.

    return cleaned
