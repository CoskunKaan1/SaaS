"""Uygulamanın başlangıç noktası: bağlantı, şema, örnek veri, pencere."""

from __future__ import annotations

import logging
import sys
from dataclasses import replace

import pyodbc
from PySide6.QtWidgets import QApplication, QDialog

from core import APP_NAME
from core.config import Settings, load_settings, save_settings
from core.connectors.testusers import SimulationEngine
from core.db.connection import DatabaseUnavailable
from core.db.migrate import migrate
from core.db.repository import Repository
from core.db.sqlserver import SqlServerRepository
from core.services.credit_service import CreditService
from core.services.events import EventBus
from core.services.seed import seed_demo_data
from core.ui import theme
from core.ui.context import AppContext

log = logging.getLogger("kredi")


def _create_app() -> QApplication:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("BLM3001")
    app.setStyle("Fusion")  # platform stilinin QSS ile çakışmasını önler
    app.setFont(theme.base_font())
    return app


def _connect(settings: Settings) -> tuple[Settings, Repository] | None:
    """SQL Server'a bağlanır; başaramazsa kullanıcıya bağlantı diyaloğu gösterir."""
    from core.ui.dialogs import ConnectionDialog

    error = ""
    while True:
        if not error:
            try:
                migrate(settings.database)
                repo = SqlServerRepository(settings.database)
                repo.is_empty()  # bağlantıyı gerçekten dene
                return settings, repo
            except (DatabaseUnavailable, pyodbc.Error) as exc:
                error = str(exc)
                log.warning("Veritabanına bağlanılamadı: %s", error)
        dialog = ConnectionDialog(None, settings.database, error)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        settings = replace(settings, database=dialog.result_settings())
        error = ""
        try:
            save_settings(settings)
        except OSError:
            log.warning("config.ini yazılamadı")


def build_context(settings: Settings, repo: Repository) -> AppContext:
    if settings.simulation.seed_demo_data:
        seed_demo_data(repo)
    credit = CreditService(repo, EventBus())
    engine = SimulationEngine(
        credit,
        tick_seconds=settings.simulation.tick_seconds,
        auto_reset_seconds=settings.simulation.auto_reset_seconds,
    )
    return AppContext(settings, repo, credit, engine)


def run(repo: Repository | None = None, settings: Settings | None = None) -> int:
    """Uygulamayı çalıştırır. ``repo`` verilirse SQL Server yerine o kullanılır (testler)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = settings or load_settings()
    app = _create_app()
    theme.set_current(settings.ui.theme)
    app.setStyleSheet(theme.stylesheet(theme.current()))

    if repo is None:
        connected = _connect(settings)
        if connected is None:
            return 1
        settings, repo = connected

    from core.ui.main_window import MainWindow

    ctx = build_context(settings, repo)
    window = MainWindow(ctx)
    window.show()
    if settings.simulation.autostart:
        ctx.engine.start()
    try:
        return app.exec()
    finally:
        ctx.engine.stop()
        repo.close()
