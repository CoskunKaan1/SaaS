"""SQL Server'a bağlanmadan doğrulanabilen veritabanı katmanı testleri."""

from pathlib import Path

import pytest

from core.config import DatabaseSettings, Settings, load_settings, save_settings
from core.db import connection
from core.db.migrate import SCHEMA_PATH, split_batches
from core.services.seed import seed_demo_data

EXPECTED_TABLES = {
    "Departments", "Teams", "Users", "ApiProviders", "ApiServices", "TeamServiceAccess",
    "TeamBudgets", "UsageRecords", "Notifications", "SimulationProfiles",
}


def test_schema_splits_into_batches_and_defines_all_tables():
    script = SCHEMA_PATH.read_text(encoding="utf-8")
    batches = split_batches(script)
    assert len(batches) >= 15
    assert not any(b.upper().startswith("GO") for b in batches)
    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE dbo.{table}" in script
    assert "CREATE OR ALTER VIEW dbo.vw_TeamBudgetStatus" in script
    assert "CREATE OR ALTER PROCEDURE dbo.sp_ResetTeamBudget" in script


def test_split_batches_ignores_go_inside_words():
    assert split_batches("SELECT 'GOAL'\nGO\nSELECT 2\n  go  \n") == ["SELECT 'GOAL'", "SELECT 2"]


def test_driver_detection_prefers_newest(monkeypatch):
    monkeypatch.setattr(connection.pyodbc, "drivers", lambda: ["SQL Server", "ODBC Driver 18 for SQL Server"])
    assert connection.detect_driver() == "ODBC Driver 18 for SQL Server"
    monkeypatch.setattr(connection.pyodbc, "drivers", lambda: ["SQL Server"])
    assert connection.detect_driver() == "SQL Server"
    monkeypatch.setattr(connection.pyodbc, "drivers", lambda: [])
    with pytest.raises(connection.DatabaseUnavailable):
        connection.detect_driver()


def test_connection_string_trusted_and_sql_auth(monkeypatch):
    monkeypatch.setattr(connection.pyodbc, "drivers", lambda: ["ODBC Driver 18 for SQL Server"])
    trusted = connection.build_connection_string(DatabaseSettings(server="srv", database="db"))
    assert "Trusted_Connection=yes" in trusted and "TrustServerCertificate=yes" in trusted
    assert "SERVER=srv" in trusted and "DATABASE=db" in trusted
    sql = connection.build_connection_string(
        DatabaseSettings(trusted_connection=False, username="sa", password="x"), database="master"
    )
    assert "UID=sa" in sql and "PWD=x" in sql and "DATABASE=master" in sql


def test_settings_roundtrip(tmp_path: Path, monkeypatch):
    for key in ("KREDI_DB_SERVER", "KREDI_DB_NAME", "KREDI_DB_USER", "KREDI_DB_PASSWORD", "KREDI_DB_DRIVER"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "config.ini"
    original = Settings(database=DatabaseSettings(server=r".\SQLEXPRESS", database="X", trusted_connection=False,
                                                  username="u", password="p"))
    save_settings(original, path)
    loaded = load_settings(path)
    assert loaded.database == original.database
    assert loaded.simulation == original.simulation


def test_env_overrides_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KREDI_DB_SERVER", "env-server")
    monkeypatch.setenv("KREDI_DB_USER", "sa")
    settings = load_settings(tmp_path / "missing.ini")
    assert settings.database.server == "env-server"
    assert settings.database.trusted_connection is False


def test_legacy_driver_datetime_strings_are_parsed():
    from datetime import datetime

    from core.db.sqlserver import _dt

    assert _dt("2026-11-21 09:36:41.1230000") == datetime(2026, 11, 21, 9, 36, 41, 123000)
    assert _dt("2026-11-21 09:36:41") == datetime(2026, 11, 21, 9, 36, 41)
    assert _dt(None) is None


def test_seed_is_idempotent(repo):
    assert seed_demo_data(repo) is True
    users = len(repo.list_users())
    assert seed_demo_data(repo) is False
    assert len(repo.list_users()) == users
    assert all(repo.list_team_services(t.id) for t in repo.list_teams())
    assert len(repo.budget_statuses()) == len(repo.list_teams())
