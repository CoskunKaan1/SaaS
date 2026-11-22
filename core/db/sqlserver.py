"""Microsoft SQL Server üzerinde çalışan depo uygulaması."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Iterator

from core.config import DatabaseSettings
from core.db.connection import ConnectionPool
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

_SERVICE_SELECT = """
SELECT s.ServiceId, s.ProviderId, s.Name, s.UnitName, s.CreditPerUnit, s.IsActive,
       p.Name, p.Kind
FROM dbo.ApiServices s
JOIN dbo.ApiProviders p ON p.ProviderId = s.ProviderId
"""


def _dt(value):
    """Eski 'SQL Server' ODBC sürücüsü DATETIME2 kolonlarını metin döndürür."""
    if value is None or isinstance(value, datetime):
        return value
    text = str(value).strip()
    head, _, frac = text.partition(".")
    parsed = datetime.strptime(head, "%Y-%m-%d %H:%M:%S")
    return parsed.replace(microsecond=int((frac + "000000")[:6])) if frac else parsed


def _service(row) -> ApiService:
    return ApiService(
        id=row[0], provider_id=row[1], name=row[2], unit_name=row[3],
        credit_per_unit=Decimal(row[4]), is_active=bool(row[5]),
        provider_name=row[6], provider_kind=row[7],
    )


class SqlServerRepository(Repository):
    def __init__(self, settings: DatabaseSettings):
        self.settings = settings
        self.pool = ConnectionPool(settings)

    # --- yardımcılar ---------------------------------------------------
    def _cur(self):
        return self.pool.get().cursor()

    def _scalar(self, sql: str, *params):
        cur = self._cur()
        cur.execute(sql, *params)
        row = cur.fetchone()
        return None if row is None else row[0]

    def _insert(self, sql: str, *params) -> int:
        """INSERT ... OUTPUT INSERTED.<id> sorgusunu çalıştırıp kimliği döndürür."""
        return int(self._scalar(sql, *params))

    def _exec(self, sql: str, *params) -> None:
        self._cur().execute(sql, *params)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        conn = self.pool.get()
        if not conn.autocommit:  # iç içe çağrı: dıştaki işlem yönetir
            yield
            return
        conn.autocommit = False
        try:
            yield
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.autocommit = True

    def is_empty(self) -> bool:
        return not self._scalar("SELECT COUNT(*) FROM dbo.Departments")

    def close(self) -> None:
        self.pool.close_all()

    # --- organizasyon --------------------------------------------------
    def list_departments(self) -> list[Department]:
        cur = self._cur()
        cur.execute("SELECT DepartmentId, Name, CostCenter FROM dbo.Departments ORDER BY Name")
        return [Department(*r) for r in cur.fetchall()]

    def add_department(self, name: str, cost_center: str) -> int:
        return self._insert(
            "INSERT INTO dbo.Departments (Name, CostCenter) OUTPUT INSERTED.DepartmentId VALUES (?, ?)",
            name, cost_center,
        )

    def list_teams(self) -> list[Team]:
        cur = self._cur()
        cur.execute(
            """SELECT t.TeamId, t.DepartmentId, t.Name, d.Name
               FROM dbo.Teams t JOIN dbo.Departments d ON d.DepartmentId = t.DepartmentId
               ORDER BY d.Name, t.Name"""
        )
        return [Team(*r) for r in cur.fetchall()]

    def add_team(self, department_id: int, name: str) -> int:
        return self._insert(
            "INSERT INTO dbo.Teams (DepartmentId, Name) OUTPUT INSERTED.TeamId VALUES (?, ?)",
            department_id, name,
        )

    # --- kullanıcılar --------------------------------------------------
    _USER_SELECT = """SELECT u.UserId, u.TeamId, u.FullName, u.Email, u.Role, u.IsSimulated, u.IsActive, t.Name
                      FROM dbo.Users u JOIN dbo.Teams t ON t.TeamId = u.TeamId"""

    @staticmethod
    def _user(r) -> User:
        return User(r[0], r[1], r[2], r[3], r[4], bool(r[5]), bool(r[6]), r[7])

    def list_users(self) -> list[User]:
        cur = self._cur()
        cur.execute(self._USER_SELECT + " ORDER BY u.UserId")
        return [self._user(r) for r in cur.fetchall()]

    def get_user(self, user_id: int) -> User | None:
        cur = self._cur()
        cur.execute(self._USER_SELECT + " WHERE u.UserId = ?", user_id)
        r = cur.fetchone()
        return self._user(r) if r else None

    def add_user(self, team_id, full_name, email, role="member", is_simulated=False) -> int:
        return self._insert(
            """INSERT INTO dbo.Users (TeamId, FullName, Email, Role, IsSimulated)
               OUTPUT INSERTED.UserId VALUES (?, ?, ?, ?, ?)""",
            team_id, full_name, email, role, int(is_simulated),
        )

    def set_user_active(self, user_id: int, active: bool) -> None:
        self._exec("UPDATE dbo.Users SET IsActive = ? WHERE UserId = ?", int(active), user_id)

    # --- servis kataloğu -----------------------------------------------
    def list_providers(self) -> list[Provider]:
        cur = self._cur()
        cur.execute("SELECT ProviderId, Name, Kind FROM dbo.ApiProviders ORDER BY Name")
        return [Provider(*r) for r in cur.fetchall()]

    def add_provider(self, name: str, kind: str) -> int:
        return self._insert(
            "INSERT INTO dbo.ApiProviders (Name, Kind) OUTPUT INSERTED.ProviderId VALUES (?, ?)", name, kind
        )

    def list_services(self, active_only: bool = False) -> list[ApiService]:
        cur = self._cur()
        where = " WHERE s.IsActive = 1" if active_only else ""
        cur.execute(_SERVICE_SELECT + where + " ORDER BY p.Name, s.Name")
        return [_service(r) for r in cur.fetchall()]

    def get_service(self, service_id: int) -> ApiService | None:
        cur = self._cur()
        cur.execute(_SERVICE_SELECT + " WHERE s.ServiceId = ?", service_id)
        r = cur.fetchone()
        return _service(r) if r else None

    def add_service(self, provider_id, name, unit_name, credit_per_unit) -> int:
        return self._insert(
            """INSERT INTO dbo.ApiServices (ProviderId, Name, UnitName, CreditPerUnit)
               OUTPUT INSERTED.ServiceId VALUES (?, ?, ?, ?)""",
            provider_id, name, unit_name, Decimal(credit_per_unit),
        )

    def set_service_price(self, service_id: int, credit_per_unit: Decimal) -> None:
        self._exec("UPDATE dbo.ApiServices SET CreditPerUnit = ? WHERE ServiceId = ?",
                   Decimal(credit_per_unit), service_id)

    def list_team_services(self, team_id: int) -> list[ApiService]:
        cur = self._cur()
        cur.execute(
            _SERVICE_SELECT
            + " JOIN dbo.TeamServiceAccess a ON a.ServiceId = s.ServiceId"
            + " WHERE a.TeamId = ? AND s.IsActive = 1 ORDER BY s.Name",
            team_id,
        )
        return [_service(r) for r in cur.fetchall()]

    def service_access_counts(self) -> dict[int, int]:
        cur = self._cur()
        cur.execute("SELECT ServiceId, COUNT(*) FROM dbo.TeamServiceAccess GROUP BY ServiceId")
        return {r[0]: int(r[1]) for r in cur.fetchall()}

    def set_team_access(self, team_id: int, service_ids: list[int]) -> None:
        with self.transaction():
            cur = self._cur()
            cur.execute("SELECT ServiceId FROM dbo.TeamServiceAccess WHERE TeamId = ?", team_id)
            current = {r[0] for r in cur.fetchall()}
            wanted = set(service_ids)
            # Yalnızca fark yazılır; değişmeyen iznin GrantedAt değeri korunur.
            for sid in current - wanted:
                cur.execute("DELETE FROM dbo.TeamServiceAccess WHERE TeamId = ? AND ServiceId = ?", team_id, sid)
            for sid in sorted(wanted - current):
                cur.execute("INSERT INTO dbo.TeamServiceAccess (TeamId, ServiceId) VALUES (?, ?)", team_id, sid)

    # --- bütçeler ------------------------------------------------------
    def get_active_budget(self, team_id: int) -> TeamBudget | None:
        cur = self._cur()
        cur.execute(
            """SELECT TeamBudgetId, TeamId, CreditLimit, WarnPercent, StartedAt, ClosedAt, CloseReason
               FROM dbo.TeamBudgets WHERE TeamId = ? AND ClosedAt IS NULL""",
            team_id,
        )
        r = cur.fetchone()
        return TeamBudget(r[0], r[1], Decimal(r[2]), int(r[3]), _dt(r[4]), _dt(r[5]), r[6]) if r else None

    def open_budget(self, team_id: int, credit_limit: Decimal, warn_percent: int) -> int:
        return self._insert(
            """INSERT INTO dbo.TeamBudgets (TeamId, CreditLimit, WarnPercent)
               OUTPUT INSERTED.TeamBudgetId VALUES (?, ?, ?)""",
            team_id, Decimal(credit_limit), warn_percent,
        )

    def update_budget(self, team_budget_id: int, credit_limit: Decimal, warn_percent: int) -> None:
        self._exec(
            "UPDATE dbo.TeamBudgets SET CreditLimit = ?, WarnPercent = ? WHERE TeamBudgetId = ?",
            Decimal(credit_limit), warn_percent, team_budget_id,
        )

    def budget_spent(self, team_budget_id: int) -> Decimal:
        value = self._scalar(
            "SELECT ISNULL(SUM(CreditsCharged), 0) FROM dbo.UsageRecords WHERE TeamBudgetId = ?",
            team_budget_id,
        )
        return Decimal(value)

    def budget_statuses(self) -> list[BudgetStatus]:
        cur = self._cur()
        cur.execute(
            """SELECT TeamBudgetId, TeamId, TeamName, DepartmentName, CreditLimit, WarnPercent,
                      StartedAt, Spent, Calls, Rejected
               FROM dbo.vw_TeamBudgetStatus ORDER BY DepartmentName, TeamName"""
        )
        return [
            BudgetStatus(r[0], r[1], r[2], r[3], Decimal(r[4]), int(r[5]), _dt(r[6]), Decimal(r[7]), int(r[8]), int(r[9]))
            for r in cur.fetchall()
        ]

    def reset_team_budget(self, team_id: int, reason: str) -> int:
        cur = self._cur()
        cur.execute("EXEC dbo.sp_ResetTeamBudget @TeamId = ?, @Reason = ?", team_id, reason)
        new_id = int(cur.fetchone()[0])
        while cur.nextset():  # yordamın kalan sonuç kümelerini tüket
            pass
        return new_id

    # --- kullanım ------------------------------------------------------
    def add_usage(self, team_budget_id, user_id, service_id, units, credits, status_code, latency_ms, outcome) -> int:
        return self._insert(
            """INSERT INTO dbo.UsageRecords
                 (TeamBudgetId, UserId, ServiceId, Units, CreditsCharged, StatusCode, LatencyMs, Outcome)
               OUTPUT INSERTED.UsageId VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            team_budget_id, user_id, service_id, units, Decimal(credits), status_code, latency_ms,
            Outcome(outcome).value,
        )

    def has_previous_rejection(self, team_budget_id: int) -> bool:
        cur = self._cur()
        cur.execute("SELECT TOP (2) 1 FROM dbo.UsageRecords WHERE TeamBudgetId = ? AND Outcome = 'rejected'",
                    team_budget_id)
        return len(cur.fetchall()) > 1

    def recent_usage(self, limit=200, team_id=None, outcome=None) -> list[UsageRecord]:
        where, params = [], []
        if team_id is not None:
            where.append("b.TeamId = ?")
            params.append(team_id)
        if outcome is not None:
            where.append("r.Outcome = ?")
            params.append(Outcome(outcome).value)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        cur = self._cur()
        cur.execute(
            f"""SELECT TOP (?) r.UsageId, r.TeamBudgetId, r.UserId, r.ServiceId, r.Units, r.CreditsCharged,
                       r.StatusCode, r.LatencyMs, r.Outcome, r.CreatedAt, u.FullName, t.Name, s.Name
                FROM dbo.UsageRecords r
                JOIN dbo.Users u       ON u.UserId = r.UserId
                JOIN dbo.TeamBudgets b ON b.TeamBudgetId = r.TeamBudgetId
                JOIN dbo.Teams t       ON t.TeamId = b.TeamId
                JOIN dbo.ApiServices s ON s.ServiceId = r.ServiceId
                {clause}
                ORDER BY r.UsageId DESC""",
            int(limit), *params,
        )
        return [
            UsageRecord(r[0], r[1], r[2], r[3], int(r[4]), Decimal(r[5]), int(r[6]), int(r[7]), Outcome(r[8]),
                        _dt(r[9]), r[10], r[11], r[12])
            for r in cur.fetchall()
        ]

    def service_shares(self) -> list[ServiceShare]:
        # Tablo yalnızca sona eklenerek büyür: açık dönemlerin ilk kaydından
        # öncesini okumaya gerek yok.
        first = self._scalar(
            """SELECT MIN(f.UsageId) FROM dbo.TeamBudgets b
               CROSS APPLY (SELECT TOP (1) r.UsageId FROM dbo.UsageRecords r
                            WHERE r.TeamBudgetId = b.TeamBudgetId ORDER BY r.UsageId) f
               WHERE b.ClosedAt IS NULL"""
        )
        if first is None:
            return []
        cur = self._cur()
        cur.execute(
            """SELECT g.ServiceId, s.Name, g.Credits, g.Calls
               FROM (SELECT r.ServiceId, SUM(r.CreditsCharged) AS Credits, COUNT(*) AS Calls
                     FROM dbo.UsageRecords r
                     JOIN dbo.TeamBudgets b ON b.TeamBudgetId = r.TeamBudgetId AND b.ClosedAt IS NULL
                     WHERE r.UsageId >= ? AND r.Outcome = 'ok'
                     GROUP BY r.ServiceId) g
               JOIN dbo.ApiServices s ON s.ServiceId = g.ServiceId
               ORDER BY g.Credits DESC""",
            first,
        )
        return [ServiceShare(r[0], r[1], Decimal(r[2]), int(r[3])) for r in cur.fetchall()]

    def timeseries(self, minutes: int = 30) -> list[TimePoint]:
        cur = self._cur()
        cur.execute(
            """SELECT DATEADD(minute, DATEDIFF(minute, 0, CreatedAt), 0) AS Bucket,
                      SUM(CreditsCharged), COUNT(*)
               FROM dbo.UsageRecords
               WHERE CreatedAt >= DATEADD(minute, ?, SYSDATETIME()) AND Outcome = 'ok'
               GROUP BY DATEADD(minute, DATEDIFF(minute, 0, CreatedAt), 0)
               ORDER BY Bucket""",
            -int(minutes),
        )
        return [TimePoint(_dt(r[0]), Decimal(r[1]), int(r[2])) for r in cur.fetchall()]

    # --- bildirimler ---------------------------------------------------
    def add_notification(self, team_id, severity, title, body) -> int:
        return self._insert(
            """INSERT INTO dbo.Notifications (TeamId, Severity, Title, Body)
               OUTPUT INSERTED.NotificationId VALUES (?, ?, ?, ?)""",
            team_id, Severity(severity).value, title[:150], body[:500],
        )

    def list_notifications(self, limit=100, unread_only=False) -> list[Notification]:
        cur = self._cur()
        where = "WHERE n.IsRead = 0" if unread_only else ""
        cur.execute(
            f"""SELECT TOP (?) n.NotificationId, n.TeamId, n.Severity, n.Title, n.Body, n.CreatedAt, n.IsRead,
                       ISNULL(t.Name, N'')
                FROM dbo.Notifications n LEFT JOIN dbo.Teams t ON t.TeamId = n.TeamId
                {where} ORDER BY n.NotificationId DESC""",
            int(limit),
        )
        return [
            Notification(r[0], r[1], Severity(r[2]), r[3], r[4], _dt(r[5]), bool(r[6]), r[7]) for r in cur.fetchall()
        ]

    def last_notification_body(self, team_id: int, title: str, since: datetime) -> str | None:
        return self._scalar(
            """SELECT TOP (1) Body FROM dbo.Notifications
               WHERE TeamId = ? AND Title = ? AND CreatedAt >= ?
               ORDER BY NotificationId DESC""",
            team_id, title[:150], since,
        )

    def unread_count(self) -> int:
        return int(self._scalar("SELECT COUNT(*) FROM dbo.Notifications WHERE IsRead = 0"))

    def mark_all_read(self) -> None:
        self._exec("UPDATE dbo.Notifications SET IsRead = 1 WHERE IsRead = 0")

    # --- simülasyon profilleri -----------------------------------------
    def list_profiles(self) -> list[SimulationProfile]:
        cur = self._cur()
        cur.execute(
            """SELECT p.UserId, p.Persona, p.CallsPerMinute, p.ErrorRate, p.IsEnabled, u.FullName, u.TeamId, t.Name
               FROM dbo.SimulationProfiles p
               JOIN dbo.Users u ON u.UserId = p.UserId
               JOIN dbo.Teams t ON t.TeamId = u.TeamId
               ORDER BY p.UserId"""
        )
        return [
            SimulationProfile(r[0], r[1], int(r[2]), float(r[3]), bool(r[4]), r[5], r[6], r[7])
            for r in cur.fetchall()
        ]

    def upsert_profile(self, user_id, persona, calls_per_minute, error_rate, is_enabled=True) -> None:
        self._exec(
            """MERGE dbo.SimulationProfiles AS target
               USING (SELECT ? AS UserId) AS src ON target.UserId = src.UserId
               WHEN MATCHED THEN UPDATE SET Persona = ?, CallsPerMinute = ?, ErrorRate = ?, IsEnabled = ?
               WHEN NOT MATCHED THEN INSERT (UserId, Persona, CallsPerMinute, ErrorRate, IsEnabled)
                    VALUES (?, ?, ?, ?, ?);""",
            user_id,
            persona, calls_per_minute, Decimal(str(error_rate)), int(is_enabled),
            user_id, persona, calls_per_minute, Decimal(str(error_rate)), int(is_enabled),
        )

    def set_profile_enabled(self, user_id: int, enabled: bool) -> None:
        self._exec("UPDATE dbo.SimulationProfiles SET IsEnabled = ? WHERE UserId = ?", int(enabled), user_id)

    def delete_profile(self, user_id: int) -> None:
        self._exec("DELETE FROM dbo.SimulationProfiles WHERE UserId = ?", user_id)
