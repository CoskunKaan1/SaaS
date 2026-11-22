from __future__ import annotations

import random
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.services.credit_service import CreditService  # noqa: E402
from core.services.events import EventBus  # noqa: E402
from core.services.seed import seed_demo_data  # noqa: E402
from tests.fakes import InMemoryRepository  # noqa: E402


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def seeded_repo(repo) -> InMemoryRepository:
    seed_demo_data(repo)
    return repo


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def credit(seeded_repo, bus) -> CreditService:
    return CreditService(seeded_repo, bus)


@pytest.fixture
def small_team(repo, bus):
    """Tek ekip, tek servis (1 kredi/birim), 100 kredi limit, %80 uyarı."""
    dept = repo.add_department("Test", "CC-1")
    team = repo.add_team(dept, "Alfa")
    repo.open_budget(team, Decimal(100), 80)
    prov = repo.add_provider("Sağlayıcı", "external")
    svc = repo.add_service(prov, "Servis", "istek", Decimal("1"))
    repo.set_team_access(team, [svc])
    user = repo.add_user(team, "Ayşe", "ayse@test.local")
    return {"repo": repo, "credit": CreditService(repo, bus), "team": team, "service": svc, "user": user}


@pytest.fixture
def rng() -> random.Random:
    return random.Random(42)
