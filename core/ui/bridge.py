"""İş katmanı olaylarını Qt sinyallerine taşır.

Simülasyon motoru arka plan iş parçacığında olay yayınlar. Sinyal, ana
iş parçacığında yaşayan bir QObject üzerinden yayıldığı için Qt bunu
otomatik olarak kuyruğa alır ve arayüz güvenle güncellenir.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from core.services.events import Event, EventBus


class EventBridge(QObject):
    event = Signal(object)

    def __init__(self, bus: EventBus, parent: QObject | None = None):
        super().__init__(parent)
        self._unsubscribe = bus.subscribe(self.event.emit)

    def detach(self) -> None:
        self._unsubscribe()


__all__ = ["Event", "EventBridge"]
