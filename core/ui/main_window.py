from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from core import APP_NAME
from core.services.events import Event
from core.ui import theme
from core.ui.bridge import EventBridge
from core.ui.context import AppContext
from core.ui.pages.notifications import NotificationsPage
from core.ui.pages.overview import OverviewPage
from core.ui.pages.services import ServicesPage
from core.ui.pages.settings import SettingsPage
from core.ui.pages.simulator import SimulatorPage
from core.ui.pages.teams import TeamsPage
from core.ui.pages.usage import UsagePage
from core.ui.widgets.common import label
from core.ui.widgets.toast import ToastHost

REFRESH_MS = 2000


def app_icon(color: str = "#1E6B5A") -> QIcon:
    """Basit marka işareti: içinde dolum çubuğu olan yuvarlatılmış kare."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)
        p.setBrush(QColor(255, 255, 255, 80))
        bar = QRectF(size * 0.2, size * 0.58, size * 0.6, size * 0.14)
        p.drawRoundedRect(bar, bar.height() / 2, bar.height() / 2)
        p.setBrush(QColor("white"))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * 0.62, bar.height()),
                          bar.height() / 2, bar.height() / 2)
        p.drawRoundedRect(QRectF(size * 0.2, size * 0.28, size * 0.14, size * 0.14), size * 0.04, size * 0.04)
        p.end()
        icon.addPixmap(pm)
    return icon


class NavButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.badge = QLabel(self)
        self.badge.setObjectName("NavBadge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.hide()

    def set_badge(self, count: int) -> None:
        if count <= 0:
            self.badge.hide()
            return
        self.badge.setText(str(count) if count < 100 else "99+")
        self.badge.adjustSize()
        self.badge.move(self.width() - self.badge.width() - 10, (self.height() - self.badge.height()) // 2)
        self.badge.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.badge.isVisible():
            self.badge.move(self.width() - self.badge.width() - 10, (self.height() - self.badge.height()) // 2)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1360, 860)
        self.setMinimumSize(1080, 680)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.toasts = ToastHost(root)
        self.pages = QStackedWidget()
        self.overview = OverviewPage(ctx)
        self.teams = TeamsPage(ctx, self.toast)
        self.services = ServicesPage(ctx, self.toast)
        self.usage = UsagePage(ctx)
        self.notifications = NotificationsPage(ctx, self._refresh_badge)
        self.simulator = SimulatorPage(ctx, self.toast)
        self.settings_page = SettingsPage(ctx, self.apply_theme)

        lay.addWidget(self._build_sidebar())
        lay.addWidget(self.pages, 1)

        self.bridge = EventBridge(ctx.bus, self)
        self.bridge.event.connect(self._on_event)

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
            self.tray.messageClicked.connect(lambda: (self.showNormal(), self.activateWindow(),
                                                      self.go(self.notifications)))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_current)
        self.timer.start(REFRESH_MS)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self._tick)
        self.clock.start(1000)
        self._dirty = True
        self.go(self.overview)
        self._refresh_badge()

    # --- yapı ------------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(232)
        col = QVBoxLayout(side)
        col.setContentsMargins(14, 20, 14, 16)
        col.setSpacing(2)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(app_icon(theme.current().accent).pixmap(28, 28))
        self._brand_mark = mark
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label(APP_NAME, "Brand"))
        names.addWidget(label("API kredi yönetimi", "BrandSub"))
        brand.addWidget(mark)
        brand.addLayout(names, 1)
        col.addLayout(brand)
        col.addSpacing(22)

        self.nav_group = QButtonGroup(self)
        self.nav: dict[QWidget, NavButton] = {}
        sections = [
            ("İZLEME", [("Genel bakış", self.overview), ("Kullanım kayıtları", self.usage),
                        ("Bildirimler", self.notifications)]),
            ("YÖNETİM", [("Ekipler ve bütçeler", self.teams), ("API servisleri", self.services)]),
            ("GELİŞTİRİCİ", [("Test paneli", self.simulator), ("Ayarlar", self.settings_page)]),
        ]
        for title, items in sections:
            head = label(title, "Faint")
            head.setContentsMargins(12, 14, 0, 6)
            head.setStyleSheet("font-size: 10px; font-weight: 600; letter-spacing: 0.6px;")
            col.addWidget(head)
            for text, page in items:
                btn = NavButton(text)
                btn.clicked.connect(lambda _=False, p=page: self.go(p))
                self.nav_group.addButton(btn)
                self.nav[page] = btn
                self.pages.addWidget(page)
                col.addWidget(btn)
        col.addStretch(1)

        self.sim_status = label("", "SidebarFooter", wrap=True)
        db = self.ctx.settings.database
        col.addWidget(self.sim_status)
        col.addSpacing(4)
        col.addWidget(label(f"{db.server} · {db.database}", "SidebarFooter", wrap=True))
        return side

    # --- gezinme ve yenileme ----------------------------------------------
    def go(self, page) -> None:
        self.pages.setCurrentWidget(page)
        self.nav[page].setChecked(True)
        self._safe_refresh(page)

    def refresh_current(self) -> None:
        if self.isMinimized():
            return
        page = self.pages.currentWidget()
        if page is self.simulator and not self._dirty:
            return  # test paneli olay geldikçe yenilenir; tabloyu boşuna sıfırlamayalım
        self._dirty = False
        self._safe_refresh(page)
        self._refresh_badge()

    def _safe_refresh(self, page) -> None:
        try:
            page.refresh()
        except Exception as exc:  # noqa: BLE001 - bağlantı kopması vb. arayüzü düşürmesin
            self.toast("critical", "Veri yenilenemedi", str(exc)[:240])
            self.timer.setInterval(10_000)
        else:
            if self.timer.interval() != REFRESH_MS:
                self.timer.setInterval(REFRESH_MS)

    def _tick(self) -> None:
        engine = self.ctx.engine
        self.sim_status.setText(f"Simülasyon çalışıyor · {engine.active_agents} sanal kullanıcı" if engine.running
                                else "Simülasyon durduruldu")
        if self.pages.currentWidget() is self.simulator:
            self.simulator.tick()

    def _refresh_badge(self) -> None:
        try:
            self.nav[self.notifications].set_badge(self.ctx.repo.unread_count())
        except Exception:  # noqa: BLE001
            pass

    # --- olaylar --------------------------------------------------------------
    def _on_event(self, event: Event) -> None:
        self.simulator.on_event(event)
        p = event.payload
        if event.kind == "notification":
            self.toast(p["severity"], p["title"], p["body"])
            self._refresh_badge()
            if p["severity"] == "critical" and not self.isActiveWindow() and self.tray.isVisible():
                self.tray.showMessage(p["title"], p["body"], QSystemTrayIcon.MessageIcon.Warning, 6000)
        elif event.kind == "simulation" and p.get("state") == "warning":
            self.toast("warning", "Simülasyon uyarısı", p.get("message", ""))
        elif event.kind in ("reset", "budget"):
            self._dirty = True
        if event.kind == "simulation":
            self._dirty = True

    def toast(self, severity: str, title: str, body: str = "") -> None:
        self.toasts.show(severity, title, body)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.toasts.layout()

    def apply_theme(self, name: str) -> None:
        palette = theme.set_current(name)
        QApplication.instance().setStyleSheet(theme.stylesheet(palette))
        self._brand_mark.setPixmap(app_icon(palette.accent).pixmap(28, 28))
        for w in self.findChildren(QWidget):
            w.update()

    def closeEvent(self, event):
        self.timer.stop()
        self.clock.stop()
        self.ctx.engine.stop()
        self.bridge.detach()
        self.tray.hide()
        super().closeEvent(event)
