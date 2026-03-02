from __future__ import annotations

import os
import tomllib
from pathlib import Path

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

ENV_VAR = "WORK_DIARY_DATA_DIR"

# Default settings file location: ~/.config/work-diary/settings.toml
SETTINGS_FILE = Path.home() / ".config" / "work-diary" / "settings.toml"

# Built-in fallback: <repo root>/data  (python/work_diary_mcp/ -> repo root)
_BUILTIN_DEFAULT = Path(__file__).parent.parent.parent / "data"


# --------------------------------------------------------------------------- #
# Resolution logic
# --------------------------------------------------------------------------- #


def get_data_dir() -> Path:
    """Return the resolved, validated data directory.

    Resolution order (first match wins):

    1. ``WORK_DIARY_DATA_DIR`` environment variable
    2. ``data_dir`` key in ``~/.config/work-diary/settings.toml``
    3. Built-in default: ``<repo root>/data``

    The resolved path is created if it does not already exist.

    Raises:
        ValueError: If an explicitly configured path (env var or settings
            file) is set but resolves to a path that exists and is not a
            directory (e.g. a regular file is in the way).
    """
    path, source = _resolve()
    _validate(path, source)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve() -> tuple[Path, str]:
    """Return (path, human-readable source) without creating or validating it."""
    # 1. Environment variable
    raw_env = os.environ.get(ENV_VAR)
    if raw_env:
        return Path(raw_env).expanduser().resolve(), f"${ENV_VAR}"

    # 2. Settings file
    if SETTINGS_FILE.exists():
        setting = _read_settings_file(SETTINGS_FILE)
        if setting is not None:
            return setting.expanduser().resolve(), str(SETTINGS_FILE)

    # 3. Built-in default
    return _BUILTIN_DEFAULT.resolve(), "built-in default"


def _read_settings_file(path: Path) -> Path | None:
    """Parse *path* as TOML and return the ``data_dir`` value, or None.

    Returns None (rather than raising) when:
    - the file cannot be read
    - it is not valid TOML
    - it does not contain a ``data_dir`` key

    Raises:
        TypeError: If ``data_dir`` is present but is not a string.
    """
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None

    raw = data.get("data_dir")
    if raw is None:
        return None

    if not isinstance(raw, str):
        raise TypeError(
            f"Invalid settings file {path}: "
            f"'data_dir' must be a string, got {type(raw).__name__!r}."
        )

    return Path(raw)


def _validate(path: Path, source: str) -> None:
    """Raise ValueError if *path* exists but is not a directory."""
    if path.exists() and not path.is_dir():
        raise ValueError(
            f"Data directory configured via {source} points to a path that "
            f"exists but is not a directory: {path}"
        )
