"""Arayüzün ekran olmadan (offscreen) kurulup her sayfanın yenilenebildiğini doğrular."""

from __future__ import annotations

import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.app import build_context  # noqa: E402
from core.config import Settings  # noqa: E402
from core.models import Severity  # noqa: E402
from core.ui import format as fmt  # noqa: E402
from core.ui import theme  # noqa: E402
from core.ui.widgets.table import tr_upper  # noqa: E402


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyleSheet(theme.stylesheet(theme.LIGHT))
    return instance


@pytest.fixture
def window(app, repo):
    from core.ui.main_window import MainWindow

    ctx = build_context(Settings(), repo)
    ctx.engine.rng = random.Random(3)
    ctx.engine.tick_seconds = 10
    for _ in range(20):
        ctx.engine.step()
    w = MainWindow(ctx)
    w.resize(1300, 800)
    w.show()
    yield w
    w.close()


def test_every_page_refreshes(window):
    for page in (window.overview, window.teams, window.services, window.usage, window.notifications,
                 window.simulator, window.settings_page):
        window.go(page)
        assert window.pages.currentWidget() is page
    assert window.usage.table.model_.rowCount() > 0
    assert window.simulator.table.model_.rowCount() >= 5


def test_notification_event_shows_toast_and_badge(window, app):
    window.ctx.credit.notify(Severity.CRITICAL, "Deneme", "gövde")
    app.processEvents()
    assert window.toasts.toasts
    assert window.nav[window.notifications].badge.isVisible()


def test_create_test_user_from_panel(window):
    page = window.simulator
    page.create_user()  # ekip listesi henüz yüklenmeden: anlaşılır uyarı
    assert "ekip seçin" in page.c_result.text()
    window.go(page)
    page.c_name.setText("panel-bot")
    page.create_user()
    assert "oluşturuldu" in page.c_result.text()
    assert any(p.user_name == "panel-bot" for p in window.ctx.repo.list_profiles())


def test_success_card_excludes_failed_calls(window):
    repo = window.ctx.repo
    profile = repo.list_profiles()[0]
    service = repo.list_team_services(profile.team_id)[0]
    window.ctx.credit.charge(profile.user_id, service.id, 1, 500)
    shown = []
    window.overview.k_calls.set = lambda value, hint: shown.append(value)
    window.overview.refresh()
    assert shown == [fmt.number(sum(s.calls for s in repo.service_shares()))]


def test_theme_switch(window):
    window.apply_theme("dark")
    assert theme.current().name == "dark"
    window.apply_theme("light")


def test_turkish_formatting():
    assert fmt.number(1234567.5, 2) == "1.234.567,50"
    assert fmt.percent(0.825) == "%82"
    assert tr_upper("Ekip dönem başı") == "EKİP DÖNEM BAŞI"
    assert fmt.duration(None) == "kapalı" and fmt.duration(125) == "02:05"
