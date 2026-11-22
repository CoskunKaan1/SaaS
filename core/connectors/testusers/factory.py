"""Test kullanıcısı oluşturma ve var olan kullanıcıyı simülasyona dahil etme."""

from __future__ import annotations

import re
import unicodedata

from core.connectors.testusers.personas import PERSONAS
from core.db.repository import Repository


class TestUserError(ValueError):
    __test__ = False  # pytest bunu test sınıfı sanmasın


def _slug(text: str) -> str:
    text = text.translate(str.maketrans("ıİşŞğĞüÜöÖçÇ", "iIsSgGuUoOcC"))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", ".", text.lower()).strip(".") or "test"


def _validate(persona: str, calls_per_minute: int, error_rate: float) -> None:
    if persona not in PERSONAS:
        raise TestUserError(f"Bilinmeyen persona: {persona}")
    if not 1 <= calls_per_minute <= 600:
        raise TestUserError("Dakika başı çağrı 1 ile 600 arasında olmalı.")
    if not 0 <= error_rate <= 1:
        raise TestUserError("Hata oranı 0 ile 1 arasında olmalı.")


def create_test_user(
    repo: Repository,
    team_id: int,
    full_name: str,
    persona: str = "steady",
    calls_per_minute: int = 10,
    error_rate: float = 0.02,
    enabled: bool = True,
) -> int:
    """Yeni bir sanal kullanıcı oluşturur, profilini bağlar ve ID'sini döndürür."""
    full_name = full_name.strip()
    if not full_name:
        raise TestUserError("Kullanıcı adı boş olamaz.")
    _validate(persona, calls_per_minute, error_rate)

    existing = {u.email for u in repo.list_users()}
    base = _slug(full_name)
    email, n = f"{base}@test.local", 2
    while email in existing:
        email, n = f"{base}.{n}@test.local", n + 1

    with repo.transaction():
        uid = repo.add_user(team_id, full_name, email, "service", True)
        repo.upsert_profile(uid, persona, calls_per_minute, error_rate, enabled)
    return uid


def attach_user(
    repo: Repository,
    user_id: int,
    persona: str = "steady",
    calls_per_minute: int = 10,
    error_rate: float = 0.02,
    enabled: bool = True,
) -> None:
    """Var olan bir kullanıcıyı ID'si ile simülasyona dahil eder."""
    _validate(persona, calls_per_minute, error_rate)
    user = repo.get_user(user_id)
    if user is None:
        raise TestUserError(f"#{user_id} numaralı kullanıcı bulunamadı.")
    if not user.is_active:
        raise TestUserError(f"{user.full_name} pasif durumda.")
    repo.upsert_profile(user_id, persona, calls_per_minute, error_rate, enabled)
