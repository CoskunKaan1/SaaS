"""Test paneli: sanal kullanıcı oluşturma, davranış simülasyonu ve sıfırlama."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.connectors.testusers import PERSONAS, TestUserError, attach_user, create_test_user
from core.services.credit_service import CreditError
from core.services.events import Event
from core.ui import format as fmt
from core.ui.context import AppContext
from core.ui.widgets.common import Card, Page, Pill, Segmented, button, hbox, label
from core.ui.widgets.table import RIGHT, Column, DataTable

RESET_CHOICES = [("Kapalı", 0), ("1 dakika", 60), ("5 dakika", 300), ("15 dakika", 900),
                 ("1 saat", 3600), ("1 gün", 86400)]
_OUTCOME_TEXT = {"ok": "ok ", "error": "hata", "rejected": "RED"}


def _field(title: str, widget: QWidget) -> QVBoxLayout:
    box = QVBoxLayout()
    box.setSpacing(5)
    lbl = QLabel(title)
    lbl.setProperty("role", "field")
    box.addWidget(lbl)
    box.addWidget(widget)
    return box


def _persona_combo() -> QComboBox:
    combo = QComboBox()
    for key, text in PERSONAS.items():
        combo.addItem(text, key)
    return combo


def _rate_spin(value: int = 12) -> QSpinBox:
    s = QSpinBox()
    s.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    s.lineEdit().setTextMargins(8, 0, 0, 0)
    s.setRange(1, 600)
    s.setValue(value)
    s.setSuffix(" çağrı/dk")
    return s


def _error_spin(value: float = 2.0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    s.lineEdit().setTextMargins(8, 0, 0, 0)
    s.setRange(0, 100)
    s.setDecimals(1)
    s.setValue(value)
    s.setPrefix("%")
    return s


class SimulatorPage(Page):
    def __init__(self, ctx: AppContext, toast):
        super().__init__(
            "Test paneli",
            "Gerçek API'ler yerine sanal kullanıcılar kredi harcar. Kullanıcı oluşturun ya da var olan bir "
            "kullanıcıyı ID'si ile dahil edin; davranışını ve sıfırlama aralığını buradan yönetin.",
        )
        self.ctx, self.toast = ctx, toast
        self.state_pill = Pill("", "neutral")
        self.run_btn = button("", "primary", self.toggle_engine)
        self.actions.addWidget(self.state_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        self.actions.addWidget(self.run_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(0, 0, 4, 0)
        grid.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(self._build_create_card())
        left.addWidget(self._build_attach_card())
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(self._build_engine_card())
        right.addWidget(self._build_agents_card())
        right.addWidget(self._build_log_card(), 1)

        left_host = QWidget()
        left_host.setLayout(left)
        left_host.setFixedWidth(360)
        grid.addWidget(left_host, 0, 0, Qt.AlignmentFlag.AlignTop)
        grid.addLayout(right, 0, 1)
        grid.setColumnStretch(1, 1)
        scroll.setWidget(inner)
        self.content.addWidget(scroll)
        self._update_engine_state()
        self._lookup(self.a_id.value())

    # --- kartlar ---------------------------------------------------------
    def _build_create_card(self) -> Card:
        card = Card("Yeni test kullanıcısı", "Oluşturulan kullanıcı veritabanına sanal olarak eklenir ve "
                                            "seçilen davranışla çağrı yapmaya başlar.")
        self.c_name = QLineEdit()
        self.c_name.setPlaceholderText("ör. yuk-testi-bot")
        self.c_team = QComboBox()
        self.c_persona = _persona_combo()
        self.c_rate = _rate_spin(15)
        self.c_error = _error_spin(2.0)
        self.c_enabled = QCheckBox("Oluşturunca hemen çalıştır")
        self.c_enabled.setChecked(True)
        for title, w in (("Ad", self.c_name), ("Ekip", self.c_team), ("Davranış", self.c_persona)):
            card.body.addLayout(_field(title, w))
        card.body.addLayout(hbox(_field("Hız", self.c_rate), _field("Hata oranı", self.c_error)))
        card.body.addWidget(self.c_enabled)
        card.body.addWidget(button("Kullanıcı oluştur", "primary", self.create_user))
        self.c_result = label("", "Faint", wrap=True)
        card.body.addWidget(self.c_result)
        return card

    def _build_attach_card(self) -> Card:
        card = Card("Var olan kullanıcıyı dahil et", "Kullanıcı ID'sini girin; o kullanıcı adına sanal "
                                                    "çağrılar üretilir.")
        self.a_id = QSpinBox()
        self.a_id.setRange(1, 10_000_000)
        self.a_id.setPrefix("#")
        self.a_id.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.a_id.lineEdit().setTextMargins(8, 0, 0, 0)
        self.a_id.valueChanged.connect(self._lookup)
        self.a_who = label("", "Faint", wrap=True)
        self.a_persona = _persona_combo()
        self.a_rate = _rate_spin(10)
        self.a_error = _error_spin(1.0)
        card.body.addLayout(_field("Kullanıcı ID", self.a_id))
        card.body.addWidget(self.a_who)
        card.body.addLayout(_field("Davranış", self.a_persona))
        card.body.addLayout(hbox(_field("Hız", self.a_rate), _field("Hata oranı", self.a_error)))
        card.body.addWidget(button("Simülasyona dahil et", None, self.attach_user))
        return card

    def _build_engine_card(self) -> Card:
        card = Card("Simülasyon motoru")
        self.speed = Segmented([("1×", 1.0), ("2×", 2.0), ("5×", 5.0), ("10×", 10.0)], self.ctx.engine.speed)
        self.speed.changed.connect(self._set_speed)
        self.speed.setToolTip("Tüm sanal kullanıcıların çağrı hızını çarpar")
        self.reset_combo = QComboBox()
        for text, seconds in RESET_CHOICES:
            self.reset_combo.addItem(text, seconds)
        idx = self.reset_combo.findData(self.ctx.engine.auto_reset_seconds)
        self.reset_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.reset_combo.currentIndexChanged.connect(
            lambda _: self.ctx.engine.set_auto_reset(self.reset_combo.currentData()))
        self.next_reset = label("", "Muted")
        self.stats = label("", "Faint")
        card.body.addLayout(hbox(_field("Hız çarpanı", self.speed), 16,
                                 _field("Otomatik kredi sıfırlama", self.reset_combo), 16,
                                 _field("Sonraki sıfırlama", self.next_reset), None))
        card.body.addLayout(hbox(self.stats, None,
                                 button("Tüm kredileri şimdi sıfırla", "danger", self.reset_all)))
        return card

    def _build_agents_card(self) -> Card:
        card = Card("Sanal kullanıcılar", "Çift tıklayarak açıp kapatabilirsiniz.")
        self.table = DataTable(
            [
                Column("ID", lambda p: f"#{p.user_id}", RIGHT, tone=lambda p: "text_3", width=60),
                Column("Kullanıcı", lambda p: p.user_name, stretch=True),
                Column("Ekip", lambda p: p.team_name, width=130),
                Column("Davranış", lambda p: PERSONAS.get(p.persona, p.persona).split(" — ")[0], width=110),
                Column("Hız", lambda p: f"{p.calls_per_minute}/dk", RIGHT),
                Column("Hata", lambda p: fmt.percent(p.error_rate, 1), RIGHT, tone=lambda p: "text_3"),
                Column("Durum", lambda p: "Çalışıyor" if p.is_enabled else "Duraklatıldı", width=110,
                       tone=lambda p: "accent" if p.is_enabled else "text_3"),
            ],
            key=lambda p: p.user_id,
        )
        self.table.setMinimumHeight(240)
        self.table.doubleClicked.connect(lambda _: self.toggle_agent())
        card.header_actions.addWidget(button("Aç / kapat", None, self.toggle_agent))
        card.header_actions.addWidget(button("Tek çağrı gönder", None, self.fire_once))
        card.header_actions.addWidget(button("Çıkar", "danger", self.remove_agent))
        card.body.addWidget(self.table)
        return card

    def _build_log_card(self) -> Card:
        card = Card("Canlı akış", "Sanal kullanıcıların son çağrıları")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        self.log.setMinimumHeight(200)
        card.header_actions.addWidget(button("Temizle", "ghost", self.log.clear))
        card.body.addWidget(self.log)
        return card

    # --- yenileme ----------------------------------------------------------
    def refresh(self) -> None:
        repo = self.ctx.repo
        teams = repo.list_teams()
        if self.c_team.count() != len(teams):
            current = self.c_team.currentData()
            self.c_team.clear()
            for t in teams:
                self.c_team.addItem(f"{t.name}  ·  {t.department_name}", t.id)
            self.c_team.setCurrentIndex(max(0, self.c_team.findData(current)))
        self.table.set_rows(repo.list_profiles())
        self._update_engine_state()

    def tick(self) -> None:
        """Her saniye: geri sayım ve sayaçlar (veritabanına gitmez)."""
        engine = self.ctx.engine
        self.next_reset.setText(fmt.duration(engine.seconds_to_reset()))
        s = engine.stats
        self.stats.setText(f"Bu oturumda {fmt.number(s.calls)} çağrı  ·  {fmt.number(s.ok)} başarılı  ·  "
                           f"{fmt.number(s.errors)} hata  ·  {fmt.number(s.rejected)} red  ·  {s.resets} sıfırlama")

    def _update_engine_state(self) -> None:
        running = self.ctx.engine.running
        self.state_pill.setText("Çalışıyor" if running else "Durduruldu")
        self.state_pill.set_tone("ok" if running else "neutral")
        self.run_btn.setText("Simülasyonu durdur" if running else "Simülasyonu başlat")
        self.run_btn.setProperty("variant", None if running else "primary")
        self.run_btn.style().unpolish(self.run_btn)
        self.run_btn.style().polish(self.run_btn)
        self.tick()

    def on_event(self, event: Event) -> None:
        p = event.payload
        t = fmt.clock(event.at)
        if event.kind == "usage":
            credits = fmt.credits(p["credits"]) if p["credits"] else "—"
            self.log.appendPlainText(
                f"{t}  {_OUTCOME_TEXT.get(p['outcome'], p['outcome']):<4}  {p['user_name'][:20]:<20}  "
                f"{p['service_name'][:18]:<18}  {p['units']:>4} birim  {credits:>8} kr  "
                f"{fmt.percent(p['ratio'])} dolu"
            )
        elif event.kind == "reset":
            self.log.appendPlainText(f"{t}  ----  ekip #{p['team_id']} sıfırlandı: {p['reason']}")
        elif event.kind == "simulation":
            if p.get("message"):
                self.log.appendPlainText(f"{t}  !!!!  {p['message']}")
            self._update_engine_state()

    # --- eylemler ----------------------------------------------------------
    def toggle_engine(self) -> None:
        engine = self.ctx.engine
        engine.stop() if engine.running else engine.start()
        self._update_engine_state()

    def _set_speed(self, value) -> None:
        self.ctx.engine.speed = float(value)

    def create_user(self) -> None:
        if self.c_team.currentData() is None:
            self.c_result.setText("Önce bir ekip seçin. Ekip yoksa Ekipler sayfasından oluşturun.")
            return
        try:
            uid = create_test_user(
                self.ctx.repo, self.c_team.currentData(), self.c_name.text(), self.c_persona.currentData(),
                self.c_rate.value(), self.c_error.value() / 100, self.c_enabled.isChecked(),
            )
        except Exception as exc:  # noqa: BLE001 - doğrulama ve veritabanı hataları kullanıcıya gösterilir
            self.c_result.setText(f"Oluşturulamadı: {exc}")
            return
        self.ctx.engine.invalidate()
        self.c_result.setText(f"#{uid} numaralı kullanıcı oluşturuldu ve simülasyona dahil edildi.")
        self.toast("info", f"Test kullanıcısı #{uid} oluşturuldu", self.c_name.text().strip())
        self.c_name.clear()
        self.a_id.setValue(uid)
        self.refresh()

    def _lookup(self, uid: int) -> None:
        user = self.ctx.repo.get_user(uid)
        if user is None:
            self.a_who.setText("Bu ID ile kullanıcı yok.")
        else:
            kind = "sanal" if user.is_simulated else "gerçek"
            self.a_who.setText(f"{user.full_name} · {user.team_name} · {kind} kullanıcı")

    def attach_user(self) -> None:
        try:
            attach_user(self.ctx.repo, self.a_id.value(), self.a_persona.currentData(), self.a_rate.value(),
                        self.a_error.value() / 100)
        except TestUserError as exc:
            self.toast("warning", "Dahil edilemedi", str(exc))
            return
        self.ctx.engine.invalidate()
        self.toast("info", f"#{self.a_id.value()} simülasyona dahil edildi")
        self.refresh()

    def _selected(self):
        profile = self.table.selected()
        if profile is None:
            self.toast("info", "Önce tablodan bir sanal kullanıcı seçin.")
        return profile

    def toggle_agent(self) -> None:
        profile = self._selected()
        if profile:
            self.ctx.repo.set_profile_enabled(profile.user_id, not profile.is_enabled)
            self.ctx.engine.invalidate()
            self.refresh()

    def fire_once(self) -> None:
        profile = self._selected()
        if not profile:
            return
        try:
            result = self.ctx.engine.fire_once(profile.user_id)
        except CreditError as exc:
            self.toast("warning", "Çağrı yapılamadı", str(exc))
            return
        if result is None:
            self.toast("warning", "Çağrı yapılamadı", "Ekibin erişebildiği servis yok veya kural ihlali.")

    def remove_agent(self) -> None:
        profile = self._selected()
        if profile:
            self.ctx.repo.delete_profile(profile.user_id)
            self.ctx.engine.invalidate()
            self.toast("info", f"{profile.user_name} simülasyondan çıkarıldı",
                       "Kullanıcı ve geçmiş kayıtları veritabanında kalır.")
            self.refresh()

    def reset_all(self) -> None:
        answer = QMessageBox.question(
            self, "Tüm kredileri sıfırla",
            "Bütün ekiplerin açık dönemleri kapatılıp sıfır harcamayla yeni dönem açılacak. "
            "Geçmiş kayıtlar korunur. Devam edilsin mi?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            count = self.ctx.credit.reset_all("Test panelinden elle sıfırlama")
            self.toast("info", "Krediler sıfırlandı", f"{count} ekip için yeni dönem açıldı.")
