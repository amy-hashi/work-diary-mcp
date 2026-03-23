"""
Tests for work_diary_mcp.diary, work_diary_mcp.config, and work_diary_mcp.statuses.

Each test gets its own temporary data directory via the `diary_dir` fixture,
which sets WORK_DIARY_DATA_DIR in the environment so tests are fully isolated
and never touch real diary files.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from stat import S_IMODE
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to point the module at a temp directory
# ---------------------------------------------------------------------------
import work_diary_mcp.diary as diary_mod
import work_diary_mcp.server as server_mod


@pytest.fixture()
def diary_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the data directory to a fresh temp directory for each test.

    Sets WORK_DIARY_DATA_DIR in the environment so that get_data_dir() in
    config.py picks up the temp path without any module-level patching.
    """
    import work_diary_mcp.config as config_mod

    config_mod.get_data_dir.cache_clear()
    monkeypatch.setenv("WORK_DIARY_DATA_DIR", str(tmp_path))
    yield tmp_path
    config_mod.get_data_dir.cache_clear()


def _week_key(d: date) -> str:
    return diary_mod.get_week_key(d)


def _monday(d: date) -> date:
    return diary_mod.get_monday_of(d)


# ---------------------------------------------------------------------------
# Week-key helpers
# ---------------------------------------------------------------------------


class TestGetMondayOf:
    def test_monday_returns_same_day(self):
        d = date(2026, 3, 2)  # a Monday
        assert _monday(d) == d

    def test_sunday_returns_prior_monday(self):
        d = date(2026, 3, 8)  # Sunday
        assert _monday(d) == date(2026, 3, 2)

    def test_friday_returns_prior_monday(self):
        d = date(2026, 3, 6)  # Friday
        assert _monday(d) == date(2026, 3, 2)


class TestGetWeekLabel:
    def test_formats_label_without_platform_specific_strftime_directives(self):
        assert diary_mod.get_week_label("2026-03-02") == "Mar 2, 2026"


class TestGetWeekKey:
    def test_returns_iso_string(self):
        key = diary_mod.get_week_key(date(2026, 3, 4))  # Wednesday
        assert key == "2026-03-02"

    def test_defaults_to_today(self):
        today = date.today()
        expected = _monday(today).isoformat()
        assert diary_mod.get_week_key() == expected


