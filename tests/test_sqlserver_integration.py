"""Gerçek SQL Server üzerinde uçtan uca testler.

Sunucuya ulaşılamazsa bu dosyadaki testler atlanır (skip). Testler ayrı bir
``ApiKrediTakip_Test`` veritabanı oluşturur ve sonunda siler; uygulamanın
asıl veritabanına dokunmaz. Farklı bir sunucu için:

    set KREDI_DB_SERVER=.\\SQLEXPRESS
    python -m pytest tests/test_sqlserver_integration.py -v
"""

from __future__ import annotations

import random
from dataclasses import replace
from decimal import Decimal

import pyodbc
import pytest

from core.config import load_settings
from core.connectors.testusers import SimulationEngine, create_test_user
from core.db.connection import DatabaseUnavailable, connect
from core.db.migrate import migrate
from core.db.sqlserver import SqlServerRepository
from core.models import Outcome, Severity
from core.services.credit_service import CreditService
from core.services.seed import seed_demo_data

TEST_DB = "ApiKrediTakip_Test"


def _settings():
    return replace(load_settings().database, database=TEST_DB, timeout=3)


def _drop(settings) -> None:
    conn = connect(settings, database="master")
    conn.cursor().execute(
        f"IF DB_ID(N'{TEST_DB}') IS NOT NULL BEGIN "
        f"ALTER DATABASE [{TEST_DB}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{TEST_DB}]; END"
    )
    conn.close()


@pytest.fixture(scope="module")
def sql_repo():
    settings = _settings()
    try:
        _drop(settings)
        migrate(settings)
    except (DatabaseUnavailable, pyodbc.Error) as exc:
        pytest.skip(f"SQL Server'a ulaşılamadı: {str(exc)[:120]}")
    repo = SqlServerRepository(settings)
    seed_demo_data(repo)
    yield repo
    repo.close()
    _drop(settings)


def test_schema_is_idempotent(sql_repo):
    migrate(sql_repo.settings)  # ikinci kez çalıştırmak hata vermemeli
    assert not sql_repo.is_empty()


def test_seed_loaded(sql_repo):
    assert len(sql_repo.list_teams()) == 5
    assert len(sql_repo.budget_statuses()) == 5
    assert all(sql_repo.list_team_services(t.id) for t in sql_repo.list_teams())
    assert len(sql_repo.list_profiles()) >= 5


def test_charge_and_view(sql_repo):
    credit = CreditService(sql_repo)
    profile = sql_repo.list_profiles()[0]
    service = sql_repo.list_team_services(profile.team_id)[0]
    before = next(s for s in sql_repo.budget_statuses() if s.team_id == profile.team_id)
    result = credit.charge(profile.user_id, service.id, 3)
    after = next(s for s in sql_repo.budget_statuses() if s.team_id == profile.team_id)
    assert result.outcome is Outcome.OK
    assert after.spent - before.spent == result.credits
    assert after.calls == before.calls + 1
    assert sql_repo.recent_usage(1)[0].id == result.usage_id


def test_limit_rejection_and_notifications(sql_repo):
    credit = CreditService(sql_repo)
    dept = sql_repo.list_departments()[0]
    team = sql_repo.add_team(dept.id, "Limit Testi")
    sql_repo.open_budget(team, Decimal(10), 50)
    svc = sql_repo.list_services()[0]
    sql_repo.set_team_access(team, [svc.id])
    user = sql_repo.add_user(team, "Limit Kullanıcı", "limit@test.local")
    unit_cost = svc.credit_per_unit
    units = int(Decimal(6) / unit_cost) or 1
    credit.charge(user, svc.id, units)  # %50 eşiğini geçer
    while credit.charge(user, svc.id, units).outcome is Outcome.OK:
        pass
    status = next(s for s in sql_repo.budget_statuses() if s.team_id == team)
    assert status.spent <= Decimal(10)
    assert status.rejected >= 1
    notes = [n for n in sql_repo.list_notifications(20) if n.team_id == team]
    assert Severity.WARNING in [n.severity for n in notes]
    if status.spent == Decimal(10):
        assert Severity.CRITICAL in [n.severity for n in notes]
    else:
        assert any("yetmedi" in n.title for n in notes)


