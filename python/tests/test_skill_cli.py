"""Tests for the skill CLI (skill/cli.py) reviews commands."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

import work_diary_mcp.config as config_mod
import work_diary_mcp.diary as diary_mod

CLI_PATH = Path(__file__).resolve().parents[2] / "skill" / "cli.py"
LINK = "[PROJ-1](https://jira.example.com/browse/PROJ-1)"


@pytest.fixture()
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Load skill/cli.py with the data dir and settings isolated to tmp_path."""
    caches = (
        config_mod.get_data_dir,
        config_mod.get_sync_path,
        config_mod.get_auto_sync,
        config_mod.get_reviews_title,
    )
    monkeypatch.setenv("WORK_DIARY_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("WORK_DIARY_REVIEWS_TITLE", raising=False)
    monkeypatch.delenv("WORK_DIARY_AUTO_SYNC", raising=False)
    monkeypatch.setattr(config_mod, "SETTINGS_FILE", tmp_path / "no-settings.toml")
    for fn in caches:
        fn.cache_clear()
    diary_mod._reset_caches()

    spec = importlib.util.spec_from_file_location("skill_cli", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module

    diary_mod._reset_caches()
    for fn in caches:
        fn.cache_clear()


def _run(cli, *argv: str) -> None:
    args = cli.build_parser().parse_args(list(argv))
    args.func(args)


def _payload(**overrides) -> str:
    row = {"item": LINK, "role": "Delegate", "story_status": "In Progress", "status": "To Do"}
    row.update(overrides)
    return json.dumps([row])


def test_list_reviews_empty(cli, capsys):
    _run(cli, "list-reviews")
    assert "No reviews tracked yet" in capsys.readouterr().out


def test_bulk_update_then_list(cli, capsys):
    _run(cli, "bulk-update-reviews", "--json", _payload())
    assert "Updated 1 review item(s)" in capsys.readouterr().out

    _run(cli, "list-reviews")
    out = capsys.readouterr().out
    assert "PROJ-1" in out
    assert "Delegate" in out
    assert "In Progress" in out


def test_list_reviews_json(cli, capsys):
    _run(cli, "bulk-update-reviews", "--json", _payload())
    capsys.readouterr()

    _run(cli, "list-reviews", "--json")
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 1
    entry = next(iter(data.values()))
    assert entry["role"] == "Delegate"
    assert entry["storyStatus"] == "In Progress"


def test_update_does_not_duplicate_row(cli, capsys):
    _run(cli, "bulk-update-reviews", "--json", _payload())
    _run(cli, "bulk-update-reviews", "--json", _payload(status="Reviewed & Approved"))
    capsys.readouterr()

    _run(cli, "list-reviews", "--json")
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 1


def test_remove_review(cli, capsys):
    _run(cli, "bulk-update-reviews", "--json", _payload())
    capsys.readouterr()

    _run(cli, "remove-review", "--item", LINK)
    assert "Removed" in capsys.readouterr().out

    _run(cli, "list-reviews")
    assert "No reviews tracked yet" in capsys.readouterr().out