class TestParseWeekKey:
    def test_iso_date(self):
        assert diary_mod.parse_week_key("2026-03-04") == "2026-03-02"

    def test_last_week(self):
        expected = diary_mod.get_week_key(date.today() - timedelta(weeks=1))
        assert diary_mod.parse_week_key("last week") == expected

    def test_n_weeks_ago(self):
        expected = diary_mod.get_week_key(date.today() - timedelta(weeks=3))
        assert diary_mod.parse_week_key("3 weeks ago") == expected

    def test_singular_week_ago(self):
        expected = diary_mod.get_week_key(date.today() - timedelta(weeks=1))
        assert diary_mod.parse_week_key("1 week ago") == expected

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Could not parse"):
            diary_mod.parse_week_key("yesterday")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestConfig:
    @staticmethod
    def _clear_cache(config_mod) -> None:
        config_mod.get_data_dir.cache_clear()

    def test_env_var_takes_precedence(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """WORK_DIARY_DATA_DIR overrides everything else."""
        import work_diary_mcp.config as config_mod

        target = tmp_path / "from_env"
        monkeypatch.setenv("WORK_DIARY_DATA_DIR", str(target))
        monkeypatch.setattr(config_mod, "SETTINGS_FILE", tmp_path / "nonexistent.toml")

        self._clear_cache(config_mod)
        result = config_mod.get_data_dir()
        assert result == target.resolve()
        assert result.is_dir()

    def test_settings_file_used_when_no_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """data_dir from settings.toml is used when the env var is absent."""
        import work_diary_mcp.config as config_mod

        target = tmp_path / "from_settings"
        settings_file = tmp_path / "settings.toml"
        settings_file.write_text(f'data_dir = "{target}"\n', encoding="utf-8")

        monkeypatch.delenv("WORK_DIARY_DATA_DIR", raising=False)
        monkeypatch.setattr(config_mod, "SETTINGS_FILE", settings_file)

        self._clear_cache(config_mod)
        result = config_mod.get_data_dir()
        assert result == target.resolve()
        assert result.is_dir()

    def test_builtin_default_used_when_nothing_configured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Falls back to the built-in default when neither env var nor settings file is present."""
        import work_diary_mcp.config as config_mod

        monkeypatch.delenv("WORK_DIARY_DATA_DIR", raising=False)
        monkeypatch.setattr(config_mod, "SETTINGS_FILE", tmp_path / "nonexistent.toml")

        self._clear_cache(config_mod)
        result = config_mod.get_data_dir()
        assert result == config_mod._BUILTIN_DEFAULT.resolve()

    def test_missing_data_dir_key_in_settings_falls_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A settings file without data_dir falls through to the built-in default."""
        import work_diary_mcp.config as config_mod

        settings_file = tmp_path / "settings.toml"
        settings_file.write_text('some_other_key = "value"\n', encoding="utf-8")

        monkeypatch.delenv("WORK_DIARY_DATA_DIR", raising=False)
        monkeypatch.setattr(config_mod, "SETTINGS_FILE", settings_file)

        self._clear_cache(config_mod)
        result = config_mod.get_data_dir()
        assert result == config_mod._BUILTIN_DEFAULT.resolve()

    def test_invalid_toml_in_settings_falls_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A malformed settings file is silently skipped, falling back to the default."""
        import work_diary_mcp.config as config_mod

        settings_file = tmp_path / "settings.toml"
        settings_file.write_text("this is not : valid toml [\n", encoding="utf-8")

        monkeypatch.delenv("WORK_DIARY_DATA_DIR", raising=False)
        monkeypatch.setattr(config_mod, "SETTINGS_FILE", settings_file)

        self._clear_cache(config_mod)
        result = config_mod.get_data_dir()
        assert result == config_mod._BUILTIN_DEFAULT.resolve()

    def test_data_dir_wrong_type_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A non-string data_dir in settings.toml raises TypeError."""
        import work_diary_mcp.config as config_mod

        settings_file = tmp_path / "settings.toml"
        settings_file.write_text("data_dir = 42\n", encoding="utf-8")

        monkeypatch.delenv("WORK_DIARY_DATA_DIR", raising=False)
        monkeypatch.setattr(config_mod, "SETTINGS_FILE", settings_file)

        self._clear_cache(config_mod)
        with pytest.raises(TypeError, match="data_dir"):
            config_mod.get_data_dir()

    def test_path_exists_but_is_file_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A configured path that exists as a regular file raises ValueError."""
        import work_diary_mcp.config as config_mod

        blocker = tmp_path / "not_a_dir"
        blocker.write_text("oops", encoding="utf-8")

        monkeypatch.setenv("WORK_DIARY_DATA_DIR", str(blocker))

        self._clear_cache(config_mod)
        with pytest.raises(ValueError, match="not a directory"):
            config_mod.get_data_dir()

    def test_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A path starting with ~ is expanded correctly."""
        import work_diary_mcp.config as config_mod

        # Point home to tmp_path so ~/diary resolves to tmp_path/diary
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("WORK_DIARY_DATA_DIR", "~/diary")

        self._clear_cache(config_mod)
        result = config_mod.get_data_dir()
        assert result == (tmp_path / "diary").resolve()
        assert result.is_dir()

    def test_get_data_dir_creates_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """get_data_dir() creates the target directory if it does not exist."""
        import work_diary_mcp.config as config_mod

        target = tmp_path / "new" / "nested" / "dir"
        assert not target.exists()
        monkeypatch.setenv("WORK_DIARY_DATA_DIR", str(target))

        self._clear_cache(config_mod)
        result = config_mod.get_data_dir()
        assert result.is_dir()

    def test_empty_string_env_var_falls_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """An empty-string WORK_DIARY_DATA_DIR is treated the same as unset."""
        import work_diary_mcp.config as config_mod

        monkeypatch.setenv("WORK_DIARY_DATA_DIR", "")
        monkeypatch.setattr(config_mod, "SETTINGS_FILE", tmp_path / "nonexistent.toml")

        self._clear_cache(config_mod)
        result = config_mod.get_data_dir()
        assert result == config_mod._BUILTIN_DEFAULT.resolve()

    def test_settings_file_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A ~ in settings.toml data_dir is expanded correctly."""
        import work_diary_mcp.config as config_mod

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("WORK_DIARY_DATA_DIR", raising=False)

        settings_file = tmp_path / "settings.toml"
        settings_file.write_text('data_dir = "~/from-settings"\n', encoding="utf-8")
        monkeypatch.setattr(config_mod, "SETTINGS_FILE", settings_file)

        self._clear_cache(config_mod)
        result = config_mod.get_data_dir()
        assert result == (tmp_path / "from-settings").resolve()
        assert result.is_dir()

    def test_windows_settings_file_uses_appdata(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """On Windows, the default settings file lives under %APPDATA%."""
        import work_diary_mcp.config as config_mod

        appdata = tmp_path / "AppData" / "Roaming"
        monkeypatch.setenv("APPDATA", str(appdata))

        with patch.object(config_mod.os, "name", "nt"):
            result = config_mod._default_settings_file()

        result_str = result.replace("\\", "/")
        appdata_str = str(appdata).replace("\\", "/")
        assert result_str.startswith(appdata_str)
        assert result_str.endswith("work-diary/settings.toml")

    def test_windows_settings_file_falls_back_when_appdata_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """On Windows, the settings path falls back to USERPROFILE/AppData/Roaming when APPDATA is unset."""
        import work_diary_mcp.config as config_mod

        monkeypatch.setenv("USERPROFILE", "C:/Users/tester")
        monkeypatch.delenv("APPDATA", raising=False)

        with patch.object(config_mod.os, "name", "nt"):
            result = config_mod._default_settings_file()

        result_str = result.replace("\\", "/")
        assert "Users" in result_str
        assert "tester" in result_str
        assert result_str.endswith("work-diary/settings.toml")

    def test_settings_file_path_exists_as_file_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A settings-file-configured path that exists as a regular file raises ValueError."""
        import work_diary_mcp.config as config_mod

        blocker = tmp_path / "not_a_dir"
        blocker.write_text("oops", encoding="utf-8")

        settings_file = tmp_path / "settings.toml"
        settings_file.write_text(f'data_dir = "{blocker}"\n', encoding="utf-8")

        monkeypatch.delenv("WORK_DIARY_DATA_DIR", raising=False)
        monkeypatch.setattr(config_mod, "SETTINGS_FILE", settings_file)

        self._clear_cache(config_mod)
        with pytest.raises(ValueError, match="not a directory"):
            config_mod.get_data_dir()


class TestAtomicWriteText:
    def test_preserves_existing_file_mode(self, diary_dir):
        target = diary_dir / "sample.txt"
        target.write_text("original", encoding="utf-8")
        target.chmod(0o644)

        diary_mod._atomic_write_text(target, "updated")

        assert target.read_text(encoding="utf-8") == "updated"
        assert S_IMODE(target.stat().st_mode) == 0o644

    def test_new_file_keeps_secure_default_permissions(self, diary_dir):
        target = diary_dir / "new-file.txt"

        diary_mod._atomic_write_text(target, "created")

        assert target.read_text(encoding="utf-8") == "created"
        mode = S_IMODE(target.stat().st_mode)
        if os.name == "nt":
            assert mode & 0o777 == mode
        else:
            assert mode == 0o600


class TestWeekLock:
    def test_windows_lock_file_does_not_grow_on_repeated_acquire(self, diary_dir):
        if os.name != "nt":
            pytest.skip("Windows-specific lock file behavior")

        week_key = "2026-03-02"
        lock_path = diary_dir / f"{week_key}.lock"

        with diary_mod._week_lock(week_key):
            pass
        with diary_mod._week_lock(week_key):
            pass
        with diary_mod._week_lock(week_key):
            pass

        assert lock_path.read_bytes() == b"0"


class TestHistoricalWeekWrites:
    def test_add_note_to_previous_week(self, diary_dir):
        week_key = "2026-03-02"
        page = diary_mod.get_or_create_page_for_week(week_key)

        assert page["is_new"] is True
        assert page["week_key"] == week_key

        diary_mod.add_note(week_key, "retrospective note")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())

        assert state["weekKey"] == week_key
        assert state["notes"] == [{"content": "retrospective note"}]
        assert state["projects"] == {}
        assert state["projectNotes"] == {}

    def test_previous_week_is_created_empty_without_carry_forward(self, diary_dir):
        prior_week = "2026-02-23"
        previous_state = {
            "weekKey": prior_week,
            "projects": {"Carry Me": "On Track"},
            "projectNotes": {"Carry Me": "from the prior week"},
            "notes": [{"content": "existing note"}],
        }
        (diary_dir / f"{prior_week}.json").write_text(json.dumps(previous_state), encoding="utf-8")

        target_week = "2026-03-02"
        page = diary_mod.get_or_create_page_for_week(target_week)

        assert page["is_new"] is True
        state = json.loads((diary_dir / f"{target_week}.json").read_text())
        assert state == {
            "weekKey": target_week,
            "projects": {},
            "projectNotes": {},
            "notes": [],
        }

    def test_update_project_status_in_previous_week(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.get_or_create_page_for_week(week_key)

        diary_mod.update_project_status(
            week_key,
            "Stacks on TFE",
            "Blocked",
            note="waiting on dependency",
        )
        state = json.loads((diary_dir / f"{week_key}.json").read_text())

        assert state["projects"] == {"Stacks on TFE": "Blocked"}
        assert state["projectNotes"] == {"Stacks on TFE": "waiting on dependency"}

    def test_edit_and_delete_note_in_previous_week(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.get_or_create_page_for_week(week_key)

        diary_mod.add_note(week_key, "first note")
        diary_mod.add_note(week_key, "second note")
        diary_mod.edit_note(week_key, 1, "updated first note")
        deleted = diary_mod.delete_note(week_key, 2)

        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert deleted == "second note"
        assert state["notes"] == [{"content": "updated first note"}]

    def test_current_week_page_with_explicit_date_still_carries_forward(self, diary_dir):
        prior_week = "2026-02-23"
        prior_state = {
            "weekKey": prior_week,
            "projects": {"Carry Me": "On Track"},
            "projectNotes": {"Carry Me": "week-specific note"},
            "notes": [],
        }
        (diary_dir / f"{prior_week}.json").write_text(json.dumps(prior_state), encoding="utf-8")

        current_week = "2026-03-02"
        page = diary_mod._ensure_week_page(current_week, carry_forward=True)

        assert page["is_new"] is True
        state = json.loads((diary_dir / f"{current_week}.json").read_text())
        assert state == {
            "weekKey": current_week,
            "projects": {"Carry Me": "On Track"},
            "projectNotes": {},
            "notes": [],
        }

    def test_carry_forward_ignores_future_weeks(self, diary_dir):
        past_week = "2026-03-02"
        future_week = "2026-04-06"

        (diary_dir / f"{past_week}.json").write_text(
            json.dumps(
                {
                    "weekKey": past_week,
                    "projects": {"Past Project": "On Track"},
                    "projectNotes": {"Past Project": "from the past"},
                    "notes": [],
                }
            ),
            encoding="utf-8",
        )
        (diary_dir / f"{future_week}.json").write_text(
            json.dumps(
                {
                    "weekKey": future_week,
                    "projects": {"Future Project": "Blocked"},
                    "projectNotes": {"Future Project": "from the future"},
                    "notes": [],
                }
            ),
            encoding="utf-8",
        )

        target_week = "2026-03-09"
        carried = diary_mod._get_carry_forward_state(target_week)

        assert carried == {
            "projects": {"Past Project": "On Track"},
            "projectNotes": {},
        }


class TestServerWriteTools:
    def test_resolve_target_page_uses_current_week_helper_for_current_week_iso(self, diary_dir):
        current_week = diary_mod.get_week_key()
        expected_page = {
            "week_key": current_week,
            "week_label": diary_mod.get_week_label(current_week),
            "is_new": False,
        }

        with (
            patch.object(
                server_mod, "get_or_create_week_page", return_value=expected_page
            ) as current_mock,
            patch.object(server_mod, "get_or_create_page_for_week") as historical_mock,
        ):
            page = server_mod._resolve_target_page(current_week)

        assert page == expected_page
        current_mock.assert_called_once_with()
        historical_mock.assert_not_called()

    def test_resolve_target_page_uses_historical_helper_for_last_week(self, diary_dir):
        target_week = diary_mod.parse_week_key("last week")
        expected_page = {
            "week_key": target_week,
            "week_label": diary_mod.get_week_label(target_week),
            "is_new": True,
        }

        with (
            patch.object(server_mod, "get_or_create_week_page") as current_mock,
            patch.object(
                server_mod, "get_or_create_page_for_week", return_value=expected_page
            ) as historical_mock,
        ):
            page = server_mod._resolve_target_page("last week")

        assert page == expected_page
        current_mock.assert_not_called()
        historical_mock.assert_called_once_with(target_week)

    def test_add_note_tool_targets_last_week(self, diary_dir):
        target_week = diary_mod.parse_week_key("last week")

        with (
            patch.object(server_mod, "get_or_create_page_for_week") as page_mock,
            patch.object(server_mod, "add_note") as add_note_mock,
        ):
            page_mock.return_value = {
                "week_key": target_week,
                "week_label": diary_mod.get_week_label(target_week),
                "is_new": True,
            }

            result = server_mod.add_note_tool(
                "Wrapped up validation work.",
                date="last week",
            )

        page_mock.assert_called_once_with(target_week)
        add_note_mock.assert_called_once_with(target_week, "Wrapped up validation work.")
        assert "Created new diary" in result
        assert diary_mod.get_week_label(target_week) in result

    def test_update_project_status_tool_targets_last_week(self, diary_dir):
        target_week = diary_mod.parse_week_key("last week")

        with (
            patch.object(server_mod, "get_or_create_page_for_week") as page_mock,
            patch.object(server_mod, "update_project_status") as update_mock,
        ):
            page_mock.return_value = {
                "week_key": target_week,
                "week_label": diary_mod.get_week_label(target_week),
                "is_new": False,
            }

            result = server_mod.update_project_status_tool(
                "Stacks on TFE",
                "Blocked",
                note="Waiting on dependency.",
                append_note=False,
                date="last week",
            )

        page_mock.assert_called_once_with(target_week)
        update_mock.assert_called_once_with(
            target_week,
            "Stacks on TFE",
            "Blocked",
            "Waiting on dependency.",
            False,
        )
        assert "Stacks on TFE" in result
        assert diary_mod.get_week_label(target_week) in result


# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------


class TestStatuses:
    def test_completed_statuses_derived_from_map(self):
        from work_diary_mcp.statuses import COMPLETED_STATUSES, STATUS_MAP

        for key, display in STATUS_MAP.items():
            if display.startswith(("✅", "⛔")):
                assert key in COMPLETED_STATUSES
            else:
                assert key not in COMPLETED_STATUSES

    def test_is_completed_true(self):
        from work_diary_mcp.statuses import is_completed

        for status in ("done", "Done", "DONE", "completed", "cancelled", "canceled"):
            assert is_completed(status), f"Expected {status!r} to be completed"

    def test_is_completed_false(self):
        from work_diary_mcp.statuses import is_completed

        for status in ("on track", "blocked", "at risk", "in progress", "paused"):
            assert not is_completed(status), f"Expected {status!r} not to be completed"

    def test_format_status_known(self):
        from work_diary_mcp.statuses import format_status

        assert format_status("on track") == "🟢 On Track"
        assert format_status("  Done  ") == "✅ Done"

    def test_format_status_unknown_passthrough(self):
        from work_diary_mcp.statuses import format_status

        assert format_status("Some Custom Status") == "Some Custom Status"


# ---------------------------------------------------------------------------
# State migration
# ---------------------------------------------------------------------------


class TestMigrateState:
    def test_adds_missing_project_notes(self, diary_dir):
        """Old diary files without projectNotes are loaded cleanly."""
        week_key = "2026-03-02"
        # Write a legacy-format file with no projectNotes key
        legacy = {
            "weekKey": week_key,
            "projects": {"Alpha": "On Track"},
            "notes": [],
        }
        (diary_dir / f"{week_key}.json").write_text(json.dumps(legacy), encoding="utf-8")

        state = diary_mod._load_state(week_key)
        assert "projectNotes" in state
        assert state["projectNotes"] == {}

    def test_existing_project_notes_preserved(self, diary_dir):
        """Migration does not overwrite an already-present projectNotes key."""
        week_key = "2026-03-02"
        full = {
            "weekKey": week_key,
            "projects": {"Alpha": "On Track"},
            "projectNotes": {"Alpha": "existing note"},
            "notes": [],
        }
        (diary_dir / f"{week_key}.json").write_text(json.dumps(full), encoding="utf-8")

        state = diary_mod._load_state(week_key)
        assert state["projectNotes"] == {"Alpha": "existing note"}

    def test_bare_ticket_key_linkified_on_load(self, diary_dir):
        """A project key that is a bare ticket ref is linkified during migration."""
        week_key = "2026-03-02"
        pre_linking = {
            "weekKey": week_key,
            "projects": {"CAG-516": "On Track"},
            "projectNotes": {},
            "notes": [],
        }
        (diary_dir / f"{week_key}.json").write_text(json.dumps(pre_linking), encoding="utf-8")

        state = diary_mod._load_state(week_key)
        assert "[CAG-516](https://hashicorp.atlassian.net/browse/CAG-516)" in state["projects"]
        assert "CAG-516" not in state["projects"]

    def test_bare_ticket_in_project_note_linkified_on_load(self, diary_dir):
        """A project note containing a bare ticket ref is linkified during migration."""
        week_key = "2026-03-02"
        pre_linking = {
            "weekKey": week_key,
            "projects": {"Alpha": "Blocked"},
            "projectNotes": {"Alpha": "blocked by TF-9999"},
            "notes": [],
        }
        (diary_dir / f"{week_key}.json").write_text(json.dumps(pre_linking), encoding="utf-8")

        state = diary_mod._load_state(week_key)
        assert (
            "[TF-9999](https://hashicorp.atlassian.net/browse/TF-9999)"
            in state["projectNotes"]["Alpha"]
        )

    def test_project_note_key_stays_in_sync_after_key_linkification(self, diary_dir):
        """When a project key is linkified, its projectNotes entry is re-keyed to match."""
        week_key = "2026-03-02"
        pre_linking = {
            "weekKey": week_key,
            "projects": {"TF-1234": "At Risk"},
            "projectNotes": {"TF-1234": "needs attention"},
            "notes": [],
        }
        (diary_dir / f"{week_key}.json").write_text(json.dumps(pre_linking), encoding="utf-8")

        state = diary_mod._load_state(week_key)
        linked_key = "[TF-1234](https://hashicorp.atlassian.net/browse/TF-1234)"
        assert linked_key in state["projects"]
        assert linked_key in state["projectNotes"]
        assert state["projectNotes"][linked_key] == "needs attention"
        assert "TF-1234" not in state["projectNotes"]

    def test_bare_ticket_in_general_note_linkified_on_load(self, diary_dir):
        """A general note content containing a bare ticket ref is linkified during migration."""
        week_key = "2026-03-02"
        pre_linking = {
            "weekKey": week_key,
            "projects": {},
            "projectNotes": {},
            "notes": [
                {
                    "timestamp": "2026-03-02T10:00:00+00:00",
                    "content": "opened TF-5678 to track",
                },
            ],
        }
        (diary_dir / f"{week_key}.json").write_text(json.dumps(pre_linking), encoding="utf-8")

        state = diary_mod._load_state(week_key)
        assert (
            "[TF-5678](https://hashicorp.atlassian.net/browse/TF-5678)"
            in state["notes"][0]["content"]
        )

    def test_already_linked_key_not_double_linked_on_load(self, diary_dir):
        """A project key that is already a Markdown link is not double-linked during migration."""
        week_key = "2026-03-02"
        linked = "[TF-1234](https://hashicorp.atlassian.net/browse/TF-1234)"
        already_linked = {
            "weekKey": week_key,
            "projects": {linked: "On Track"},
            "projectNotes": {},
            "notes": [],
        }
        (diary_dir / f"{week_key}.json").write_text(json.dumps(already_linked), encoding="utf-8")

        state = diary_mod._load_state(week_key)
        assert list(state["projects"].keys()) == [linked]


# ---------------------------------------------------------------------------
# Carry-forward
# ---------------------------------------------------------------------------


class TestCarryForward:
    def test_no_prior_week_returns_empty(self, diary_dir):
        result = diary_mod._get_carry_forward_state()
        assert result == {"projects": {}, "projectNotes": {}}  # notes are never carried forward

    def test_carries_non_completed_projects(self, diary_dir):
        week_key = "2026-03-02"
        state = {
            "weekKey": week_key,
            "projects": {"Alpha": "On Track", "Beta": "Blocked"},
            "projectNotes": {"Alpha": "going well", "Beta": "waiting on infra"},
            "notes": [],
        }
        (diary_dir / f"{week_key}.json").write_text(json.dumps(state), encoding="utf-8")

        result = diary_mod._get_carry_forward_state()
        assert result["projects"] == {"Alpha": "On Track", "Beta": "Blocked"}
        assert result["projectNotes"] == {}  # notes are not carried forward

    def test_excludes_completed_projects(self, diary_dir):
        week_key = "2026-03-02"
        state = {
            "weekKey": week_key,
            "projects": {
                "Done Project": "Done",
                "Complete Project": "Complete",
                "Completed Project": "Completed",
                "Cancelled Project": "Cancelled",
                "Canceled Project": "Canceled",
                "Active Project": "On Track",
            },
            "projectNotes": {"Active Project": "still going"},
            "notes": [],
        }
        (diary_dir / f"{week_key}.json").write_text(json.dumps(state), encoding="utf-8")

        result = diary_mod._get_carry_forward_state()
        assert list(result["projects"].keys()) == ["Active Project"]
        assert result["projectNotes"] == {}  # notes are not carried forward

    def test_completed_project_note_not_carried(self, diary_dir):
        week_key = "2026-03-02"
        state = {
            "weekKey": week_key,
            "projects": {"Shipped": "Done"},
            "projectNotes": {"Shipped": "launched on Friday"},
            "notes": [],
        }
        (diary_dir / f"{week_key}.json").write_text(json.dumps(state), encoding="utf-8")

        result = diary_mod._get_carry_forward_state()
        assert result["projects"] == {}
        assert result["projectNotes"] == {}

    def test_uses_most_recent_week(self, diary_dir):
        for week_key, projects in [
            ("2026-02-16", {"OldProject": "On Track"}),
            ("2026-03-02", {"NewProject": "Blocked"}),
        ]:
            state = {
                "weekKey": week_key,
                "projects": projects,
                "projectNotes": {},
                "notes": [],
            }
            (diary_dir / f"{week_key}.json").write_text(json.dumps(state), encoding="utf-8")

        result = diary_mod._get_carry_forward_state()
        assert list(result["projects"].keys()) == ["NewProject"]


# ---------------------------------------------------------------------------
# get_diary_markdown / list_projects
# ---------------------------------------------------------------------------


class TestGetDiaryMarkdown:
    def test_returns_markdown_string(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track")
        md = diary_mod.get_diary_markdown(week_key)
        assert isinstance(md, str)
        assert "Alpha" in md

    def test_does_not_write_md_file(self, diary_dir):
        week_key = "2026-03-02"
        md_file = diary_dir / f"{week_key}.md"
        assert not md_file.exists()

        md = diary_mod.get_diary_markdown(week_key)

        assert isinstance(md, str)
        assert not md_file.exists()

    def test_returns_current_rendered_markdown(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "Blocked", note="stuck")
        md = diary_mod.get_diary_markdown(week_key)
        assert "| Alpha | 🔴 Blocked | stuck |" in md


class TestListProjects:
    def test_returns_projects_dict(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track")
        diary_mod.update_project_status(week_key, "Beta", "Blocked")
        projects = diary_mod.list_projects(week_key)
        assert projects == {"Alpha": "On Track", "Beta": "Blocked"}

    def test_returns_empty_dict_for_new_week(self, diary_dir):
        projects = diary_mod.list_projects("2026-03-02")
        assert projects == {}


# ---------------------------------------------------------------------------
# get_or_create_week_page
# ---------------------------------------------------------------------------


class TestGetOrCreateWeekPage:
    def _fixed_today(self, d: date):
        """Context manager that pins date.today() to *d*."""
        return patch.object(diary_mod, "date", wraps=date, **{"today.return_value": d})

    def test_creates_new_page(self, diary_dir):
        today = date(2026, 3, 4)
        with patch("work_diary_mcp.diary.date") as mock_date:
            mock_date.today.return_value = today
            mock_date.fromisoformat.side_effect = date.fromisoformat
            result = diary_mod.get_or_create_week_page()

        assert result["is_new"] is True
        assert result["week_key"] == "2026-03-02"
        assert (diary_dir / "2026-03-02.json").exists()

    def test_existing_page_not_overwritten(self, diary_dir):
        today = date(2026, 3, 4)
        # Pre-create a page with a project
        state = {
            "weekKey": "2026-03-02",
            "projects": {"Existing": "Blocked"},
            "projectNotes": {},
            "notes": [],
        }
        (diary_dir / "2026-03-02.json").write_text(json.dumps(state), encoding="utf-8")

        with patch("work_diary_mcp.diary.date") as mock_date:
            mock_date.today.return_value = today
            mock_date.fromisoformat.side_effect = date.fromisoformat
            result = diary_mod.get_or_create_week_page()

        assert result["is_new"] is False
        loaded = json.loads((diary_dir / "2026-03-02.json").read_text())
        assert loaded["projects"] == {"Existing": "Blocked"}

    def test_new_page_carries_forward(self, diary_dir):
        prior = "2026-02-23"
        prior_state = {
            "weekKey": prior,
            "projects": {"CarriedProject": "At Risk"},
            "projectNotes": {"CarriedProject": "still at risk"},
            "notes": [],
        }
        (diary_dir / f"{prior}.json").write_text(json.dumps(prior_state), encoding="utf-8")

        today = date(2026, 3, 4)
        with patch("work_diary_mcp.diary.date") as mock_date:
            mock_date.today.return_value = today
            mock_date.fromisoformat.side_effect = date.fromisoformat
            diary_mod.get_or_create_week_page()

        loaded = json.loads((diary_dir / "2026-03-02.json").read_text())
        assert loaded["projects"] == {"CarriedProject": "At Risk"}
        assert loaded["projectNotes"] == {}  # notes are not carried forward


# ---------------------------------------------------------------------------
# update_project_status
# ---------------------------------------------------------------------------


class TestUpdateProjectStatus:
    def test_adds_new_project(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["projects"]["Alpha"] == "On Track"

    def test_updates_existing_project(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track")
        diary_mod.update_project_status(week_key, "Alpha", "Blocked")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["projects"]["Alpha"] == "Blocked"

    def test_case_insensitive_match(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Project Phoenix", "On Track")
        diary_mod.update_project_status(week_key, "project phoenix", "Blocked")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        # Original casing preserved, no duplicate entry
        assert "Project Phoenix" in state["projects"]
        assert "project phoenix" not in state["projects"]
        assert state["projects"]["Project Phoenix"] == "Blocked"

    def test_sets_note(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track", note="going well")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["projectNotes"]["Alpha"] == "going well"

    def test_replaces_note_by_default(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track", note="first")
        diary_mod.update_project_status(week_key, "Alpha", "On Track", note="second")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["projectNotes"]["Alpha"] == "second"

    def test_append_note(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track", note="first")
        diary_mod.update_project_status(
            week_key, "Alpha", "Blocked", note="second", append_note=True
        )
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["projectNotes"]["Alpha"] == "first — second"

    def test_append_note_no_prior_note(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(
            week_key, "Alpha", "On Track", note="only note", append_note=True
        )
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["projectNotes"]["Alpha"] == "only note"

    def test_no_note_arg_leaves_existing_note(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track", note="keep me")
        diary_mod.update_project_status(week_key, "Alpha", "Blocked")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["projectNotes"]["Alpha"] == "keep me"


# ---------------------------------------------------------------------------
# rename_project
# ---------------------------------------------------------------------------


class TestRenameProject:
    def test_renames_project(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Old Name", "On Track", note="a note")
        diary_mod.rename_project(week_key, "Old Name", "New Name")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert "New Name" in state["projects"]
        assert "Old Name" not in state["projects"]
        assert state["projectNotes"].get("New Name") == "a note"

    def test_preserves_status(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "Blocked")
        diary_mod.rename_project(week_key, "Alpha", "Beta")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["projects"]["Beta"] == "Blocked"

    def test_preserves_order(self, diary_dir):
        week_key = "2026-03-02"
        for name, status in [
            ("First", "On Track"),
            ("Second", "Blocked"),
            ("Third", "At Risk"),
        ]:
            diary_mod.update_project_status(week_key, name, status)
        diary_mod.rename_project(week_key, "Second", "Middle")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert list(state["projects"].keys()) == ["First", "Middle", "Third"]

    def test_not_found_raises(self, diary_dir):
        week_key = "2026-03-02"
        with pytest.raises(ValueError, match="not found"):
            diary_mod.rename_project(week_key, "Ghost", "Specter")

    def test_collision_raises(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track")
        diary_mod.update_project_status(week_key, "Beta", "Blocked")
        with pytest.raises(ValueError, match="already exists"):
            diary_mod.rename_project(week_key, "Alpha", "Beta")

    def test_case_insensitive_target_collision_raises(self, diary_dir):
        """Renaming to a name that differs only in case from an existing project is rejected."""
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track")
        diary_mod.update_project_status(week_key, "Beta", "Blocked")
        with pytest.raises(ValueError, match="already exists"):
            diary_mod.rename_project(week_key, "Alpha", "beta")

    def test_case_insensitive_source_match(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Project Phoenix", "On Track")
        diary_mod.rename_project(week_key, "project phoenix", "Phoenix Rewrite")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert "Phoenix Rewrite" in state["projects"]


# ---------------------------------------------------------------------------
# bulk_update_projects
# ---------------------------------------------------------------------------


class TestBulkUpdateProjects:
    def test_updates_multiple(self, diary_dir):
        week_key = "2026-03-02"
        updates = [
            {"project": "Alpha", "status": "On Track"},
            {"project": "Beta", "status": "Blocked", "note": "waiting"},
            {"project": "Gamma", "status": "Done"},
        ]
        results = diary_mod.bulk_update_projects(week_key, updates)
        assert len(results) == 3
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["projects"]["Alpha"] == "On Track"
        assert state["projects"]["Beta"] == "Blocked"
        assert state["projectNotes"]["Beta"] == "waiting"
        assert state["projects"]["Gamma"] == "Done"

    def test_single_write_cycle(self, diary_dir):
        """bulk_update should call _save_state exactly once."""
        week_key = "2026-03-02"
        updates = [
            {"project": "A", "status": "On Track"},
            {"project": "B", "status": "Blocked"},
        ]
        save_count = 0
        original_save = diary_mod._save_state

        def counting_save(state):
            nonlocal save_count
            save_count += 1
            original_save(state)

        with patch.object(diary_mod, "_save_state", side_effect=counting_save):
            diary_mod.bulk_update_projects(week_key, updates)

        assert save_count == 1

    def test_append_note_in_bulk(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track", note="first")
        diary_mod.bulk_update_projects(
            week_key,
            [
                {
                    "project": "Alpha",
                    "status": "Blocked",
                    "note": "second",
                    "append_note": True,
                }
            ],
        )
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["projectNotes"]["Alpha"] == "first — second"

    def test_returns_result_strings(self, diary_dir):
        week_key = "2026-03-02"
        results = diary_mod.bulk_update_projects(
            week_key, [{"project": "Alpha", "status": "On Track"}]
        )
        assert results == ["Alpha → On Track"]

    def test_case_insensitive_key_match_preserves_casing(self, diary_dir):
        """bulk_update matches existing keys case-insensitively and keeps original casing."""
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Project Phoenix", "On Track")
        diary_mod.bulk_update_projects(
            week_key, [{"project": "project phoenix", "status": "Blocked"}]
        )
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert "Project Phoenix" in state["projects"]
        assert "project phoenix" not in state["projects"]
        assert state["projects"]["Project Phoenix"] == "Blocked"


# ---------------------------------------------------------------------------
# remove_project
# ---------------------------------------------------------------------------


class TestRemoveProject:
    def test_removes_project_and_note(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track", note="a note")
        diary_mod.remove_project(week_key, "Alpha")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert "Alpha" not in state["projects"]
        assert "Alpha" not in state["projectNotes"]

    def test_not_found_raises(self, diary_dir):
        week_key = "2026-03-02"
        with pytest.raises(ValueError, match="not found"):
            diary_mod.remove_project(week_key, "Ghost")

    def test_case_insensitive_match(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Project Phoenix", "On Track")
        diary_mod.remove_project(week_key, "project phoenix")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert "Project Phoenix" not in state["projects"]


# ---------------------------------------------------------------------------
# clear_project_note
# ---------------------------------------------------------------------------


class TestClearProjectNote:
    def test_clears_note_leaves_status(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track", note="a note")
        diary_mod.clear_project_note(week_key, "Alpha")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["projects"]["Alpha"] == "On Track"
        assert "Alpha" not in state["projectNotes"]

    def test_not_found_raises(self, diary_dir):
        week_key = "2026-03-02"
        with pytest.raises(ValueError, match="not found"):
            diary_mod.clear_project_note(week_key, "Ghost")


# ---------------------------------------------------------------------------
# add_note / edit_note / delete_note
# ---------------------------------------------------------------------------


class TestNotes:
    def test_add_note_appends(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.add_note(week_key, "first note")
        diary_mod.add_note(week_key, "second note")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert len(state["notes"]) == 2
        assert state["notes"][0]["content"] == "first note"
        assert state["notes"][1]["content"] == "second note"

    def test_add_note_has_no_automatic_timestamp(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.add_note(week_key, "check timestamp")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert "timestamp" not in state["notes"][0]

    def test_edit_note_replaces_content(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.add_note(week_key, "original content")
        diary_mod.edit_note(week_key, 1, "updated content")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["notes"][0]["content"] == "updated content"

    def test_edit_note_preserves_legacy_timestamp(self, diary_dir):
        """edit_note should leave a legacy timestamp field intact if present."""
        week_key = "2026-03-02"
        legacy_ts = "2026-03-02T10:00:00+00:00"
        state = {
            "weekKey": week_key,
            "projects": {},
            "projectNotes": {},
            "notes": [{"timestamp": legacy_ts, "content": "original"}],
        }
        (diary_dir / f"{week_key}.json").write_text(json.dumps(state), encoding="utf-8")

        diary_mod.edit_note(week_key, 1, "updated")
        state_after = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state_after["notes"][0]["timestamp"] == legacy_ts
        assert state_after["notes"][0]["content"] == "updated"

    def test_edit_note_out_of_range_raises(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.add_note(week_key, "only note")
        with pytest.raises(ValueError, match="out of range"):
            diary_mod.edit_note(week_key, 2, "oops")

    def test_edit_note_zero_index_raises(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.add_note(week_key, "a note")
        with pytest.raises(ValueError, match="out of range"):
            diary_mod.edit_note(week_key, 0, "oops")

    def test_delete_note_removes_entry(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.add_note(week_key, "first")
        diary_mod.add_note(week_key, "second")
        diary_mod.add_note(week_key, "third")
        diary_mod.delete_note(week_key, 2)
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert len(state["notes"]) == 2
        assert state["notes"][0]["content"] == "first"
        assert state["notes"][1]["content"] == "third"

    def test_delete_note_returns_content(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.add_note(week_key, "deletable note")
        deleted = diary_mod.delete_note(week_key, 1)
        assert deleted == "deletable note"

    def test_delete_note_out_of_range_raises(self, diary_dir):
        week_key = "2026-03-02"
        with pytest.raises(ValueError, match="out of range"):
            diary_mod.delete_note(week_key, 1)

    def test_edit_note_negative_index_raises(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.add_note(week_key, "a note")
        with pytest.raises(ValueError, match="out of range"):
            diary_mod.edit_note(week_key, -1, "oops")

    def test_delete_note_negative_index_raises(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.add_note(week_key, "a note")
        with pytest.raises(ValueError, match="out of range"):
            diary_mod.delete_note(week_key, -1)

    def test_delete_note_zero_index_raises(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.add_note(week_key, "a note")
        with pytest.raises(ValueError, match="out of range"):
            diary_mod.delete_note(week_key, 0)


# ---------------------------------------------------------------------------
# list_week_keys
# ---------------------------------------------------------------------------


class TestListWeekKeys:
    def test_empty_dir(self, diary_dir):
        assert diary_mod.list_week_keys() == []

    def test_returns_sorted_keys(self, diary_dir):
        for week_key in ("2026-03-09", "2026-02-23", "2026-03-02"):
            state = {
                "weekKey": week_key,
                "projects": {},
                "projectNotes": {},
                "notes": [],
            }
            (diary_dir / f"{week_key}.json").write_text(json.dumps(state), encoding="utf-8")
        assert diary_mod.list_week_keys() == [
            "2026-02-23",
            "2026-03-02",
            "2026-03-09",
        ]

    def test_ignores_non_week_json_files(self, diary_dir):
        (diary_dir / "notes.json").write_text("{}", encoding="utf-8")
        (diary_dir / "2026-03-02.json").write_text(
            json.dumps(
                {
                    "weekKey": "2026-03-02",
                    "projects": {},
                    "projectNotes": {},
                    "notes": [],
                }
            ),
            encoding="utf-8",
        )
        assert diary_mod.list_week_keys() == ["2026-03-02"]


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


class TestMarkdownRendering:
    def test_notes_are_numbered(self, diary_dir):
        from work_diary_mcp.markdown import render_diary

        state = {
            "weekKey": "2026-03-02",
            "projects": {},
            "projectNotes": {},
            "notes": [
                {"content": "first"},
                {"content": "second"},
            ],
        }
        md = render_diary(state)
        assert "[1]" in md
        assert "[2]" in md

    def test_contains_section_headers(self, diary_dir):
        from work_diary_mcp.markdown import render_diary

        state = {
            "weekKey": "2026-03-02",
            "projects": {},
            "projectNotes": {},
            "notes": [],
        }
        md = render_diary(state)
        assert "## Project Status" in md
        assert "## Notes" in md

    def test_empty_projects_placeholder(self, diary_dir):
        from work_diary_mcp.markdown import render_diary

        state = {
            "weekKey": "2026-03-02",
            "projects": {},
            "projectNotes": {},
            "notes": [],
        }
        md = render_diary(state)
        assert "no projects yet" in md

    def test_empty_notes_placeholder(self, diary_dir):
        from work_diary_mcp.markdown import render_diary

        state = {
            "weekKey": "2026-03-02",
            "projects": {},
            "projectNotes": {},
            "notes": [],
        }
        md = render_diary(state)
        assert "no notes yet" in md

    def test_project_without_note_has_empty_cell(self, diary_dir):
        from work_diary_mcp.markdown import render_diary

        state = {
            "weekKey": "2026-03-02",
            "projects": {"Alpha": "On Track"},
            "projectNotes": {},
            "notes": [],
        }
        md = render_diary(state)
        # The Notes cell for Alpha should be empty: "| Alpha | ... |  |"
        assert "| Alpha |" in md
        lines = [line for line in md.splitlines() if "| Alpha |" in line]
        assert len(lines) == 1
        assert lines[0].endswith("|  |")

    def test_project_status_formatted(self, diary_dir):
        from work_diary_mcp.markdown import render_diary

        state = {
            "weekKey": "2026-03-02",
            "projects": {"Alpha": "on track"},
            "projectNotes": {},
            "notes": [],
        }
        md = render_diary(state)
        assert "🟢 On Track" in md

    def test_project_note_included(self, diary_dir):
        from work_diary_mcp.markdown import render_diary

        state = {
            "weekKey": "2026-03-02",
            "projects": {"Alpha": "Blocked"},
            "projectNotes": {"Alpha": "waiting on infra"},
            "notes": [],
        }
        md = render_diary(state)
        assert "waiting on infra" in md

    def test_windows_newlines_in_table_cells_are_normalized(self, diary_dir):
        from work_diary_mcp.markdown import render_diary

        state = {
            "weekKey": "2026-03-02",
            "projects": {"Alpha": "Blocked"},
            "projectNotes": {"Alpha": "line one\r\nline two"},
            "notes": [],
        }
        md = render_diary(state)
        assert "line one<br>line two" in md
        assert "\r" not in md


# ---------------------------------------------------------------------------
# Jira linkification
# ---------------------------------------------------------------------------


class TestLinkifyJiraRefs:
    def test_bare_ticket_becomes_link(self):
        from work_diary_mcp.jira import linkify_jira_refs

        assert linkify_jira_refs("TF-34398") == (
            "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)"
        )

    def test_all_known_prefixes(self):
        from work_diary_mcp.jira import JIRA_BASE_URL, linkify_jira_refs

        prefixes = ["TF", "RDPR", "TFDN", "SECGRC", "IND", "CAG"]
        for prefix in prefixes:
            ticket = f"{prefix}-1234"
            result = linkify_jira_refs(ticket)
            assert result == f"[{ticket}]({JIRA_BASE_URL}/{ticket})", (
                f"Failed for prefix {prefix!r}"
            )

    def test_ticket_mid_sentence(self):
        from work_diary_mcp.jira import linkify_jira_refs

        result = linkify_jira_refs("blocked by TF-34398 and RDPR-1234")
        assert "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)" in result
        assert "[RDPR-1234](https://hashicorp.atlassian.net/browse/RDPR-1234)" in result

    def test_multiple_tickets_in_one_string(self):
        from work_diary_mcp.jira import linkify_jira_refs

        result = linkify_jira_refs("TF-1000 and TF-2000")
        assert "[TF-1000](https://hashicorp.atlassian.net/browse/TF-1000)" in result
        assert "[TF-2000](https://hashicorp.atlassian.net/browse/TF-2000)" in result

    def test_already_linked_ticket_not_double_linked(self):
        from work_diary_mcp.jira import linkify_jira_refs

        already_linked = "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)"
        assert linkify_jira_refs(already_linked) == already_linked

    def test_already_linked_ticket_mid_sentence_not_double_linked(self):
        from work_diary_mcp.jira import linkify_jira_refs

        text = "see [TF-34398](https://hashicorp.atlassian.net/browse/TF-34398) for details"
        assert linkify_jira_refs(text) == text

    def test_fewer_than_three_digits_not_matched(self):
        from work_diary_mcp.jira import linkify_jira_refs

        # TF-12 has only 2 digits — should not be linkified
        assert linkify_jira_refs("TF-12") == "TF-12"

    def test_exactly_three_digits_matched(self):
        from work_diary_mcp.jira import linkify_jira_refs

        result = linkify_jira_refs("CAG-516")
        assert result == "[CAG-516](https://hashicorp.atlassian.net/browse/CAG-516)"

    def test_exactly_four_digits_matched(self):
        from work_diary_mcp.jira import linkify_jira_refs

        result = linkify_jira_refs("TF-1234")
        assert result == "[TF-1234](https://hashicorp.atlassian.net/browse/TF-1234)"

    def test_more_than_four_digits_matched(self):
        from work_diary_mcp.jira import linkify_jira_refs

        result = linkify_jira_refs("TF-123456")
        assert result == "[TF-123456](https://hashicorp.atlassian.net/browse/TF-123456)"

    def test_unknown_prefix_not_matched(self):
        from work_diary_mcp.jira import linkify_jira_refs

        assert linkify_jira_refs("XYZ-1234") == "XYZ-1234"

    def test_case_insensitive_match_uppercases_key(self):
        from work_diary_mcp.jira import linkify_jira_refs

        result = linkify_jira_refs("tf-34398")
        assert result == "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)"

    def test_no_tickets_returns_string_unchanged(self):
        from work_diary_mcp.jira import linkify_jira_refs

        text = "no tickets here, just plain text"
        assert linkify_jira_refs(text) == text

    def test_empty_string(self):
        from work_diary_mcp.jira import linkify_jira_refs

        assert linkify_jira_refs("") == ""

    def test_mixed_linked_and_bare(self):
        """A string with one already-linked and one bare ticket handles both correctly."""
        from work_diary_mcp.jira import linkify_jira_refs

        text = "[TF-1000](https://hashicorp.atlassian.net/browse/TF-1000) and TF-2000"
        result = linkify_jira_refs(text)
        assert "[TF-1000](https://hashicorp.atlassian.net/browse/TF-1000)" in result
        assert "[TF-2000](https://hashicorp.atlassian.net/browse/TF-2000)" in result
        # TF-1000 must not be double-linked
        assert result.count("TF-1000") == 2  # once in label, once in URL


# ---------------------------------------------------------------------------
# Jira linkification — diary integration
# ---------------------------------------------------------------------------


class TestJiraLinkificationIntegration:
    def test_bare_ticket_in_project_name_is_linked(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "TF-34398", "On Track")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)" in state["projects"]

    def test_bare_ticket_in_note_is_linked(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "Blocked", note="blocked by TF-34398")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert (
            "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)"
            in state["projectNotes"]["Alpha"]
        )

    def test_already_linked_project_name_unchanged(self, diary_dir):
        week_key = "2026-03-02"
        linked = "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)"
        diary_mod.update_project_status(week_key, linked, "On Track")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert linked in state["projects"]
        assert state["projects"][linked] == "On Track"

    def test_already_linked_note_unchanged(self, diary_dir):
        week_key = "2026-03-02"
        linked = "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)"
        diary_mod.update_project_status(week_key, "Alpha", "Blocked", note=linked)
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert state["projectNotes"]["Alpha"] == linked

    def test_append_note_linkifies_new_fragment(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Alpha", "On Track", note="initial note")
        diary_mod.update_project_status(
            week_key, "Alpha", "Blocked", note="see TF-9999", append_note=True
        )
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        note = state["projectNotes"]["Alpha"]
        assert "initial note" in note
        assert "[TF-9999](https://hashicorp.atlassian.net/browse/TF-9999)" in note

    def test_rename_linkifies_new_name(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.update_project_status(week_key, "Old Name", "On Track")
        diary_mod.rename_project(week_key, "Old Name", "TF-34398")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)" in state["projects"]
        assert "Old Name" not in state["projects"]

    def test_bulk_update_linkifies_project_and_note(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.bulk_update_projects(
            week_key,
            [
                {"project": "TF-34398", "status": "On Track", "note": "see RDPR-1234"},
            ],
        )
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)" in state["projects"]
        notes = state["projectNotes"]
        linked_key = "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)"
        assert "[RDPR-1234](https://hashicorp.atlassian.net/browse/RDPR-1234)" in notes[linked_key]

    def test_add_note_linkifies_content(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.add_note(week_key, "opened TF-34398 to track this")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert (
            "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)"
            in state["notes"][0]["content"]
        )

    def test_edit_note_linkifies_new_content(self, diary_dir):
        week_key = "2026-03-02"
        diary_mod.add_note(week_key, "original note")
        diary_mod.edit_note(week_key, 1, "updated, see TF-34398")
        state = json.loads((diary_dir / f"{week_key}.json").read_text())
        assert (
            "[TF-34398](https://hashicorp.atlassian.net/browse/TF-34398)"
            in state["notes"][0]["content"]
        )
