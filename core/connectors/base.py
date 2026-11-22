"""Bağlayıcı sözleşmesi."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.models import ApiService


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    units: int
    latency_ms: int

    @property
    def ok(self) -> bool:
        return self.status_code < 400


class ApiConnector(ABC):
    """Bir servise tek bir çağrı yapar ve tüketilen birimi raporlar."""

    @abstractmethod
    def call(self, service: ApiService, *, size_factor: float = 1.0,
             error_rate: float = 0.0, rng: random.Random | None = None) -> ApiResponse: ...
