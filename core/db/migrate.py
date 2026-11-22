"""Veritabanını oluşturur ve şemayı uygular."""

from __future__ import annotations

import re
from pathlib import Path

from core.config import DatabaseSettings
from core.db.connection import connect

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
_GO = re.compile(r"^\s*GO\s*$", re.IGNORECASE | re.MULTILINE)
_SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def split_batches(script: str) -> list[str]:
    """T-SQL betiğini ``GO`` ayırıcılarından parçalara böler."""
    return [b.strip() for b in _GO.split(script) if b.strip()]


def ensure_database(settings: DatabaseSettings) -> bool:
    """Veritabanı yoksa oluşturur. Oluşturulduysa True döner."""
    if not _SAFE_NAME.match(settings.database):
        raise ValueError(f"Geçersiz veritabanı adı: {settings.database!r}")
    conn = connect(settings, database="master", autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT DB_ID(?)", settings.database)
        if cur.fetchone()[0] is not None:
            return False
        cur.execute(f"CREATE DATABASE [{settings.database}]")
        return True
    finally:
        conn.close()


def apply_schema(settings: DatabaseSettings) -> None:
    script = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = connect(settings, autocommit=True)
    try:
        cur = conn.cursor()
        for batch in split_batches(script):
            cur.execute(batch)
    finally:
        conn.close()


def migrate(settings: DatabaseSettings) -> bool:
    created = ensure_database(settings)
    apply_schema(settings)
    return created
