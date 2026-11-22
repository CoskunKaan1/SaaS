"""Kredi düşme, eşik uyarıları ve dönem sıfırlama kuralları."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal

from core.db.repository import Repository
from core.models import Outcome, Severity, TeamBudget
from core.services.events import EventBus

FOUR_PLACES = Decimal("0.0001")
# Kredi yetmedi uyarısının hangi limit için verildiği gövdeden okunur. Limit
# yükseltilirse uyarının yeniden verilmesi gerekir.
SHORT_TITLE = "{team}: kalan kredi çağrıya yetmedi"
SHORT_BODY = "Dönem limiti {limit:,.2f} kredi, kalan {left:,.2f} kredi. Kalanı aşan çağrılar reddedilir."
SHORT_BODY_LIMIT = re.compile(r"^Dönem limiti ([\d,]+\.\d\d) kredi,")


class CreditError(Exception):
    """İş kuralı ihlali (ör. bilinmeyen kullanıcı, yetkisiz servis)."""


@dataclass(frozen=True)
class ChargeResult:
    usage_id: int
    outcome: Outcome
    credits: Decimal
    spent_after: Decimal
    credit_limit: Decimal
    team_id: int
    notifications: tuple[int, ...] = ()

    @property
    def ratio(self) -> float:
        return float(self.spent_after / self.credit_limit) if self.credit_limit else 0.0


def compute_cost(units: int, credit_per_unit: Decimal) -> Decimal:
    return (Decimal(units) * Decimal(credit_per_unit)).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


class CreditService:
    def __init__(self, repo: Repository, bus: EventBus | None = None):
        self.repo = repo
        self.bus = bus or EventBus()
        # Aynı ekibe eşzamanlı iki çağrının ikisinin de limiti "boş" görmesini
        # engeller. Uygulama tek süreç olduğu için süreç içi kilit yeterlidir;
        # veritabanı tarafında da işlem (transaction) bütünlüğü sağlanır.
        self._lock = threading.RLock()
        # Dönem -> kredi yetmedi uyarısı verilmiş limit. Yalnızca her redde
        # yeniden sorgulamamak için önbellektir; asıl bilgi veritabanındadır.
        self._short_limit: dict[int, Decimal] = {}

    # ------------------------------------------------------------------
    def charge(
        self,
        user_id: int,
        service_id: int,
        units: int,
        status_code: int = 200,
        latency_ms: int = 0,
    ) -> ChargeResult:
        """Bir API çağrısını kaydeder ve ekibin bütçesinden düşer.

        * Başarısız çağrılar (status >= 400) kaydedilir ama ücretlendirilmez.
        * Limit yetmiyorsa çağrı ``rejected`` olarak kaydedilir, kredi düşülmez.
        * Eşik geçilince, limit dolunca ve kalan kredi ilk kez yetmeyince bildirim üretilir.
        """
        if units <= 0:
            raise CreditError("Birim sayısı pozitif olmalı.")
        user = self.repo.get_user(user_id)
        if user is None:
            raise CreditError(f"Kullanıcı bulunamadı: #{user_id}")
        if not user.is_active:
            raise CreditError(f"Kullanıcı pasif: {user.full_name}")
        service = next((s for s in self.repo.list_team_services(user.team_id) if s.id == service_id), None)
        if service is None:
            # İkinci sorgu yalnızca hatanın nedenini söyleyebilmek için yapılır.
            other = self.repo.get_service(service_id)
            if other is None or not other.is_active:
                raise CreditError(f"Servis bulunamadı veya kapalı: #{service_id}")
            raise CreditError(f"{user.team_name} ekibinin {other.name} servisine erişim izni yok.")

        notes: list[int] = []
        with self._lock, self.repo.transaction():
            budget = self.repo.get_active_budget(user.team_id)
            if budget is None:
                raise CreditError(f"{user.team_name} ekibinin açık bütçe dönemi yok.")
            before = self.repo.budget_spent(budget.id)
            cost = compute_cost(units, service.credit_per_unit)

            if status_code >= 400:
                outcome, charged = Outcome.ERROR, Decimal(0)
            elif before + cost > budget.credit_limit:
                outcome, charged = Outcome.REJECTED, Decimal(0)
            else:
                outcome, charged = Outcome.OK, cost

            usage_id = self.repo.add_usage(
                budget.id, user.id, service.id, units, charged, status_code, latency_ms, outcome
            )
            after = before + charged
            notes.extend(self._threshold_notifications(budget, user.team_name, before, after))
            if outcome is Outcome.REJECTED and before < budget.credit_limit:
                notes.extend(self._shortfall_notification(budget, user.team_name, before))

        result = ChargeResult(usage_id, outcome, charged, after, budget.credit_limit, user.team_id, tuple(notes))
        self.bus.publish(
            "usage",
            usage_id=usage_id,
            user_id=user.id,
            user_name=user.full_name,
            team_id=user.team_id,
            team_name=user.team_name,
            service_name=service.name,
            units=units,
            credits=charged,
            outcome=outcome.value,
            ratio=result.ratio,
        )
        return result

    def _threshold_notifications(
        self, budget: TeamBudget, team_name: str, before: Decimal, after: Decimal,
        previous: TeamBudget | None = None,
    ) -> list[int]:
        """Harcama artınca veya bütçe değişince yeni geçilen eşikleri bildirir.

        ``previous`` bütçenin değişiklikten önceki hâlidir. Karar yalnızca önceki
        ve sonraki duruma bakar, bu yüzden yeniden başlatmada tekrar etmez.
        """
        old = previous or budget
        limit = budget.credit_limit

        def newly_reached(old_percent: int, percent: int) -> bool:
            return before * 100 < old.credit_limit * old_percent and after * 100 >= limit * percent

        created: list[int] = []
        if newly_reached(old.warn_percent, budget.warn_percent):
            created.append(
                self._notify(
                    budget.team_id,
                    Severity.WARNING,
                    f"{team_name}: bütçenin %{budget.warn_percent}'i kullanıldı",
                    f"Harcanan {after:,.2f} / {limit:,.2f} kredi. Kalan {max(Decimal(0), limit - after):,.2f} kredi.",
                )
            )
        if newly_reached(100, 100):
            created.append(
                self._notify(
                    budget.team_id,
                    Severity.CRITICAL,
                    f"{team_name}: kredi limiti doldu",
                    f"Dönem limiti {limit:,.2f} kredi. Yeni çağrılar sıfırlamaya veya limit artışına kadar reddedilecek.",
                )
            )
        return created

    def _shortfall_notification(self, budget: TeamBudget, team_name: str, spent: Decimal) -> list[int]:
        """Limit dolmadan gelen ret: dönem ve limit başına bir kez uyarır."""
        limit = budget.credit_limit
        if self._short_limit.get(budget.id, Decimal(0)) >= limit:
            return []
        title = SHORT_TITLE.format(team=team_name)
        # Bildirim zamanı saniye hassasiyetinde olduğundan önce dönemin kendi ret
        # kayıtlarına bakılır; önceki dönemin aynı saniyedeki uyarısı böylece karışmaz.
        if self.repo.has_previous_rejection(budget.id):
            body = self.repo.last_notification_body(budget.team_id, title, budget.started_at)
            if body and (match := SHORT_BODY_LIMIT.match(body)):
                reported = Decimal(match[1].replace(",", ""))
                if reported >= limit:
                    self._short_limit[budget.id] = reported
                    return []
        body = SHORT_BODY.format(limit=limit, left=limit - spent)
        return [self._notify(budget.team_id, Severity.WARNING, title, body)]

    def _notify(self, team_id: int | None, severity: Severity, title: str, body: str) -> int:
        nid = self.repo.add_notification(team_id, severity, title, body)
        self.bus.publish("notification", id=nid, team_id=team_id, severity=severity.value, title=title, body=body)
        return nid

    # ------------------------------------------------------------------
    def notify(self, severity: Severity, title: str, body: str, team_id: int | None = None) -> int:
        return self._notify(team_id, severity, title, body)

    def reset_team(self, team_id: int, reason: str = "Elle sıfırlama") -> int:
        with self._lock, self.repo.transaction():
            name = self._team_name(team_id)
            new_id = self.repo.reset_team_budget(team_id, reason)
            self._notify(team_id, Severity.INFO, f"{name}: krediler sıfırlandı",
                         f"Bütçe dönemi kapatılıp yenisi açıldı. Sebep: {reason}.")
        self.bus.publish("reset", team_id=team_id, team_budget_id=new_id, reason=reason)
        return new_id

    def reset_all(self, reason: str = "Dönem sıfırlama") -> int:
        done: list[tuple[int, int]] = []
        with self._lock, self.repo.transaction():  # ya hepsi sıfırlanır ya hiçbiri
            for status in self.repo.budget_statuses():
                done.append((status.team_id, self.repo.reset_team_budget(status.team_id, reason)))
            if done:
                self._notify(None, Severity.INFO, "Krediler sıfırlandı",
                             f"{len(done)} ekibin bütçe dönemi kapatılıp yenisi açıldı. Sebep: {reason}.")
        for team_id, new_id in done:
            self.bus.publish("reset", team_id=team_id, team_budget_id=new_id, reason=reason)
        return len(done)

    def _team_name(self, team_id: int) -> str:
        return next((t.name for t in self.repo.list_teams() if t.id == team_id), f"Ekip #{team_id}")

    def set_budget(self, team_id: int, credit_limit: Decimal, warn_percent: int) -> int:
        credit_limit = Decimal(credit_limit)
        if credit_limit <= 0:
            raise CreditError("Kredi limiti pozitif olmalı.")
        if not 1 <= warn_percent <= 99:
            raise CreditError("Uyarı eşiği 1 ile 99 arasında olmalı.")
        with self._lock, self.repo.transaction():
            budget = self.repo.get_active_budget(team_id)
            if budget is None:
                bid = self.repo.open_budget(team_id, credit_limit, warn_percent)
            else:
                bid = budget.id
                self.repo.update_budget(bid, credit_limit, warn_percent)
                spent = self.repo.budget_spent(bid)
                changed = replace(budget, credit_limit=credit_limit, warn_percent=warn_percent)
                self._threshold_notifications(changed, self._team_name(team_id), spent, spent, previous=budget)
        self.bus.publish("budget", team_id=team_id, team_budget_id=bid)
        return bid
