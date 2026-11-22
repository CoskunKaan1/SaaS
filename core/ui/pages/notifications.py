from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from core.models import Notification, Severity
from core.ui import format as fmt
from core.ui.context import AppContext
from core.ui.widgets.common import Card, Page, Pill, Segmented, button, label

_TONE = {Severity.CRITICAL: ("critical", "Kritik"), Severity.WARNING: ("warning", "Uyarı"),
         Severity.INFO: ("neutral", "Bilgi")}


class _Item(QFrame):
    def __init__(self, n: Notification):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 12, 4, 12)
        lay.setSpacing(14)
        tone, text = _TONE[n.severity]
        pill = Pill(text, tone)
        pill.setFixedWidth(58)
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(pill, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        title = label(n.title, "SectionTitle", wrap=True)
        if n.is_read:
            title.setObjectName("Muted")
        texts.addWidget(title)
        texts.addWidget(label(n.body, "Faint", wrap=True))
        lay.addLayout(texts, 1)
        when = label(f"{fmt.ago(n.created_at)}\n{fmt.when(n.created_at)}", "Faint")
        when.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        lay.addWidget(when)


class NotificationsPage(Page):
    LIMIT = 150

    def __init__(self, ctx: AppContext, on_change):
        super().__init__("Bildirimler", "Eşik uyarıları, limit aşımları ve sıfırlama kayıtları.")
        self.ctx, self.on_change = ctx, on_change
        self.filter = Segmented([("Tümü", False), ("Okunmamış", True)])
        self.filter.changed.connect(lambda _: self.refresh(force=True))
        self.actions.addWidget(button("Tümünü okundu say", None, self.mark_read))

        card = Card()
        card.body.addWidget(self.filter, 0, Qt.AlignmentFlag.AlignLeft)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.list_host = QWidget()
        self.list = QVBoxLayout(self.list_host)
        self.list.setContentsMargins(0, 0, 8, 0)
        self.list.setSpacing(0)
        scroll.setWidget(self.list_host)
        card.body.addWidget(scroll, 1)
        self.content.addWidget(card, 1)
        self._signature: tuple | None = None

    def refresh(self, force: bool = False) -> None:
        items = self.ctx.repo.list_notifications(self.LIMIT, bool(self.filter.value()))
        signature = tuple((n.id, n.is_read) for n in items)
        if signature == self._signature and not force:
            # yalnızca "x dk önce" metinlerinin yaşlanması için tam yeniden çizim gerekmez
            return
        self._signature = signature
        while self.list.count():
            item = self.list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not items:
            empty = label("Gösterilecek bildirim yok.", "Muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(120)
            self.list.addWidget(empty)
        for i, n in enumerate(items):
            if i:
                line = QFrame()
                line.setObjectName("Divider")
                self.list.addWidget(line)
            self.list.addWidget(_Item(n))
        self.list.addStretch(1)

    def mark_read(self) -> None:
        self.ctx.repo.mark_all_read()
        self.refresh(force=True)
        self.on_change()
