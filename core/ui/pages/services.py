from __future__ import annotations

from decimal import Decimal

from core.ui import format as fmt
from core.ui.context import AppContext
from core.ui.dialogs import PriceDialog, ProviderDialog, ServiceDialog
from core.ui.widgets.common import Card, Page, button, hbox, label
from core.ui.widgets.table import RIGHT, Column, DataTable


class ServicesPage(Page):
    def __init__(self, ctx: AppContext, toast):
        super().__init__("API servisleri", "Kullanılan harici ve dahili servisler, ücretlendirme birimleri ve "
                                           "açık dönemdeki tüketim.")
        self.ctx, self.toast = ctx, toast
        self.actions.addWidget(button("Yeni sağlayıcı", None, self.new_provider))
        self.actions.addWidget(button("Yeni servis", "primary", self.new_service))
        self._shares: dict[int, tuple[Decimal, int]] = {}

        self.table = DataTable(
            [
                Column("Servis", lambda s: s.name, stretch=True),
                Column("Sağlayıcı", lambda s: s.provider_name, width=150),
                Column("Tür", lambda s: "Dahili" if s.provider_kind == "internal" else "Harici", width=80,
                       tone=lambda s: "text_3"),
                Column("Birim", lambda s: s.unit_name, width=90),
                Column("Kredi / birim", lambda s: f"{s.credit_per_unit.normalize():f}".replace(".", ","), RIGHT),
                Column("Dönem çağrısı", lambda s: fmt.number(self._shares.get(s.id, (0, 0))[1]), RIGHT),
                Column("Dönem harcaması", lambda s: fmt.credits(self._shares.get(s.id, (0, 0))[0]), RIGHT),
                Column("Erişen ekip", lambda s: str(self._access.get(s.id, 0)), RIGHT, tone=lambda s: "text_3"),
            ]
        )
        self._access: dict[int, int] = {}
        self.table.doubleClicked.connect(lambda _: self.edit_price())
        card = Card()
        card.body.addLayout(hbox(label("Tutarlar açık bütçe dönemlerindeki başarılı çağrılardan hesaplanır.",
                                       "Faint"), None, button("Fiyatı güncelle", None, self.edit_price)))
        card.body.addWidget(self.table)
        self.content.addWidget(card)

    def refresh(self) -> None:
        repo = self.ctx.repo
        self._shares = {s.service_id: (s.credits, s.calls) for s in repo.service_shares()}
        self._access = repo.service_access_counts()
        self.table.set_rows(repo.list_services())

    def new_provider(self) -> None:
        dlg = ProviderDialog(self)
        if dlg.exec():
            try:
                self.ctx.repo.add_provider(dlg.name.text().strip(), dlg.kind.value())
                self.toast("info", f"{dlg.name.text().strip()} eklendi.")
            except Exception as exc:
                self.toast("critical", "Sağlayıcı eklenemedi", str(exc)[:200])

    def new_service(self) -> None:
        dlg = ServiceDialog(self, self.ctx.repo.list_providers())
        if dlg.exec():
            try:
                self.ctx.repo.add_service(dlg.provider.currentData(), dlg.name.text().strip(),
                                          dlg.unit.currentText().strip(), Decimal(str(dlg.price.value())))
                self.toast("info", f"{dlg.name.text().strip()} servisi eklendi.",
                           "Ekiplerin kullanabilmesi için Ekipler sayfasından izin verin.")
                self.refresh()
            except Exception as exc:
                self.toast("critical", "Servis eklenemedi", str(exc)[:200])

    def edit_price(self) -> None:
        service = self.table.selected()
        if service is None:
            self.toast("info", "Önce bir servis seçin.")
            return
        dlg = PriceDialog(self, service)
        if dlg.exec():
            self.ctx.repo.set_service_price(service.id, Decimal(str(dlg.price.value())))
            self.ctx.engine.invalidate()
            self.refresh()
