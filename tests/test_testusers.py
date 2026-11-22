import random
from decimal import Decimal

import pytest

from core.connectors.simulated_api import SimulatedApiConnector
from core.connectors.testusers import PERSONAS, SimulationEngine, TestUserError, attach_user, create_test_user
from core.connectors.testusers.personas import PersonaState, plan_tick, poisson
from core.models import ApiService, Outcome
from core.services.credit_service import CreditError


def test_create_test_user_returns_id_and_profile(seeded_repo):
    team = seeded_repo.list_teams()[0]
    uid = create_test_user(seeded_repo, team.id, "Yük Testi Ç", "bursty", 30, 0.1)
    user = seeded_repo.get_user(uid)
    assert user.is_simulated and user.email == "yuk.testi.c@test.local"
    profile = next(p for p in seeded_repo.list_profiles() if p.user_id == uid)
    assert profile.persona == "bursty" and profile.calls_per_minute == 30


def test_create_test_user_generates_unique_emails(seeded_repo):
    team = seeded_repo.list_teams()[0]
    a = create_test_user(seeded_repo, team.id, "Bot")
    b = create_test_user(seeded_repo, team.id, "Bot")
    assert seeded_repo.get_user(a).email != seeded_repo.get_user(b).email


@pytest.mark.parametrize(
    "kwargs",
    [{"full_name": " "}, {"persona": "nope"}, {"calls_per_minute": 0}, {"calls_per_minute": 601},
     {"error_rate": 1.5}],
)
def test_create_test_user_validation(seeded_repo, kwargs):
    team = seeded_repo.list_teams()[0]
    args = {"full_name": "x", "persona": "steady", "calls_per_minute": 5, "error_rate": 0.0} | kwargs
    with pytest.raises(TestUserError):
        create_test_user(seeded_repo, team.id, **args)


def test_attach_existing_user_by_id(seeded_repo):
    human = next(u for u in seeded_repo.list_users() if not u.is_simulated)
    attach_user(seeded_repo, human.id, "wave", 20, 0.0)
    assert any(p.user_id == human.id for p in seeded_repo.list_profiles())


def test_attach_unknown_or_inactive_user(seeded_repo):
    with pytest.raises(TestUserError):
        attach_user(seeded_repo, 9999)
    human = next(u for u in seeded_repo.list_users() if not u.is_simulated)
    seeded_repo.set_user_active(human.id, False)
    with pytest.raises(TestUserError):
        attach_user(seeded_repo, human.id)


def test_poisson_mean_is_close_to_lambda(rng):
    samples = [poisson(2.5, rng) for _ in range(20000)]
    assert abs(sum(samples) / len(samples) - 2.5) < 0.1
    assert poisson(0, rng) == 0
    assert poisson(100, rng) > 50


@pytest.mark.parametrize("persona", list(PERSONAS))
def test_every_persona_produces_traffic(persona, rng):
    state = PersonaState(phase=0.0)
    total = sum(plan_tick(persona, 60, 1.0, t, state, rng)[0] for t in range(600))
    assert 200 < total < 1500  # ortalama ~600 çağrı civarında


def test_heavy_persona_has_larger_calls(rng):
    assert plan_tick("heavy", 60, 1.0, 0, PersonaState(), rng)[1] > 1.0


def test_connector_units_and_errors():
    conn = SimulatedApiConnector(random.Random(1))
    token = ApiService(1, 1, "LLM", "1K token", Decimal("0.8"), provider_kind="external")
    single = ApiService(2, 1, "Auth", "istek", Decimal("0.01"), provider_kind="internal")
    for _ in range(200):
        r = conn.call(token)
        assert 1 <= r.units <= 12 and r.latency_ms >= 40 and r.ok
        assert conn.call(single).units == 1
    errors = sum(not conn.call(single, error_rate=0.5).ok for _ in range(1000))
    assert 400 < errors < 600
    assert conn.call(token, size_factor=3.0).units >= 3


def test_engine_step_writes_usage(credit, seeded_repo):
    engine = SimulationEngine(credit, tick_seconds=5.0, rng=random.Random(7))
    produced = []
    for _ in range(10):
        produced += engine.step()
    assert produced, "simülasyon hiç çağrı üretmedi"
    assert len(seeded_repo.usage) == engine.stats.calls
    assert engine.stats.ok + engine.stats.errors + engine.stats.rejected == engine.stats.calls


def test_engine_skips_disabled_profiles(credit, seeded_repo):
    for p in seeded_repo.list_profiles():
        seeded_repo.set_profile_enabled(p.user_id, False)
    engine = SimulationEngine(credit, tick_seconds=5.0, rng=random.Random(7))
    for _ in range(5):
        engine.step()
    assert seeded_repo.usage == []


def test_engine_auto_reset(credit, seeded_repo, monkeypatch):
    engine = SimulationEngine(credit, tick_seconds=1.0, auto_reset_seconds=60, rng=random.Random(3))
    before = {s.team_budget_id for s in seeded_repo.budget_statuses()}
    engine._last_reset -= 61  # süre dolmuş gibi davran
    engine.step()
    after = {s.team_budget_id for s in seeded_repo.budget_statuses()}
    assert engine.stats.resets == 1
    assert before.isdisjoint(after)
    assert 0 < engine.seconds_to_reset() <= 60


def test_engine_fire_once_and_missing_profile(credit, seeded_repo):
    engine = SimulationEngine(credit, rng=random.Random(1))
    profile = seeded_repo.list_profiles()[0]
    result = engine.fire_once(profile.user_id)
    assert result is not None and result.outcome in set(Outcome)
    with pytest.raises(CreditError):
        engine.fire_once(9999)


def test_engine_warns_once_when_team_has_no_services(credit, seeded_repo, bus):
    team = seeded_repo.list_teams()[0]
    seeded_repo.set_team_access(team.id, [])
    messages = []
    bus.subscribe(lambda e: messages.append(e.payload.get("message")) if e.kind == "simulation" else None)
    engine = SimulationEngine(credit, tick_seconds=5.0, rng=random.Random(1))
    for _ in range(3):
        engine.step()
    assert sum(1 for m in messages if m and "servis yok" in m) == 1


def test_engine_thread_starts_and_stops(credit, seeded_repo):
    engine = SimulationEngine(credit, tick_seconds=0.05, rng=random.Random(1))
    engine.speed = 50
    engine.start()
    assert engine.running
    import time

    deadline = time.time() + 3
    while not seeded_repo.usage and time.time() < deadline:
        time.sleep(0.05)
    engine.stop()
    assert not engine.running
    assert seeded_repo.usage
