from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QGridLayout, QScrollArea, QVBoxLayout, QWidget

from core.models import Severity
from core.ui import format as fmt
from core.ui.context import AppContext
from core.ui.widgets.charts import AreaChart, BudgetList, ShareBars
from core.ui.widgets.common import Card, KpiCard, Page, label


class OverviewPage(Page):
    def __init__(self, ctx: AppContext):
        super().__init__("Genel bakış", "Açık bütçe dönemlerinin anlık durumu. Veriler birkaç saniyede bir yenilenir.")
        self.ctx = ctx

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 4, 0)
        col.setSpacing(16)

        kpis = QGridLayout()
        kpis.setSpacing(16)
        self.k_spent = KpiCard("Harcanan kredi")
        self.k_left = KpiCard("Kalan kredi")
        self.k_calls = KpiCard("Başarılı çağrı")
        self.k_risk = KpiCard("Limite yakın ekip")
        for i, card in enumerate((self.k_spent, self.k_left, self.k_calls, self.k_risk)):
            kpis.addWidget(card, 0, i)
        col.addLayout(kpis)

        charts = QGridLayout()
        charts.setSpacing(16)
        self.area_card = Card("Dakikalık harcama", "Son 30 dakika, başarılı çağrıların kredisi")
        self.area = AreaChart(30)
        self.area_card.body.addWidget(self.area)
        self.share_card = Card("Servis dağılımı", "Açık dönemde en çok kredi harcanan servisler")
        self.shares = ShareBars(6)
        self.share_card.body.addWidget(self.shares)
        self.share_card.body.addStretch(1)
        charts.addWidget(self.area_card, 0, 0)
        charts.addWidget(self.share_card, 0, 1)
        charts.setColumnStretch(0, 3)
        charts.setColumnStretch(1, 2)
        col.addLayout(charts)

        self.budget_card = Card("Ekip bütçeleri", "Doluluğa göre sıralı. Çubuktaki ince çizgi uyarı eşiğini gösterir.")
        self.budgets = BudgetList()
        self.budget_card.body.addWidget(self.budgets)
        self.empty = label("Henüz ekip yok. Ekipler sayfasından ekip ve bütçe tanımlayın.", "Muted")
        self.budget_card.body.addWidget(self.empty)
        col.addWidget(self.budget_card)
        col.addStretch(1)

        scroll.setWidget(inner)
        self.content.addWidget(scroll)

    def refresh(self) -> None:
        repo = self.ctx.repo
        statuses = repo.budget_statuses()
        limit = sum((s.credit_limit for s in statuses), Decimal(0))
        spent = sum((s.spent for s in statuses), Decimal(0))
        shares = repo.service_shares()
        # s.calls hatalı çağrıları da içerir; başarılı sayısı servis dağılımından gelir.
        calls = sum(s.calls for s in shares)
        rejected = sum(s.rejected for s in statuses)
        warn = [s for s in statuses if s.state is Severity.WARNING]
        full = [s for s in statuses if s.state is Severity.CRITICAL]

        self.k_spent.set(fmt.credits(spent), f"Toplam limitin kullanımı {fmt.percent(float(spent / limit) if limit else 0)}")
        self.k_left.set(fmt.credits(max(Decimal(0), limit - spent)), f"{len(statuses)} ekip, {fmt.credits(limit)} limit")
        self.k_calls.set(fmt.number(calls), f"{fmt.number(rejected)} çağrı limit nedeniyle reddedildi"
                         if rejected else "Reddedilen çağrı yok")
        risk = len(warn) + len(full)
        self.k_risk.set(str(risk), f"{len(full)} ekipte kredi yetmiyor" if full else
                        ("Uyarı eşiğini geçen ekipler" if warn else "Tüm ekipler eşiğin altında"))

        self.area.set_data(repo.timeseries(30))
        self.shares.set_data(shares)
        self.budgets.set_data(statuses)
        self.budgets.setVisible(bool(statuses))
        self.empty.setVisible(not statuses)
