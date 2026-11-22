"""Sanal kullanıcı davranış tipleri.

Her persona, bir simülasyon adımında (tick) kaç çağrı yapılacağını ve
çağrıların ne kadar "büyük" olacağını belirler. Çağrı sayıları Poisson
dağılımından çekilir; böylece trafik düzenli ama mekanik görünmez.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

PERSONAS: dict[str, str] = {
    "steady": "Düzenli — sabit hızda çağrı",
    "bursty": "Ani yük — sessiz bekleyip toplu çağrı",
    "heavy": "Ağır iş — az ama büyük çağrı",
    "wave": "Dalgalı — gün içi trafik gibi inip çıkan",
}


def poisson(lam: float, rng: random.Random) -> int:
    """Knuth algoritması; küçük λ değerleri için yeterli ve bağımlılıksız."""
    if lam <= 0:
        return 0
    if lam > 30:  # büyük λ için normal yaklaşım
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    threshold, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


@dataclass
class PersonaState:
    burst_ticks_left: int = 0
    phase: float = field(default_factory=lambda: random.random() * math.tau)


def plan_tick(
    persona: str,
    calls_per_minute: int,
    tick_seconds: float,
    elapsed: float,
    state: PersonaState,
    rng: random.Random,
) -> tuple[int, float]:
    """Bu adımda yapılacak (çağrı sayısı, boyut çarpanı) çiftini döndürür."""
    lam = calls_per_minute * tick_seconds / 60.0

    if persona == "bursty":
        if state.burst_ticks_left > 0:
            state.burst_ticks_left -= 1
            return poisson(lam * 6, rng), 1.0
        if rng.random() < 0.02:
            state.burst_ticks_left = rng.randint(4, 10)
        return poisson(lam * 0.3, rng), 1.0

    if persona == "heavy":
        return poisson(lam, rng), 3.0

    if persona == "wave":
        # ~3 dakikalık periyotla 0.2x ile 1.8x arasında salınım
        factor = 1.0 + 0.8 * math.sin(elapsed * math.tau / 180.0 + state.phase)
        return poisson(lam * factor, rng), 1.0

    return poisson(lam, rng), 1.0  # steady
