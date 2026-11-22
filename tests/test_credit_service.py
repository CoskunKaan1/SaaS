from decimal import Decimal

import pytest

from core.models import Outcome, Severity
from core.services.credit_service import CreditError, CreditService, compute_cost


def test_compute_cost_rounds_to_four_places():
    assert compute_cost(3, Decimal("0.33333")) == Decimal("1.0000")
    assert compute_cost(12, Decimal("0.80")) == Decimal("9.6000")


def test_successful_call_is_charged(small_team):
    t = small_team
    result = t["credit"].charge(t["user"], t["service"], 10)
    assert result.outcome is Outcome.OK
    assert result.credits == Decimal(10)
    assert t["repo"].budget_statuses()[0].spent == Decimal(10)


def test_failed_call_is_recorded_but_not_charged(small_team):
    t = small_team
    result = t["credit"].charge(t["user"], t["service"], 10, status_code=503)
    assert result.outcome is Outcome.ERROR
    assert result.credits == 0
    status = t["repo"].budget_statuses()[0]
    assert status.spent == 0 and status.calls == 1


def test_call_exceeding_limit_is_rejected(small_team):
    t = small_team
    t["credit"].charge(t["user"], t["service"], 95)
    result = t["credit"].charge(t["user"], t["service"], 10)
    assert result.outcome is Outcome.REJECTED
    status = t["repo"].budget_statuses()[0]
    assert status.spent == Decimal(95)
    assert status.rejected == 1


def test_exact_limit_is_allowed(small_team):
    t = small_team
    assert t["credit"].charge(t["user"], t["service"], 100).outcome is Outcome.OK


def test_warning_notification_only_once(small_team):
    t = small_team
    for _ in range(9):  # 90 kredi; %80 eşiği bir kez geçilir
        t["credit"].charge(t["user"], t["service"], 10)
    warnings = [n for n in t["repo"].list_notifications() if n.severity is Severity.WARNING]
    assert len(warnings) == 1
    assert "%80" in warnings[0].title


def test_critical_notification_when_limit_reached_and_not_repeated(small_team):
    t = small_team
    t["credit"].charge(t["user"], t["service"], 100)
    for _ in range(5):
        t["credit"].charge(t["user"], t["service"], 1)  # hepsi reddedilir
    critical = [n for n in t["repo"].list_notifications() if n.severity is Severity.CRITICAL]
    assert len(critical) == 1


def _critical_count(repo):
    return sum(1 for n in repo.notifications if n.severity is Severity.CRITICAL)


def _short_count(repo):
    return sum(1 for n in repo.notifications if "yetmedi" in n.title)


def test_first_rejection_below_limit_warns_without_claiming_full(small_team):
    t = small_team
    t["credit"].charge(t["user"], t["service"], 95)
    t["credit"].charge(t["user"], t["service"], 10)
    t["credit"].charge(t["user"], t["service"], 10)
    assert _short_count(t["repo"]) == 1
    assert _critical_count(t["repo"]) == 0
    assert t["credit"].charge(t["user"], t["service"], 1).outcome is Outcome.OK  # küçük çağrı hâlâ geçer


def test_oversized_call_on_empty_budget_is_not_reported_as_full(small_team):
    t = small_team
    t["credit"].charge(t["user"], t["service"], 101)
    assert _critical_count(t["repo"]) == 0
    assert "kalan 100.00 kredi" in t["repo"].notifications[-1].body


def test_filling_limit_after_rejection_reports_full_once(small_team):
    t = small_team
    t["credit"].charge(t["user"], t["service"], 95)
    assert t["credit"].charge(t["user"], t["service"], 10).outcome is Outcome.REJECTED
    assert t["credit"].charge(t["user"], t["service"], 5).outcome is Outcome.OK  # limit tam doldu
    t["credit"].charge(t["user"], t["service"], 1)
    assert (_short_count(t["repo"]), _critical_count(t["repo"])) == (1, 1)


@pytest.mark.parametrize("first,then,expected", [((95, 10), 10, (1, 0)), ((95, 10), 5, (1, 1)), ((100,), 1, (0, 1))])
def test_limit_alerts_not_repeated_after_restart(small_team, first, then, expected):
    t = small_team
    for units in first:
        t["credit"].charge(t["user"], t["service"], units)
    CreditService(t["repo"]).charge(t["user"], t["service"], then)
    assert (_short_count(t["repo"]), _critical_count(t["repo"])) == expected


