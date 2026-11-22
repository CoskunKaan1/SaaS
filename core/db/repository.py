"""Depo (repository) arayüzü.

İş katmanı veritabanına yalnızca bu arayüz üzerinden erişir. Üretimde
``SqlServerRepository`` kullanılır; birim testleri aynı sözleşmeyi uygulayan
bellek içi bir sahte depo ile çalışır (bkz. ``tests/fakes.py``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from datetime import datetime
from decimal import Decimal

from core.models import (
    ApiService,
    BudgetStatus,
    Department,
    Notification,
    Outcome,
    Provider,
    ServiceShare,
    Severity,
    SimulationProfile,
    Team,
    TeamBudget,
    TimePoint,
    UsageRecord,
    User,
)


class Repository(ABC):
    # --- altyapı -------------------------------------------------------
    @abstractmethod
    def transaction(self) -> AbstractContextManager[None]: ...

    @abstractmethod
    def is_empty(self) -> bool: ...

    def close(self) -> None:  # pragma: no cover - varsayılan boş
        pass

    # --- organizasyon --------------------------------------------------
    @abstractmethod
    def list_departments(self) -> list[Department]: ...

    @abstractmethod
    def add_department(self, name: str, cost_center: str) -> int: ...

    @abstractmethod
    def list_teams(self) -> list[Team]: ...

    @abstractmethod
    def add_team(self, department_id: int, name: str) -> int: ...

    # --- kullanıcılar --------------------------------------------------
    @abstractmethod
    def list_users(self) -> list[User]: ...

    @abstractmethod
    def get_user(self, user_id: int) -> User | None: ...

    @abstractmethod
    def add_user(
        self, team_id: int, full_name: str, email: str, role: str = "member", is_simulated: bool = False
    ) -> int: ...

    @abstractmethod
    def set_user_active(self, user_id: int, active: bool) -> None: ...

    # --- servis kataloğu -----------------------------------------------
    @abstractmethod
    def list_providers(self) -> list[Provider]: ...

    @abstractmethod
    def add_provider(self, name: str, kind: str) -> int: ...

    @abstractmethod
    def list_services(self, active_only: bool = False) -> list[ApiService]: ...

    @abstractmethod
    def get_service(self, service_id: int) -> ApiService | None: ...

    @abstractmethod
    def add_service(self, provider_id: int, name: str, unit_name: str, credit_per_unit: Decimal) -> int: ...

    @abstractmethod
    def set_service_price(self, service_id: int, credit_per_unit: Decimal) -> None: ...

    @abstractmethod
    def list_team_services(self, team_id: int) -> list[ApiService]: ...

    @abstractmethod
    def service_access_counts(self) -> dict[int, int]:
        """Servis kimliği -> o servise erişebilen ekip sayısı."""

    @abstractmethod
    def set_team_access(self, team_id: int, service_ids: list[int]) -> None: ...

    # --- bütçeler ------------------------------------------------------
    @abstractmethod
    def get_active_budget(self, team_id: int) -> TeamBudget | None: ...

    @abstractmethod
    def open_budget(self, team_id: int, credit_limit: Decimal, warn_percent: int) -> int: ...

    @abstractmethod
    def update_budget(self, team_budget_id: int, credit_limit: Decimal, warn_percent: int) -> None: ...

    @abstractmethod
    def budget_spent(self, team_budget_id: int) -> Decimal: ...

    @abstractmethod
    def budget_statuses(self) -> list[BudgetStatus]: ...

    @abstractmethod
    def reset_team_budget(self, team_id: int, reason: str) -> int: ...

    # --- kullanım ------------------------------------------------------
    @abstractmethod
    def add_usage(
        self,
        team_budget_id: int,
        user_id: int,
        service_id: int,
        units: int,
        credits: Decimal,
        status_code: int,
        latency_ms: int,
        outcome: Outcome,
    ) -> int: ...

    @abstractmethod
    def has_previous_rejection(self, team_budget_id: int) -> bool:
        """Dönemde son kaydedilenden başka reddedilmiş çağrı var mı."""

    @abstractmethod
    def recent_usage(
        self, limit: int = 200, team_id: int | None = None, outcome: Outcome | None = None
    ) -> list[UsageRecord]: ...

    @abstractmethod
    def service_shares(self) -> list[ServiceShare]:
        """Açık dönemlerdeki harcamanın servislere dağılımı (büyükten küçüğe)."""

    @abstractmethod
    def timeseries(self, minutes: int = 30) -> list[TimePoint]:
        """Son ``minutes`` dakikadaki dakikalık harcama; boş dakikalar dahil değil."""

    # --- bildirimler ---------------------------------------------------
    @abstractmethod
    def add_notification(self, team_id: int | None, severity: Severity, title: str, body: str) -> int: ...

    @abstractmethod
    def list_notifications(self, limit: int = 100, unread_only: bool = False) -> list[Notification]: ...

    @abstractmethod
    def last_notification_body(self, team_id: int, title: str, since: datetime) -> str | None: ...

    @abstractmethod
    def unread_count(self) -> int: ...

    @abstractmethod
    def mark_all_read(self) -> None: ...

    # --- simülasyon profilleri -----------------------------------------
    @abstractmethod
    def list_profiles(self) -> list[SimulationProfile]: ...

    @abstractmethod
    def upsert_profile(
        self, user_id: int, persona: str, calls_per_minute: int, error_rate: float, is_enabled: bool = True
    ) -> None: ...

    @abstractmethod
    def set_profile_enabled(self, user_id: int, enabled: bool) -> None: ...

    @abstractmethod
    def delete_profile(self, user_id: int) -> None: ...
