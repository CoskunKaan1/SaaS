"""Veritabanı satırlarının Python karşılıkları.

Bu sınıflar yalnızca veri taşır; iş kuralları ``core.services`` altındadır.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Outcome(str, Enum):
    OK = "ok"
    ERROR = "error"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Department:
    id: int
    name: str
    cost_center: str


@dataclass(frozen=True)
class Team:
    id: int
    department_id: int
    name: str
    department_name: str = ""


@dataclass(frozen=True)
class User:
    id: int
    team_id: int
    full_name: str
    email: str
    role: str
    is_simulated: bool
    is_active: bool
    team_name: str = ""


@dataclass(frozen=True)
class Provider:
    id: int
    name: str
    kind: str  # external | internal


@dataclass(frozen=True)
class ApiService:
    id: int
    provider_id: int
    name: str
    unit_name: str
    credit_per_unit: Decimal
    is_active: bool = True
    provider_name: str = ""
    provider_kind: str = ""


@dataclass(frozen=True)
class TeamBudget:
    id: int
    team_id: int
    credit_limit: Decimal
    warn_percent: int
    started_at: datetime
    closed_at: datetime | None = None
    close_reason: str | None = None


@dataclass(frozen=True)
class BudgetStatus:
    """Bir ekibin aktif dönem bütçesinin anlık özeti (vw_TeamBudgetStatus)."""

    team_budget_id: int
    team_id: int
    team_name: str
    department_name: str
    credit_limit: Decimal
    warn_percent: int
    started_at: datetime
    spent: Decimal
    calls: int
    rejected: int

    @property
    def remaining(self) -> Decimal:
        return max(Decimal(0), self.credit_limit - self.spent)

    @property
    def ratio(self) -> float:
        if self.credit_limit <= 0:
            return 0.0
        return float(self.spent / self.credit_limit)

    @property
    def state(self) -> Severity:
        # Reddedilen çağrı varsa ekip fiilen limitte demektir (kalan kredi bir
        # çağrıya yetmiyor); limit sonradan yükseltildiyse eşik altına düşer.
        if self.ratio >= 1 or (self.rejected and self.ratio * 100 >= self.warn_percent):
            return Severity.CRITICAL
        if self.ratio * 100 >= self.warn_percent:
            return Severity.WARNING
        return Severity.INFO


@dataclass(frozen=True)
class UsageRecord:
    id: int
    team_budget_id: int
    user_id: int
    service_id: int
    units: int
    credits: Decimal
    status_code: int
    latency_ms: int
    outcome: Outcome
    created_at: datetime
    user_name: str = ""
    team_name: str = ""
    service_name: str = ""


@dataclass(frozen=True)
class Notification:
    id: int
    team_id: int | None
    severity: Severity
    title: str
    body: str
    created_at: datetime
    is_read: bool = False
    team_name: str = ""


@dataclass(frozen=True)
class SimulationProfile:
    user_id: int
    persona: str
    calls_per_minute: int
    error_rate: float
    is_enabled: bool
    user_name: str = ""
    team_id: int = 0
    team_name: str = ""


@dataclass(frozen=True)
class ServiceShare:
    service_id: int
    service_name: str
    credits: Decimal
    calls: int


@dataclass(frozen=True)
class TimePoint:
    bucket: datetime
    credits: Decimal
    calls: int
