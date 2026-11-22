"""Gerçek ağ isteği yapmadan API yanıtı üreten bağlayıcı."""

from __future__ import annotations

import random

from core.connectors.base import ApiConnector, ApiResponse
from core.models import ApiService

# Birim türüne göre tek çağrıda tüketilen birim aralığı.
_UNIT_RANGES: dict[str, tuple[int, int]] = {
    "1K token": (1, 12),
    "sayfa": (1, 15),
    "mesaj": (1, 3),
}
_ERROR_CODES = (429, 500, 503)


class SimulatedApiConnector(ApiConnector):
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def call(self, service: ApiService, *, size_factor: float = 1.0,
             error_rate: float = 0.0, rng: random.Random | None = None) -> ApiResponse:
        r = rng or self.rng
        low, high = _UNIT_RANGES.get(service.unit_name, (1, 1))
        units = max(1, round(r.randint(low, high) * max(size_factor, 0.1)))

        # Dahili servisler daha hızlı; harici servislerde uzun kuyruklu gecikme.
        if service.provider_kind == "internal":
            latency = max(3, int(r.gauss(25, 8)))
        else:
            latency = max(40, int(r.lognormvariate(5.3, 0.45)))

        status = r.choice(_ERROR_CODES) if r.random() < error_rate else 200
        return ApiResponse(status_code=status, units=units, latency_ms=latency)
