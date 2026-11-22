"""Simülasyon motoru.

Arka plan iş parçacığında çalışır. Her adımda etkin profilleri okur, her
sanal kullanıcı için personasına göre çağrı sayısını belirler, sahte
bağlayıcı üzerinden "API çağrısı" yapar ve sonucu ``CreditService.charge``
ile gerçek iş kurallarından geçirerek veritabanına yazar.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass

from core.connectors.base import ApiConnector
from core.connectors.simulated_api import SimulatedApiConnector
from core.connectors.testusers.personas import PersonaState, plan_tick
from core.models import ApiService, SimulationProfile
from core.services.credit_service import ChargeResult, CreditError, CreditService

log = logging.getLogger(__name__)

MAX_CALLS_PER_TICK = 60
PROFILE_REFRESH_SECONDS = 2.0


@dataclass
class EngineStats:
    calls: int = 0
    ok: int = 0
    errors: int = 0
    rejected: int = 0
    resets: int = 0


class SimulationEngine:
    def __init__(
        self,
        credit: CreditService,
        connector: ApiConnector | None = None,
        tick_seconds: float = 0.5,
        auto_reset_seconds: int = 0,
        rng: random.Random | None = None,
    ):
        self.credit = credit
        self.repo = credit.repo
        self.connector = connector or SimulatedApiConnector()
        self.tick_seconds = tick_seconds
        self.auto_reset_seconds = auto_reset_seconds
        self.speed = 1.0
        self.rng = rng or random.Random()
        self.stats = EngineStats()

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._states: dict[int, PersonaState] = {}
        self._profiles: list[SimulationProfile] = []
        self._services: dict[int, list[ApiService]] = {}
        self._profiles_loaded_at = 0.0
        self._started_at = time.monotonic()
        self._last_reset = time.monotonic()
        self._warned: set[tuple[int, str]] = set()

    # --- yaşam döngüsü -------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._last_reset = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="simulation", daemon=True)
        self._thread.start()
        self.credit.bus.publish("simulation", state="started")

    def stop(self, timeout: float = 3.0) -> None:
        if not self.running:
            return
        self._stop.set()
        assert self._thread is not None
        self._thread.join(timeout)
        self._thread = None
        self.credit.bus.publish("simulation", state="stopped")

    @property
    def active_agents(self) -> int:
        return sum(1 for p in self._profiles if p.is_enabled)

    def set_auto_reset(self, seconds: int) -> None:
        self.auto_reset_seconds = max(0, int(seconds))
        self._last_reset = time.monotonic()

    def seconds_to_reset(self) -> float | None:
        if not self.auto_reset_seconds:
            return None
        return max(0.0, self.auto_reset_seconds - (time.monotonic() - self._last_reset))

    def invalidate(self) -> None:
        """Profil veya erişim değiştiğinde önbelleği bir sonraki adımda yenile."""
        self._profiles_loaded_at = 0.0

    # --- ana döngü -----------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            began = time.monotonic()
            try:
                self.step()
            except Exception:  # motor ölmesin; hatayı kaydet ve devam et
                log.exception("Simülasyon adımı başarısız")
                self.credit.bus.publish("simulation", state="error")
                self._stop.wait(2.0)
            spent = time.monotonic() - began
            self._stop.wait(max(0.0, self.tick_seconds - spent))

    def step(self) -> list[ChargeResult]:
        """Tek bir simülasyon adımı; testlerde doğrudan çağrılabilir."""
        now = time.monotonic()
        if self.auto_reset_seconds and now - self._last_reset >= self.auto_reset_seconds:
            self._last_reset = now
            self.stats.resets += 1
            minutes = self.auto_reset_seconds / 60
            label = f"{minutes:g} dk" if minutes < 60 else f"{minutes / 60:g} saat"
            self.credit.reset_all(f"Otomatik sıfırlama (her {label})")

        if now - self._profiles_loaded_at >= PROFILE_REFRESH_SECONDS:
            self._reload()

        results: list[ChargeResult] = []
        elapsed = now - self._started_at
        budget = MAX_CALLS_PER_TICK
        for profile in self._profiles:
            if not profile.is_enabled or budget <= 0:
                continue
            services = self._services.get(profile.team_id) or []
            if not services:
                self._warn_once(profile, "no-service",
                                f"{profile.user_name}: ekibin erişebildiği servis yok, çağrı yapılamıyor.")
                continue
            state = self._states.setdefault(profile.user_id, PersonaState())
            count, size = plan_tick(
                profile.persona, profile.calls_per_minute, self.tick_seconds * self.speed, elapsed, state, self.rng
            )
            for _ in range(min(count, budget)):
                budget -= 1
                result = self.fire(profile, services, size)
                if result is not None:
                    results.append(result)
        return results

    def fire(self, profile: SimulationProfile, services: list[ApiService] | None = None,
             size: float = 1.0) -> ChargeResult | None:
        services = services or self.repo.list_team_services(profile.team_id)
        if not services:
            return None
        service = self.rng.choice(services)
        response = self.connector.call(service, size_factor=size, error_rate=profile.error_rate, rng=self.rng)
        try:
            result = self.credit.charge(
                profile.user_id, service.id, response.units, response.status_code, response.latency_ms
            )
        except CreditError as exc:
            self._warn_once(profile, str(exc), str(exc))
            return None
        self.stats.calls += 1
        if result.outcome.value == "ok":
            self.stats.ok += 1
        elif result.outcome.value == "error":
            self.stats.errors += 1
        else:
            self.stats.rejected += 1
        return result

    def fire_once(self, user_id: int) -> ChargeResult | None:
        """Test panelindeki "tek çağrı" düğmesi için."""
        profile = next((p for p in self.repo.list_profiles() if p.user_id == user_id), None)
        if profile is None:
            raise CreditError(f"#{user_id} için simülasyon profili yok.")
        return self.fire(profile)

    # --- yardımcılar ---------------------------------------------------
    def _reload(self) -> None:
        self._profiles = self.repo.list_profiles()
        team_ids = {p.team_id for p in self._profiles}
        self._services = {tid: self.repo.list_team_services(tid) for tid in team_ids}
        self._profiles_loaded_at = time.monotonic()

    def _warn_once(self, profile: SimulationProfile, key: str, message: str) -> None:
        marker = (profile.user_id, key)
        if marker in self._warned:
            return
        self._warned.add(marker)
        self.credit.bus.publish("simulation", state="warning", message=message, user_id=profile.user_id)