def test_reset_procedure_keeps_history(sql_repo):
    credit = CreditService(sql_repo)
    team = sql_repo.list_teams()[0]
    old = sql_repo.get_active_budget(team.id)
    spent_before = sql_repo.budget_spent(old.id)
    new_id = credit.reset_team(team.id, "Entegrasyon testi")
    assert new_id != old.id
    assert sql_repo.get_active_budget(team.id).id == new_id
    assert sql_repo.budget_spent(new_id) == 0
    assert sql_repo.budget_spent(old.id) == spent_before


def test_one_active_budget_constraint(sql_repo):
    team = sql_repo.list_teams()[0]
    with pytest.raises(pyodbc.IntegrityError):
        sql_repo.open_budget(team.id, Decimal(100), 80)


def test_shortfall_once_and_full_only_at_limit(sql_repo):
    credit = CreditService(sql_repo)
    team = sql_repo.add_team(sql_repo.list_departments()[0].id, "Yetmedi Testi")
    sql_repo.open_budget(team, Decimal(10), 50)
    svc = sql_repo.add_service(sql_repo.list_providers()[0].id, "Tek Kredi", "istek", Decimal(1))
    sql_repo.set_team_access(team, [svc])
    user = sql_repo.add_user(team, "Yetmedi", "yetmedi@test.local")
    titles = lambda: [n.title for n in sql_repo.list_notifications(50) if n.team_id == team]
    credit.charge(user, svc, 11)
    CreditService(sql_repo).charge(user, svc, 11)  # yeniden başlatma
    assert sum("yetmedi" in x for x in titles()) == 1 and not any("doldu" in x for x in titles())
    credit.charge(user, svc, 10)
    assert sum("doldu" in x for x in titles()) == 1


def test_access_update_keeps_grant_time(sql_repo):
    team = sql_repo.list_teams()[0]
    ids = [s.id for s in sql_repo.list_team_services(team.id)]
    sql_repo._exec("UPDATE dbo.TeamServiceAccess SET GrantedAt = '2020-01-01' WHERE TeamId = ?", team.id)
    sql_repo.set_team_access(team.id, ids[1:])
    sql_repo.set_team_access(team.id, ids)
    old = sql_repo._scalar(
        "SELECT COUNT(*) FROM dbo.TeamServiceAccess WHERE TeamId = ? AND GrantedAt = '2020-01-01'", team.id)
    assert old == len(ids) - 1


def test_check_constraints(sql_repo):
    prov = sql_repo.list_providers()[0]
    with pytest.raises(pyodbc.IntegrityError):
        sql_repo.add_service(prov.id, "Bedava", "istek", Decimal(0))


def test_test_user_and_engine(sql_repo):
    credit = CreditService(sql_repo)
    team = sql_repo.list_teams()[1]
    uid = create_test_user(sql_repo, team.id, "Entegrasyon Bot", "steady", 600, 0.0)
    for p in sql_repo.list_profiles():
        if p.user_id != uid:
            sql_repo.set_profile_enabled(p.user_id, False)
    engine = SimulationEngine(credit, tick_seconds=1.0, rng=random.Random(1))
    results = []
    for _ in range(3):
        results += engine.step()
    assert results
    assert all(r.team_id == team.id for r in results)


def test_timeseries_and_shares(sql_repo):
    assert sql_repo.timeseries(30)
    shares = sql_repo.service_shares()
    assert shares == sorted(shares, key=lambda s: s.credits, reverse=True)


def test_mark_all_read(sql_repo):
    sql_repo.add_notification(None, Severity.INFO, "x", "y")
    assert sql_repo.unread_count() > 0
    sql_repo.mark_all_read()
    assert sql_repo.unread_count() == 0
