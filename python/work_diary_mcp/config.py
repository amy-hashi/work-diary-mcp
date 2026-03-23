from __future__ import annotations

import ntpath
import os
import tomllib
from functools import lru_cache
from pathlib import Path

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

ENV_VAR = "WORK_DIARY_DATA_DIR"
JIRA_BASE_URL_ENV_VAR = "WORK_DIARY_JIRA_BASE_URL"
JIRA_PREFIXES_ENV_VAR = "WORK_DIARY_JIRA_PREFIXES"

_DEFAULT_JIRA_BASE_URL = "https://jira.example.com/browse"
_DEFAULT_JIRA_PREFIXES: tuple[str, ...] = ("PROJ", "INFRA", "ENG", "OPS", "SEC", "DATA")


def _default_settings_file() -> str:
    """Return the platform-native default settings file path as a string."""
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return ntpath.join(appdata, "work-diary", "settings.toml")

        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            return ntpath.join(
                userprofile,
                "AppData",
                "Roaming",
                "work-diary",
                "settings.toml",
            )

        return ntpath.join(
            "C:\\Users\\Default",
            "AppData",
            "Roaming",
            "work-diary",
            "settings.toml",
        )

    return str(Path.home() / ".config" / "work-diary" / "settings.toml")


# Default settings file location:
# - Windows: %APPDATA%/work-diary/settings.toml
# - Other platforms: ~/.config/work-diary/settings.toml
SETTINGS_FILE = Path(_default_settings_file())

# Built-in fallback: <repo root>/data  (python/work_diary_mcp/ -> repo root)
_BUILTIN_DEFAULT = Path(__file__).parent.parent.parent / "data"


# --------------------------------------------------------------------------- #
# Resolution logic
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=1)
def get_data_dir() -> Path:
    """Return the resolved, validated data directory.

    Resolution order (first match wins):

    1. ``WORK_DIARY_DATA_DIR`` environment variable
    2. ``data_dir`` key in the platform-native settings file
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


def _load_settings_data(path: Path) -> dict:
    """Parse *path* as TOML and return the decoded settings object."""
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def _read_settings_file(path: Path) -> Path | None:
    """Parse *path* as TOML and return the ``data_dir`` value, or None.

    Returns None (rather than raising) when:
    - the file cannot be read
    - it is not valid TOML
    - it does not contain a ``data_dir`` key

    Raises:
        TypeError: If ``data_dir`` is present but is not a string.
    """
    data = _load_settings_data(path)

    raw = data.get("data_dir")
    if raw is None:
        return None

    if not isinstance(raw, str):
        raise TypeError(
            f"Invalid settings file {path}: "
            f"'data_dir' must be a string, got {type(raw).__name__!r}."
        )

    return Path(raw)


@lru_cache(maxsize=1)
def get_jira_base_url() -> str:
    """Return the configured Jira browse base URL."""
    raw_env = os.environ.get(JIRA_BASE_URL_ENV_VAR)
    if raw_env:
        return raw_env.rstrip("/")

    if SETTINGS_FILE.exists():
        data = _load_settings_data(SETTINGS_FILE)
        raw = data.get("jira_base_url")
        if raw is not None:
            if not isinstance(raw, str):
                raise TypeError(
                    f"Invalid settings file {SETTINGS_FILE}: "
                    f"'jira_base_url' must be a string, got {type(raw).__name__!r}."
                )
            return raw.rstrip("/")

    return _DEFAULT_JIRA_BASE_URL


@lru_cache(maxsize=1)
def get_jira_prefixes() -> tuple[str, ...]:
    """Return the configured Jira prefixes."""
    raw_env = os.environ.get(JIRA_PREFIXES_ENV_VAR)
    if raw_env:
        prefixes = tuple(prefix.strip().upper() for prefix in raw_env.split(",") if prefix.strip())
        return prefixes or _DEFAULT_JIRA_PREFIXES

    if SETTINGS_FILE.exists():
        data = _load_settings_data(SETTINGS_FILE)
        raw = data.get("jira_prefixes")
        if raw is not None:
            if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
                raise TypeError(
                    f"Invalid settings file {SETTINGS_FILE}: "
                    "'jira_prefixes' must be a list of strings."
                )
            prefixes = tuple(item.strip().upper() for item in raw if item.strip())
            return prefixes or _DEFAULT_JIRA_PREFIXES

    return _DEFAULT_JIRA_PREFIXES


def _validate(path: Path, source: str) -> None:
    """Raise ValueError if *path* exists but is not a directory."""
    if path.exists() and not path.is_dir():
        raise ValueError(
            f"Data directory configured via {source} points to a path that "
            f"exists but is not a directory: {path}"
        )