def test_restart_still_finds_alert_behind_newer_notifications(small_team):
    t = small_team
    t["credit"].charge(t["user"], t["service"], 101)
    for _ in range(150):  # list_notifications varsayılanı 100 satır döndürür
        t["credit"].notify(Severity.INFO, "Başka bildirim", "gövde")
    CreditService(t["repo"]).charge(t["user"], t["service"], 101)
    assert _short_count(t["repo"]) == 1


@pytest.mark.parametrize("limit,warn,full", [(100, 70, 0), (97, 80, 0), (90, 80, 1)])
def test_shortfall_not_repeated_when_limit_is_not_raised(small_team, limit, warn, full):
    t = small_team
    t["credit"].charge(t["user"], t["service"], 95)
    t["credit"].charge(t["user"], t["service"], 10)
    t["credit"].set_budget(t["team"], Decimal(limit), warn)
    t["credit"].charge(t["user"], t["service"], 10)
    assert (_short_count(t["repo"]), _critical_count(t["repo"])) == (1, full)


def test_raised_limit_rearms_shortfall_once_even_after_restart(small_team):
    t = small_team
    t["credit"].charge(t["user"], t["service"], 95)
    t["credit"].charge(t["user"], t["service"], 10)
    t["credit"].set_budget(t["team"], Decimal(2000), 80)  # gövdede binlik ayırıcı: 2,000.00
    CreditService(t["repo"]).charge(t["user"], t["service"], 1906)
    assert _short_count(t["repo"]) == 2
    CreditService(t["repo"]).charge(t["user"], t["service"], 1906)
    assert _short_count(t["repo"]) == 2


@pytest.mark.parametrize("units,expected", [(100, (1, 1)), (101, (2, 0))])
def test_reset_in_same_second_still_notifies_new_period(small_team, units, expected):
    t = small_team
    # DATETIME2(0): eski bildirim ile yeni dönemin başlangıcı aynı saniyeye düşebilir.
    second = t["repo"].now().replace(microsecond=0)
    t["repo"].now = lambda: second
    t["credit"].charge(t["user"], t["service"], 101)
    t["credit"].reset_team(t["team"])
    CreditService(t["repo"]).charge(t["user"], t["service"], units)
    assert (_short_count(t["repo"]), _critical_count(t["repo"])) == expected


@pytest.mark.parametrize("limit,warn,expected", [(70, 80, (1, 0)), (100, 50, (1, 0)), (50, 80, (1, 1)), (200, 80, (0, 0))])
def test_budget_change_reports_newly_reached_thresholds(small_team, limit, warn, expected):
    t = small_team
    t["credit"].charge(t["user"], t["service"], 60)
    for _ in range(2):  # aynı değeri tekrar kaydetmek bildirimi tekrarlamaz
        t["credit"].set_budget(t["team"], Decimal(limit), warn)
    notes = [n.severity for n in t["repo"].notifications]
    assert (notes.count(Severity.WARNING), notes.count(Severity.CRITICAL)) == expected
    assert "Kalan -" not in " ".join(n.body for n in t["repo"].notifications)


def test_single_team_reset_notifies(small_team):
    t = small_team
    t["credit"].reset_team(t["team"], "Ay sonu")
    note = t["repo"].notifications[-1]
    assert (note.team_id, note.severity) == (t["team"], Severity.INFO)
    assert "Ay sonu" in note.body


def test_same_second_reset_then_lowered_limit_still_notifies(small_team):
    t = small_team
    second = t["repo"].now().replace(microsecond=0)
    t["repo"].now = lambda: second
    t["credit"].charge(t["user"], t["service"], 100)
    t["credit"].reset_team(t["team"])
    t["credit"].charge(t["user"], t["service"], 60)
    t["credit"].set_budget(t["team"], Decimal(50), 80)
    t["credit"].charge(t["user"], t["service"], 1)
    assert _critical_count(t["repo"]) == 2


def test_same_second_higher_limit_of_previous_period_is_ignored(small_team):
    t = small_team
    second = t["repo"].now().replace(microsecond=0)
    t["repo"].now = lambda: second
    t["credit"].set_budget(t["team"], Decimal(1000), 80)
    t["credit"].charge(t["user"], t["service"], 1001)
    t["credit"].reset_team(t["team"])
    for limit in (100, 150):
        t["credit"].set_budget(t["team"], Decimal(limit), 80)
        t["credit"].charge(t["user"], t["service"], 200)
    assert _short_count(t["repo"]) == 3


