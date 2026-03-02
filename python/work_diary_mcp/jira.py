from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

JIRA_BASE_URL = "https://hashicorp.atlassian.net/browse"

# Known Jira project prefixes.  Add new prefixes here as needed.
_KNOWN_PREFIXES: tuple[str, ...] = (
    "TF",
    "RDPR",
    "TFDN",
    "SECGRC",
    "IND",
    "CAG",
)

_PREFIX_ALTERNATION = "|".join(re.escape(p) for p in _KNOWN_PREFIXES)

# Matches any Markdown link: [label](url)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")

# Matches a bare Jira ticket reference — applied only to plain-text segments
# (after existing Markdown links have been extracted and protected).
#
# Pattern breakdown:
#   \b           — word boundary before the prefix
#   (PREFIX)     — one of the known project prefixes (case-insensitive)
#   -            — literal hyphen
#   (\d{4,})     — four or more digits
#   \b           — word boundary after the digits
_BARE_TICKET_RE = re.compile(
    rf"\b({_PREFIX_ALTERNATION})-(\d{{4,}})\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def linkify_jira_refs(text: str) -> str:
    """Replace bare Jira ticket references in *text* with Markdown links.

    Already-linked references (i.e. those already wrapped in ``[...](...)``
    Markdown syntax) are left untouched.

    The approach is a two-pass protect-then-substitute:

    1. Split the text into alternating plain-text and Markdown-link segments.
    2. Apply ticket linkification only to the plain-text segments.
    3. Reassemble and return.

    This guarantees that ticket keys that already appear inside a Markdown link
    (either in the label or in the URL) are never double-linked.

    Examples::

        >>> linkify_jira_refs("TF-34398")
        '[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)'

        >>> linkify_jira_refs("see [TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)")
        'see [TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)'

        >>> linkify_jira_refs("blocked by TF-34398 and RDPR-1234")
        'blocked by [TF-34398](https://hashicorp.atlassian.net/browse/TF-34398) and [RDPR-1234](https://hashicorp.atlassian.net/browse/RDPR-1234)'

    Args:
        text: The string to process.

    Returns:
        A new string with bare ticket references replaced by Markdown links.
        The ticket key is always uppercased in both the label and the URL.
    """
    parts: list[str] = []
    last_end = 0

    for m in _MARKDOWN_LINK_RE.finditer(text):
        # Linkify the plain-text segment before this existing Markdown link
        plain = text[last_end : m.start()]
        parts.append(_linkify_plain(plain))
        # Preserve the existing Markdown link verbatim
        parts.append(m.group(0))
        last_end = m.end()

    # Linkify any trailing plain-text after the last Markdown link
    parts.append(_linkify_plain(text[last_end:]))

    return "".join(parts)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _linkify_plain(text: str) -> str:
    """Linkify bare Jira ticket references in a plain-text (non-link) segment."""

    def _replace(m: re.Match) -> str:
        prefix = m.group(1).upper()
        number = m.group(2)
        ticket = f"{prefix}-{number}"
        return f"[{ticket}]({JIRA_BASE_URL}/{ticket})"

    return _BARE_TICKET_RE.sub(_replace, text)
