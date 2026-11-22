from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QMessageBox, QStackedWidget

from core.models import Severity
from core.ui import format as fmt
from core.ui.context import AppContext
from core.ui.dialogs import AccessDialog, BudgetDialog, DepartmentDialog, TeamDialog
from core.ui.widgets.common import Card, Page, Segmented, button, hbox
from core.ui.widgets.table import RIGHT, Column, DataTable

_STATE_TONE = {Severity.CRITICAL: "crit", Severity.WARNING: "warn"}


class TeamsPage(Page):
    def __init__(self, ctx: AppContext, toast):
        super().__init__("Ekipler ve bütçeler", "Her ekibin dönemlik kredi limiti, uyarı eşiği ve servis izinleri.")
        self.ctx, self.toast = ctx, toast

        self.view = Segmented([("Bütçeler", "budgets"), ("Kullanıcılar", "users")])
        self.view.changed.connect(self._switch)
        self.actions.addWidget(button("Yeni departman", None, self.new_department))
        self.actions.addWidget(button("Yeni ekip", "primary", self.new_team))

        self.budget_table = DataTable(
            [
                Column("Ekip", lambda s: s.team_name, stretch=True),
                Column("Departman", lambda s: s.department_name, width=170),
                Column("Limit", lambda s: fmt.credits(s.credit_limit), RIGHT),
                Column("Harcanan", lambda s: fmt.credits(s.spent), RIGHT),
                Column("Kalan", lambda s: fmt.credits(s.remaining), RIGHT),
                Column("Kullanım", lambda s: fmt.percent(s.ratio), RIGHT, tone=lambda s: _STATE_TONE.get(s.state)),
                Column("Eşik", lambda s: f"%{s.warn_percent}", RIGHT, tone=lambda s: "text_3"),
                Column("Çağrı", lambda s: fmt.number(s.calls), RIGHT),
                Column("Red", lambda s: fmt.number(s.rejected) if s.rejected else "—", RIGHT,
                       tone=lambda s: "crit" if s.rejected else "text_3"),
                Column("Dönem başı", lambda s: fmt.when(s.started_at), RIGHT, tone=lambda s: "text_3"),
            ],
            key=lambda s: s.team_id,
        )
        self.budget_table.doubleClicked.connect(lambda _: self.edit_budget())
        budget_card = Card()
        budget_card.body.addLayout(hbox(
            self.view, None,
            button("Bütçeyi düzenle", None, self.edit_budget),
            button("Servis izinleri", None, self.edit_access),
            button("Dönemi sıfırla", "danger", self.reset_team),
        ))
        budget_card.body.addWidget(self.budget_table)

        self.user_table = DataTable(
            [
                Column("ID", lambda u: f"#{u.id}", RIGHT, tone=lambda u: "text_3", width=60),
                Column("Ad", lambda u: u.full_name, stretch=True),
                Column("E-posta", lambda u: u.email, width=230),
                Column("Ekip", lambda u: u.team_name, width=150),
                Column("Rol", lambda u: {"member": "Üye", "lead": "Ekip lideri", "admin": "Yönetici",
                                         "service": "Servis hesabı"}.get(u.role, u.role), width=120),
                Column("Tür", lambda u: "Sanal" if u.is_simulated else "Gerçek", width=80,
                       tone=lambda u: "accent" if u.is_simulated else None),
                Column("Durum", lambda u: "Aktif" if u.is_active else "Pasif", width=80,
                       tone=lambda u: None if u.is_active else "text_3"),
            ]
        )
        self.user_toggle = button("Aktif / pasif yap", None, self.toggle_user)
        self.user_view = Segmented([("Bütçeler", "budgets"), ("Kullanıcılar", "users")], "users")
        self.user_view.changed.connect(self._switch)
        user_card = Card()
        user_card.body.addLayout(hbox(self.user_view, None, self.user_toggle))
        user_card.body.addWidget(self.user_table)

        self.stack = QStackedWidget()
        self.stack.addWidget(budget_card)
        self.stack.addWidget(user_card)
        self.content.addWidget(self.stack)

    def _switch(self, which) -> None:
        self.stack.setCurrentIndex(0 if which == "budgets" else 1)
        self.view.set_value(which)
        self.user_view.set_value(which)
        self.refresh()

    def refresh(self) -> None:
        if self.stack.currentIndex() == 0:
            self.budget_table.set_rows(self.ctx.repo.budget_statuses())
        else:
            self.user_table.set_rows(self.ctx.repo.list_users())

    # --- eylemler --------------------------------------------------------
    def _selected_status(self):
        status = self.budget_table.selected()
        if status is None:
            self.toast("info", "Önce tablodan bir ekip seçin.")
        return status

    def new_department(self) -> None:
        dlg = DepartmentDialog(self)
        if dlg.exec():
            try:
                self.ctx.repo.add_department(dlg.name.text().strip(), dlg.cost_center.text().strip())
                self.toast("info", f"{dlg.name.text().strip()} departmanı eklendi.")
            except Exception as exc:
                self.toast("critical", "Departman eklenemedi", str(exc)[:200])

    def new_team(self) -> None:
        repo = self.ctx.repo
        dlg = TeamDialog(self, repo.list_departments(), repo.list_services(active_only=True))
        if not dlg.exec():
            return
        try:
            with repo.transaction():
                tid = repo.add_team(dlg.department.currentData(), dlg.name.text().strip())
                repo.open_budget(tid, Decimal(dlg.limit.value()), dlg.warn.value())
                repo.set_team_access(tid, dlg.services.selected())
            self.ctx.engine.invalidate()
            self.toast("info", f"{dlg.name.text().strip()} ekibi oluşturuldu.")
            self.refresh()
        except Exception as exc:
            self.toast("critical", "Ekip oluşturulamadı", str(exc)[:200])

    def edit_budget(self) -> None:
        status = self._selected_status()
        if status is None:
            return
        dlg = BudgetDialog(self, status.team_name, status.credit_limit, status.warn_percent)
        if dlg.exec():
            self.ctx.credit.set_budget(status.team_id, Decimal(str(dlg.limit.value())), dlg.warn.value())
            self.toast("info", f"{status.team_name} bütçesi güncellendi.")
            self.refresh()

    def edit_access(self) -> None:
        status = self._selected_status()
        if status is None:
            return
        repo = self.ctx.repo
        team = next(t for t in repo.list_teams() if t.id == status.team_id)
        granted = {s.id for s in repo.list_team_services(team.id)}
        dlg = AccessDialog(self, team, repo.list_services(active_only=True), granted)
        if dlg.exec():
            repo.set_team_access(team.id, dlg.services.selected())
            self.ctx.engine.invalidate()
            self.toast("info", f"{team.name} servis izinleri kaydedildi.")

    def reset_team(self) -> None:
        status = self._selected_status()
        if status is None:
            return
        answer = QMessageBox.question(
            self, "Dönemi sıfırla",
            f"{status.team_name} ekibinin açık dönemi kapatılıp sıfır harcamayla yeni dönem açılacak.\n"
            "Geçmiş kullanım kayıtları silinmez. Devam edilsin mi?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.ctx.credit.reset_team(status.team_id, "Elle sıfırlama")
            self.refresh()

    def toggle_user(self) -> None:
        user = self.user_table.selected()
        if user is None:
            self.toast("info", "Önce bir kullanıcı seçin.")
            return
        self.ctx.repo.set_user_active(user.id, not user.is_active)
        self.refresh()
