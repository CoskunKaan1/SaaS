"""Basit, iş parçacığı güvenli olay yayıncısı.

İş katmanı Qt'ye bağımlı değildir; arayüz bu yayıncıya abone olup olayları
Qt sinyallerine çevirir (bkz. ``core.ui.bridge``).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    kind: str  # "usage" | "notification" | "reset" | "budget" | "simulation"
    payload: dict[str, Any] = field(default_factory=dict)
    at: datetime = field(default_factory=datetime.now)


Listener = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []
        self._lock = threading.Lock()

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def publish(self, kind: str, **payload: Any) -> Event:
        event = Event(kind, payload)
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:  # bir dinleyicinin hatası diğerlerini durdurmamalı
                log.exception("Olay dinleyicisi hata verdi: %s", kind)
        return event
