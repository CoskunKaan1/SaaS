"""``Repository`` sözleşmesinin bellek içi uygulaması.

SQL Server gerektirmeden iş kurallarını ve arayüzü test etmek için kullanılır.
Kısıtlar (benzersizlik, tek açık dönem, CHECK) SQL şemasıyla aynı davranacak
şekilde burada da denetlenir.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal

from core.db.repository import Repository
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


class IntegrityError(Exception):
    pass


class InMemoryRepository(Repository):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.departments: dict[int, Department] = {}
        self.teams: dict[int, Team] = {}
        self.users: dict[int, User] = {}
        self.providers: dict[int, Provider] = {}
        self.services: dict[int, ApiService] = {}
        self.access: dict[int, set[int]] = defaultdict(set)
        self.budgets: dict[int, TeamBudget] = {}
        self.usage: list[UsageRecord] = []
        self.notifications: list[Notification] = []
        self.profiles: dict[int, SimulationProfile] = {}
        self._ids: dict[str, int] = defaultdict(int)
        self.now = datetime.now  # testlerde zaman kaydırmak için değiştirilebilir

    def _next(self, key: str) -> int:
        self._ids[key] += 1
        return self._ids[key]

    @contextmanager
    def transaction(self):
        with self._lock:
            yield

    def is_empty(self) -> bool:
        return not self.departments

    # --- organizasyon --------------------------------------------------
    def list_departments(self):
        return sorted(self.departments.values(), key=lambda d: d.name)

    def add_department(self, name, cost_center):
        if any(d.name == name for d in self.departments.values()):
            raise IntegrityError("UQ_Departments_Name")
        i = self._next("dept")
        self.departments[i] = Department(i, name, cost_center)
        return i

    def list_teams(self):
        return sorted(
            (Team(t.id, t.department_id, t.name, self.departments[t.department_id].name) for t in self.teams.values()),
            key=lambda t: (t.department_name, t.name),
        )

    def add_team(self, department_id, name):
        if department_id not in self.departments:
            raise IntegrityError("FK_Teams_Departments")
        if any(t.department_id == department_id and t.name == name for t in self.teams.values()):
            raise IntegrityError("UQ_Teams_Department_Name")
        i = self._next("team")
        self.teams[i] = Team(i, department_id, name)
        return i

    # --- kullanıcılar --------------------------------------------------
    def _user(self, u: User) -> User:
        return User(u.id, u.team_id, u.full_name, u.email, u.role, u.is_simulated, u.is_active,
                    self.teams[u.team_id].name)

    def list_users(self):
        return [self._user(u) for u in sorted(self.users.values(), key=lambda u: u.id)]

    def get_user(self, user_id):
        u = self.users.get(user_id)
        return self._user(u) if u else None

    def add_user(self, team_id, full_name, email, role="member", is_simulated=False):
        if team_id not in self.teams:
            raise IntegrityError("FK_Users_Teams")
        if any(u.email == email for u in self.users.values()):
            raise IntegrityError("UQ_Users_Email")
        i = self._next("user")
        self.users[i] = User(i, team_id, full_name, email, role, is_simulated, True)
        return i

    def set_user_active(self, user_id, active):
        u = self.users[user_id]
        self.users[user_id] = User(u.id, u.team_id, u.full_name, u.email, u.role, u.is_simulated, active)

    # --- katalog -------------------------------------------------------
    def list_providers(self):
        return sorted(self.providers.values(), key=lambda p: p.name)

    def add_provider(self, name, kind):
        i = self._next("prov")
        self.providers[i] = Provider(i, name, kind)
        return i

    def _svc(self, s: ApiService) -> ApiService:
        p = self.providers[s.provider_id]
        return ApiService(s.id, s.provider_id, s.name, s.unit_name, s.credit_per_unit, s.is_active, p.name, p.kind)

    def list_services(self, active_only=False):
        out = [self._svc(s) for s in self.services.values() if s.is_active or not active_only]
        return sorted(out, key=lambda s: (s.provider_name, s.name))

    def get_service(self, service_id):
        s = self.services.get(service_id)
        return self._svc(s) if s else None

    def add_service(self, provider_id, name, unit_name, credit_per_unit):
        if Decimal(credit_per_unit) <= 0:
            raise IntegrityError("CK_ApiServices_Price")
        i = self._next("svc")
        self.services[i] = ApiService(i, provider_id, name, unit_name, Decimal(credit_per_unit))
        return i

    def set_service_price(self, service_id, credit_per_unit):
        s = self.services[service_id]
        self.services[service_id] = ApiService(s.id, s.provider_id, s.name, s.unit_name, Decimal(credit_per_unit),
                                               s.is_active)

    def list_team_services(self, team_id):
        return sorted((self._svc(self.services[sid]) for sid in self.access.get(team_id, ())
                       if self.services[sid].is_active), key=lambda s: s.name)

    def service_access_counts(self):
        counts: dict[int, int] = defaultdict(int)
        for sids in self.access.values():
            for sid in sids:
                counts[sid] += 1
        return dict(counts)

    def set_team_access(self, team_id, service_ids):
        self.access[team_id] = set(service_ids)

    # --- bütçeler ------------------------------------------------------
    def get_active_budget(self, team_id):
        return next((b for b in self.budgets.values() if b.team_id == team_id and b.closed_at is None), None)

    def open_budget(self, team_id, credit_limit, warn_percent):
        if self.get_active_budget(team_id):
            raise IntegrityError("UX_TeamBudgets_OneActive")
        i = self._next("budget")
        self.budgets[i] = TeamBudget(i, team_id, Decimal(credit_limit), warn_percent, self.now())
        return i

    def update_budget(self, team_budget_id, credit_limit, warn_percent):
        b = self.budgets[team_budget_id]
        self.budgets[team_budget_id] = TeamBudget(b.id, b.team_id, Decimal(credit_limit), warn_percent,
                                                  b.started_at, b.closed_at, b.close_reason)

    def budget_spent(self, team_budget_id):
        return sum((u.credits for u in self.usage if u.team_budget_id == team_budget_id), Decimal(0))

    def budget_statuses(self):
        out = []
        for b in self.budgets.values():
            if b.closed_at is not None:
                continue
            t = self.teams[b.team_id]
            rows = [u for u in self.usage if u.team_budget_id == b.id]
            out.append(BudgetStatus(
                b.id, t.id, t.name, self.departments[t.department_id].name, b.credit_limit, b.warn_percent,
                b.started_at, sum((u.credits for u in rows), Decimal(0)),
                sum(1 for u in rows if u.outcome is not Outcome.REJECTED),
                sum(1 for u in rows if u.outcome is Outcome.REJECTED),
            ))
        return sorted(out, key=lambda s: (s.department_name, s.team_name))

    def reset_team_budget(self, team_id, reason):
        with self._lock:
            b = self.get_active_budget(team_id)
            if b is None:
                raise IntegrityError("Ekibin açık bütçe dönemi yok.")
            self.budgets[b.id] = TeamBudget(b.id, b.team_id, b.credit_limit, b.warn_percent, b.started_at,
                                            self.now(), reason)
            return self.open_budget(team_id, b.credit_limit, b.warn_percent)

    # --- kullanım ------------------------------------------------------
    def add_usage(self, team_budget_id, user_id, service_id, units, credits, status_code, latency_ms, outcome):
        if units <= 0:
            raise IntegrityError("CK_Usage_Units")
        i = self._next("usage")
        self.usage.append(UsageRecord(i, team_budget_id, user_id, service_id, units, Decimal(credits), status_code,
                                      latency_ms, Outcome(outcome), self.now()))
        return i

    def has_previous_rejection(self, team_budget_id):
        return sum(u.team_budget_id == team_budget_id and u.outcome is Outcome.REJECTED for u in self.usage) > 1

    def recent_usage(self, limit=200, team_id=None, outcome=None):
        out = []
        for u in reversed(self.usage):
            team = self.budgets[u.team_budget_id].team_id
            if team_id is not None and team != team_id:
                continue
            if outcome is not None and u.outcome is not Outcome(outcome):
                continue
            out.append(UsageRecord(u.id, u.team_budget_id, u.user_id, u.service_id, u.units, u.credits,
                                   u.status_code, u.latency_ms, u.outcome, u.created_at,
                                   self.users[u.user_id].full_name, self.teams[team].name,
                                   self.services[u.service_id].name))
            if len(out) >= limit:
                break
        return out

    def service_shares(self):
        agg: dict[int, list] = {}
        for u in self.usage:
            if u.outcome is not Outcome.OK or self.budgets[u.team_budget_id].closed_at is not None:
                continue
            row = agg.setdefault(u.service_id, [Decimal(0), 0])
            row[0] += u.credits
            row[1] += 1
        out = [ServiceShare(sid, self.services[sid].name, c, n) for sid, (c, n) in agg.items()]
        return sorted(out, key=lambda s: s.credits, reverse=True)

    def timeseries(self, minutes=30):
        since = self.now() - timedelta(minutes=minutes)
        agg: dict[datetime, list] = {}
        for u in self.usage:
            if u.outcome is not Outcome.OK or u.created_at < since:
                continue
            bucket = u.created_at.replace(second=0, microsecond=0)
            row = agg.setdefault(bucket, [Decimal(0), 0])
            row[0] += u.credits
            row[1] += 1
        return [TimePoint(b, c, n) for b, (c, n) in sorted(agg.items())]

    # --- bildirimler ---------------------------------------------------
    def add_notification(self, team_id, severity, title, body):
        i = self._next("note")
        self.notifications.append(Notification(i, team_id, Severity(severity), title, body, self.now()))
        return i

    def list_notifications(self, limit=100, unread_only=False):
        out = []
        for n in reversed(self.notifications):
            if unread_only and n.is_read:
                continue
            team = self.teams[n.team_id].name if n.team_id else ""
            out.append(Notification(n.id, n.team_id, n.severity, n.title, n.body, n.created_at, n.is_read, team))
            if len(out) >= limit:
                break
        return out

    def last_notification_body(self, team_id, title, since):
        return next((n.body for n in reversed(self.notifications)
                     if n.team_id == team_id and n.title == title and n.created_at >= since), None)

    def unread_count(self):
        return sum(1 for n in self.notifications if not n.is_read)

    def mark_all_read(self):
        self.notifications = [
            Notification(n.id, n.team_id, n.severity, n.title, n.body, n.created_at, True) for n in self.notifications
        ]

    # --- profiller -----------------------------------------------------
    def list_profiles(self):
        out = []
        for p in sorted(self.profiles.values(), key=lambda p: p.user_id):
            u = self.users[p.user_id]
            out.append(SimulationProfile(p.user_id, p.persona, p.calls_per_minute, p.error_rate, p.is_enabled,
                                         u.full_name, u.team_id, self.teams[u.team_id].name))
        return out

    def upsert_profile(self, user_id, persona, calls_per_minute, error_rate, is_enabled=True):
        if user_id not in self.users:
            raise IntegrityError("FK_SimProfiles_Users")
        self.profiles[user_id] = SimulationProfile(user_id, persona, calls_per_minute, error_rate, is_enabled)

    def set_profile_enabled(self, user_id, enabled):
        p = self.profiles[user_id]
        self.profiles[user_id] = SimulationProfile(p.user_id, p.persona, p.calls_per_minute, p.error_rate, enabled)

    def delete_profile(self, user_id):
        self.profiles.pop(user_id, None)
