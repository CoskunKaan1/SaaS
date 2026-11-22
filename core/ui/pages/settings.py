from __future__ import annotations

from dataclasses import replace

from core import __version__
from core.config import save_settings
from core.db.connection import detect_driver
from core.ui.context import AppContext
from core.ui.widgets.common import Card, Page, Segmented, hbox, label


class SettingsPage(Page):
    def __init__(self, ctx: AppContext, on_theme):
        super().__init__("Ayarlar")
        self.ctx, self.on_theme = ctx, on_theme

        appearance = Card("Görünüm")
        self.theme = Segmented([("Açık", "light"), ("Koyu", "dark")], ctx.settings.ui.theme)
        self.theme.changed.connect(self._theme)
        appearance.body.addLayout(hbox(label("Tema", "Muted"), None, self.theme))
        self.content.addWidget(appearance)

        db = ctx.settings.database
        try:
            driver = detect_driver(db.driver)
        except Exception as exc:  # noqa: BLE001
            driver = f"bulunamadı ({exc})"
        conn = Card("Veritabanı", "Bağlantı ayarları proje kökündeki config.ini dosyasında tutulur.")
        for key, value in (
            ("Sunucu", db.server),
            ("Veritabanı", db.database),
            ("Kimlik doğrulama", "Windows" if db.trusted_connection else f"SQL ({db.username})"),
            ("ODBC sürücüsü", driver),
            ("Depo", type(ctx.repo).__name__),
        ):
            conn.body.addLayout(hbox(label(key, "Muted"), None, label(value)))
        self.content.addWidget(conn)

        about = Card("Hakkında")
        about.body.addWidget(label(
            f"Kredi Takip {__version__} · Şirket içi API kredi takip sistemi. "
            "BLM3001 Veritabanı Yönetim Sistemleri dersi projesi.", "Muted", wrap=True))
        self.content.addWidget(about)
        self.content.addStretch(1)

    def _theme(self, name) -> None:
        settings = self.ctx.settings
        self.ctx.settings = replace(settings, ui=replace(settings.ui, theme=name))
        try:
            save_settings(self.ctx.settings)
        except OSError:
            pass
        self.on_theme(name)