def test_other_critical_notifications_do_not_suppress_limit_alert(small_team):
    t = small_team
    t["credit"].notify(Severity.CRITICAL, "Servis kesintisi", "gövde", t["team"])
    other = t["repo"].add_team(1, "Beta")
    t["credit"].notify(Severity.CRITICAL, "Beta: kredi limiti doldu", "Dönem limiti 100.00 kredi.", other)
    t["credit"].charge(t["user"], t["service"], 100)
    assert _critical_count(t["repo"]) == 3


def test_reset_opens_new_period_and_keeps_history(small_team):
    t = small_team
    t["credit"].charge(t["user"], t["service"], 60)
    old = t["repo"].get_active_budget(t["team"])
    new_id = t["credit"].reset_team(t["team"], "test")
    assert new_id != old.id
    assert t["repo"].budgets[old.id].closed_at is not None
    assert t["repo"].budgets[old.id].close_reason == "test"
    assert t["repo"].budget_statuses()[0].spent == 0
    assert t["repo"].budget_spent(old.id) == Decimal(60)  # geçmiş korunur


def test_reset_allows_spending_again_and_rearms_notifications(small_team):
    t = small_team
    t["credit"].charge(t["user"], t["service"], 100)
    t["credit"].reset_team(t["team"])
    assert t["credit"].charge(t["user"], t["service"], 100).outcome is Outcome.OK
    critical = [n for n in t["repo"].list_notifications() if n.severity is Severity.CRITICAL]
    assert len(critical) == 2


def test_reset_all_resets_every_team_and_notifies(credit, seeded_repo):
    before = {s.team_id: s.team_budget_id for s in seeded_repo.budget_statuses()}
    count = credit.reset_all("Ay sonu")
    after = {s.team_id: s.team_budget_id for s in seeded_repo.budget_statuses()}
    assert count == len(before)
    assert all(after[t] != before[t] for t in before)
    assert [(n.team_id, n.severity) for n in seeded_repo.list_notifications()] == [(None, Severity.INFO)]


def test_set_budget_validates(small_team):
    t = small_team
    with pytest.raises(CreditError):
        t["credit"].set_budget(t["team"], Decimal(0), 80)
    with pytest.raises(CreditError):
        t["credit"].set_budget(t["team"], Decimal(10), 100)
    t["credit"].set_budget(t["team"], Decimal(500), 50)
    b = t["repo"].get_active_budget(t["team"])
    assert b.credit_limit == Decimal(500) and b.warn_percent == 50


def test_raising_limit_rearms_full_notification(small_team):
    t = small_team
    t["credit"].charge(t["user"], t["service"], 100)
    t["credit"].set_budget(t["team"], Decimal(200), 80)
    assert t["credit"].charge(t["user"], t["service"], 100).outcome is Outcome.OK
    critical = [n for n in t["repo"].list_notifications() if n.severity is Severity.CRITICAL]
    assert len(critical) == 2


def test_service_without_access_is_refused(small_team):
    t = small_team
    other = t["repo"].add_service(1, "Yetkisiz", "istek", Decimal(1))
    with pytest.raises(CreditError, match="erişim izni yok"):
        t["credit"].charge(t["user"], other, 1)


def test_inactive_or_unknown_user_is_refused(small_team):
    t = small_team
    with pytest.raises(CreditError):
        t["credit"].charge(999, t["service"], 1)
    t["repo"].set_user_active(t["user"], False)
    with pytest.raises(CreditError, match="pasif"):
        t["credit"].charge(t["user"], t["service"], 1)


def test_non_positive_units_refused(small_team):
    t = small_team
    with pytest.raises(CreditError):
        t["credit"].charge(t["user"], t["service"], 0)


def test_events_are_published(small_team, bus):
    t = small_team
    seen = []
    bus.subscribe(lambda e: seen.append(e.kind))
    for _ in range(8):
        t["credit"].charge(t["user"], t["service"], 10)
    assert seen.count("usage") == 8
    assert "notification" in seen


def test_listener_failure_does_not_break_charge(small_team, bus):
    t = small_team

    def broken(_):
        raise RuntimeError("boom")

    bus.subscribe(broken)
    assert t["credit"].charge(t["user"], t["service"], 1).outcome is Outcome.OK


def test_concurrent_charges_never_exceed_limit(small_team):
    import threading

    t = small_team

    def worker():
        for _ in range(30):
            t["credit"].charge(t["user"], t["service"], 3)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert t["repo"].budget_statuses()[0].spent <= Decimal(100)
