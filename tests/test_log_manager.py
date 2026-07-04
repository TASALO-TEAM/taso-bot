"""Tests para src/services/log_manager.py."""

import os
import time

import pytest

from src.services import log_manager


def _make_service_tree(base_dir, display_name, with_active=True, archive_files=None):
    """Crea un árbol logs/ realista para un servicio dentro de base_dir."""
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    if with_active:
        (logs_dir / f"{display_name}.log").write_text("linea de log activa\n")
        (logs_dir / f"{display_name}-errors.log").write_text("")
    if archive_files:
        archive_dir = logs_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        for fname, content in archive_files.items():
            (archive_dir / fname).write_text(content)
    return logs_dir


def test_normalize_service_aliases():
    assert log_manager.normalize_service("bot") == "bot"
    assert log_manager.normalize_service("API") == "api"
    assert log_manager.normalize_service("web") == "web"
    assert log_manager.normalize_service("app") == "web"
    assert log_manager.normalize_service("miniapp") == "web"
    assert log_manager.normalize_service("wat") is None


def test_format_size_human_readable():
    assert log_manager.format_size(500) == "500 B"
    assert log_manager.format_size(2048) == "2.0 KB"
    assert log_manager.format_size(5 * 1024 * 1024) == "5.0 MB"


def test_get_service_log_info_missing_directory(tmp_path, monkeypatch):
    missing_dir = tmp_path / "does-not-exist" / "logs"
    monkeypatch.setattr(
        log_manager, "_service_logs_dir", lambda service: str(missing_dir)
    )

    info = log_manager.get_service_log_info("web")

    assert info.exists is False
    assert info.active_log_path is None
    assert "No se encontró el directorio" in info.error


def test_get_service_log_info_active_and_archives(tmp_path, monkeypatch):
    logs_dir = _make_service_tree(
        tmp_path,
        "taso-api",
        with_active=True,
        archive_files={
            "taso-api_2026-07-01_10-00-00.log": "old1",
            "taso-api_2026-07-02_11-00-00.log": "old2",
        },
    )
    monkeypatch.setattr(log_manager, "_service_logs_dir", lambda service: str(logs_dir))

    info = log_manager.get_service_log_info("api")

    assert info.exists is True
    assert info.active_log_path is not None
    assert info.active_size_bytes > 0
    assert len(info.archives) == 2
    # Orden descendente por fecha
    assert info.archives[0].date_str == "2026-07-02"
    assert info.archives[1].date_str == "2026-07-01"


def test_find_archive_by_date_exact_match(tmp_path, monkeypatch):
    logs_dir = _make_service_tree(
        tmp_path,
        "taso-bot",
        archive_files={"taso-bot_2026-07-01_09-00-00.log": "contenido"},
    )
    monkeypatch.setattr(log_manager, "_service_logs_dir", lambda service: str(logs_dir))

    archived, available = log_manager.find_archive_by_date("bot", "2026-07-01")

    assert archived is not None
    assert archived.date_str == "2026-07-01"
    assert available == ["2026-07-01"]


def test_find_archive_by_date_no_match_suggests_dates(tmp_path, monkeypatch):
    logs_dir = _make_service_tree(
        tmp_path,
        "taso-bot",
        archive_files={"taso-bot_2026-07-01_09-00-00.log": "x"},
    )
    monkeypatch.setattr(log_manager, "_service_logs_dir", lambda service: str(logs_dir))

    archived, available = log_manager.find_archive_by_date("bot", "2026-01-01")

    assert archived is None
    assert available == ["2026-07-01"]


def test_clear_archives_removes_only_archived_files(tmp_path, monkeypatch):
    logs_dir = _make_service_tree(
        tmp_path,
        "taso-bot",
        with_active=True,
        archive_files={
            "taso-bot_2026-07-01_09-00-00.log": "x",
            "taso-bot_2026-07-02_09-00-00.log": "y",
        },
    )
    monkeypatch.setattr(log_manager, "_service_logs_dir", lambda service: str(logs_dir))

    results = log_manager.clear_archives("bot")

    assert results["bot"]["removed"] == 2
    assert results["bot"]["bytes_freed"] > 0
    # El log activo no se toca
    assert (logs_dir / "taso-bot.log").exists()
    assert not (logs_dir / "archive").exists() or list((logs_dir / "archive").iterdir()) == []


def test_clear_archives_all_services(tmp_path, monkeypatch):
    dirs = {
        "bot": _make_service_tree(
            tmp_path / "bot", "taso-bot", archive_files={"taso-bot_2026-07-01_00-00-00.log": "x"}
        ),
        "api": _make_service_tree(
            tmp_path / "api", "taso-api", archive_files={"taso-api_2026-07-01_00-00-00.log": "x"}
        ),
        "web": _make_service_tree(tmp_path / "web", "taso-app"),
    }
    monkeypatch.setattr(log_manager, "_service_logs_dir", lambda service: str(dirs[service]))

    results = log_manager.clear_archives(None)

    assert results["bot"]["removed"] == 1
    assert results["api"]["removed"] == 1
    assert results["web"]["removed"] == 0
