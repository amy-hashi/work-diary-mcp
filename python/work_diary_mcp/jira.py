from __future__ import annotations

import re
from functools import lru_cache

from work_diary_mcp.config import get_jira_base_url, get_jira_prefixes

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# Matches any Markdown link: [label](url)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")


@lru_cache(maxsize=1)
def _bare_ticket_re() -> re.Pattern[str]:
    """Build and cache the Jira ticket regex from the configured prefixes."""
    prefixes = get_jira_prefixes()
    prefix_alternation = "|".join(re.escape(p) for p in prefixes)
    return re.compile(
        rf"\b({prefix_alternation})-(\d{{3,}})\b",
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

        >>> linkify_jira_refs("PROJ-1234")
        '[PROJ-1234](https://jira.example.com/browse/PROJ-1234)'

        >>> linkify_jira_refs("see [PROJ-1234](https://jira.example.com/browse/PROJ-1234)")
        'see [PROJ-1234](https://jira.example.com/browse/PROJ-1234)'

        >>> linkify_jira_refs("blocked by PROJ-1234 and INFRA-5678")
        'blocked by [PROJ-1234](https://jira.example.com/browse/PROJ-1234) and [INFRA-5678](https://jira.example.com/browse/INFRA-5678)'

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
    bare_ticket_re = _bare_ticket_re()
    jira_base_url = get_jira_base_url()

    def _replace(m: re.Match) -> str:
        prefix = m.group(1).upper()
        number = m.group(2)
        ticket = f"{prefix}-{number}"
        return f"[{ticket}]({jira_base_url}/{ticket})"

    return bare_ticket_re.sub(_replace, text)
