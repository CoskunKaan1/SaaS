from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox

from core.models import Outcome
from core.ui import format as fmt
from core.ui.context import AppContext
from core.ui.widgets.common import Card, Page, hbox, label
from core.ui.widgets.table import RIGHT, Column, DataTable

_OUTCOME = {Outcome.OK: ("Başarılı", None), Outcome.ERROR: ("Hata", "warn"), Outcome.REJECTED: ("Reddedildi", "crit")}


class UsagePage(Page):
    LIMIT = 300

    def __init__(self, ctx: AppContext):
        super().__init__("Kullanım kayıtları", "Her satır bir API çağrısı. Hatalı ve reddedilen çağrılar ücretlendirilmez.")
        self.ctx = ctx

        self.team = QComboBox()
        self.team.setMinimumWidth(180)
        self.outcome = QComboBox()
        self.outcome.addItem("Tüm sonuçlar", None)
        for o, (text, _) in _OUTCOME.items():
            self.outcome.addItem(text, o)
        self.live = QCheckBox("Canlı akış")
        self.live.setChecked(True)
        self.count = label("", "Faint")
        self.team.currentIndexChanged.connect(lambda _: self.refresh(force=True))
        self.outcome.currentIndexChanged.connect(lambda _: self.refresh(force=True))

        self.table = DataTable(
            [
                Column("#", lambda r: r.id, RIGHT, tone=lambda r: "text_3", width=70),
                Column("Zaman", lambda r: fmt.clock(r.created_at), width=90),
                Column("Kullanıcı", lambda r: r.user_name, width=170),
                Column("Ekip", lambda r: r.team_name, width=130),
                Column("Servis", lambda r: r.service_name, stretch=True),
                Column("Birim", lambda r: fmt.number(r.units), RIGHT),
                Column("Kredi", lambda r: fmt.credits(r.credits) if r.credits else "—", RIGHT,
                       tone=lambda r: None if r.credits else "text_3"),
                Column("Gecikme", lambda r: f"{fmt.number(r.latency_ms)} ms", RIGHT, tone=lambda r: "text_3"),
                Column("HTTP", lambda r: r.status_code, RIGHT, tone=lambda r: "warn" if r.status_code >= 400 else "text_3"),
                Column("Sonuç", lambda r: _OUTCOME[r.outcome][0], width=100, tone=lambda r: _OUTCOME[r.outcome][1]),
            ]
        )
        card = Card()
        card.body.addLayout(hbox(self.team, self.outcome, None, self.count, 12, self.live))
        card.body.addWidget(self.table)
        self.content.addWidget(card)

    def _fill_teams(self) -> None:
        current = self.team.currentData()
        teams = self.ctx.repo.list_teams()
        if self.team.count() == len(teams) + 1:
            return
        self.team.blockSignals(True)
        self.team.clear()
        self.team.addItem("Tüm ekipler", None)
        for t in teams:
            self.team.addItem(t.name, t.id)
        self.team.setCurrentIndex(max(0, self.team.findData(current)))
        self.team.blockSignals(False)

    def refresh(self, force: bool = False) -> None:
        self._fill_teams()
        if not force and not self.live.isChecked() and self.table.model_.rows:
            return
        rows = self.ctx.repo.recent_usage(self.LIMIT, self.team.currentData(), self.outcome.currentData())
        self.table.set_rows(rows)
        self.count.setText(f"Son {len(rows)} kayıt")
