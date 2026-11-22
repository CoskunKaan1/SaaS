from __future__ import annotations

from dataclasses import dataclass

from core.config import Settings
from core.connectors.testusers import SimulationEngine
from core.db.repository import Repository
from core.services.credit_service import CreditService
from core.services.events import EventBus


@dataclass
class AppContext:
    """Sayfaların ihtiyaç duyduğu servislerin tek pakette taşınması."""

    settings: Settings
    repo: Repository
    credit: CreditService
    engine: SimulationEngine

    @property
    def bus(self) -> EventBus:
        return self.credit.bus
