"""QPainter ile çizilen sade grafikler.

Hazır grafik kütüphanesi yerine elle çizim tercih edildi: hem tema
renkleriyle birebir uyum sağlıyor hem de gereksiz süsleme (gölge, 3B,
lejant kutusu) olmadan yalnızca okunması gereken şeyi gösteriyor.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from core.models import BudgetStatus, ServiceShare, Severity, TimePoint
from core.ui import format as fmt
from core.ui import theme


def _nice_max(value: float) -> float:
    if value <= 0:
        return 10.0
    exp = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * exp:
            return step * exp
    return 10 * exp


def _small_font(base: QFont, px: int = 11, bold: bool = False) -> QFont:
    f = QFont(base)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


class AreaChart(QWidget):
    """Son N dakikanın dakikalık harcaması. Fareyle üzerine gelince değer gösterir."""

    def __init__(self, minutes: int = 30):
        super().__init__()
        self.minutes = minutes
        self.points: list[tuple[datetime, float, int]] = []
        self.hover: int | None = None
        self.setMouseTracking(True)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, series: list[TimePoint]) -> None:
        now = datetime.now().replace(second=0, microsecond=0)
        start = now - timedelta(minutes=self.minutes - 1)
        by_bucket = {p.bucket.replace(second=0, microsecond=0): p for p in series}
        self.points = []
        for i in range(self.minutes):
            b = start + timedelta(minutes=i)
            p = by_bucket.get(b)
            self.points.append((b, float(p.credits) if p else 0.0, p.calls if p else 0))
        self.update()

    def _plot_rect(self) -> QRectF:
        return QRectF(44, 10, self.width() - 56, self.height() - 38)

    def paintEvent(self, _):
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()
        font = _small_font(self.font())
        painter.setFont(font)
        fm = QFontMetrics(font)

        values = [v for _, v, _ in self.points] or [0.0]
        top = _nice_max(max(values) * 1.1)

        # yatay kılavuz çizgileri ve eksen etiketleri
        for i in range(5):
            y = rect.bottom() - rect.height() * i / 4
            painter.setPen(QPen(p.q("border"), 1, Qt.PenStyle.SolidLine if i == 0 else Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(p.q("text_3"))
            text = fmt.compact(top * i / 4)
            painter.drawText(QRectF(0, y - 8, rect.left() - 8, 16),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)

        if not self.points:
            painter.end()
            return

        n = len(self.points)
        step = rect.width() / max(1, n - 1)

        def xy(i: int, v: float) -> QPointF:
            return QPointF(rect.left() + i * step, rect.bottom() - rect.height() * (v / top))

        line = QPainterPath(xy(0, self.points[0][1]))
        for i in range(1, n):
            line.lineTo(xy(i, self.points[i][1]))
        area = QPainterPath(line)
        area.lineTo(QPointF(rect.right(), rect.bottom()))
        area.lineTo(QPointF(rect.left(), rect.bottom()))
        area.closeSubpath()

        grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
        grad.setColorAt(0, p.q("accent", 70))
        grad.setColorAt(1, p.q("accent", 0))
        painter.fillPath(area, grad)
        painter.setPen(QPen(p.q("accent"), 2))
        painter.drawPath(line)

        # zaman etiketleri: baş, orta, son
        painter.setPen(p.q("text_3"))
        for i in (0, n // 2, n - 1):
            x = rect.left() + i * step
            text = "şimdi" if i == n - 1 else fmt.clock(self.points[i][0], seconds=False)
            w = fm.horizontalAdvance(text)
            x = min(max(x - w / 2, rect.left()), rect.right() - w)
            painter.drawText(QPointF(x, rect.bottom() + 18), text)

        if self.hover is not None and 0 <= self.hover < n:
            pt = xy(self.hover, self.points[self.hover][1])
            painter.setPen(QPen(p.q("border_strong"), 1))
            painter.drawLine(QPointF(pt.x(), rect.top()), QPointF(pt.x(), rect.bottom()))
            painter.setPen(QPen(p.q("surface"), 2))
            painter.setBrush(p.q("accent"))
            painter.drawEllipse(pt, 4.5, 4.5)
        painter.end()

    def mouseMoveEvent(self, event):
        rect = self._plot_rect()
        if not self.points or not rect.adjusted(-6, 0, 6, 0).contains(event.position()):
            self.leaveEvent(None)
            return
        step = rect.width() / max(1, len(self.points) - 1)
        idx = round((event.position().x() - rect.left()) / step)
        idx = max(0, min(len(self.points) - 1, idx))
        if idx != self.hover:
            self.hover = idx
            bucket, value, calls = self.points[idx]
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{fmt.clock(bucket, False)}  ·  {fmt.credits(value)} kredi  ·  {calls} çağrı",
                self,
            )
            self.update()

    def leaveEvent(self, _):
        if self.hover is not None:
            self.hover = None
            QToolTip.hideText()
            self.update()


class ShareBars(QWidget):
    """Servislere göre harcama: tek renk yatay çubuklar, değer sağda."""

    ROW = 34

    def __init__(self, max_rows: int = 6):
        super().__init__()
        self.max_rows = max_rows
        self.rows: list[ServiceShare] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_data(self, rows: list[ServiceShare]) -> None:
        self.rows = rows[: self.max_rows]
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(300, max(1, self.max_rows) * self.ROW)

    def minimumSizeHint(self) -> QSize:
        return QSize(200, self.max_rows * self.ROW)

    def paintEvent(self, _):
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        if not self.rows:
            painter.setPen(p.q("text_3"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Bu dönem henüz harcama yok")
            painter.end()
            return
        total = sum(float(r.credits) for r in self.rows) or 1.0
        top = max(float(r.credits) for r in self.rows) or 1.0
        label_font = _small_font(self.font(), 12)
        value_font = _small_font(self.font(), 12, bold=True)
        for i, row in enumerate(self.rows):
            y = i * self.ROW
            painter.setFont(label_font)
            painter.setPen(p.q("text"))
            painter.drawText(QRectF(0, y, w * 0.6, 16), Qt.AlignmentFlag.AlignLeft, row.service_name)
            painter.setFont(value_font)
            share = float(row.credits) / total
            painter.drawText(QRectF(0, y, w, 16), Qt.AlignmentFlag.AlignRight,
                             f"{fmt.credits(row.credits)}  ·  {fmt.percent(share)}")
            track = QRectF(0, y + 20, w, 6)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(p.q("track"))
            painter.drawRoundedRect(track, 3, 3)
            fill = QRectF(track.left(), track.top(), max(4.0, w * float(row.credits) / top), track.height())
            painter.setBrush(p.q("accent"))
            painter.drawRoundedRect(fill, 3, 3)
        painter.end()


class BudgetList(QWidget):
    """Ekip bütçeleri: ad, dolum çubuğu, uyarı eşiği işareti ve kalan kredi."""

    ROW = 54

    def __init__(self):
        super().__init__()
        self.rows: list[BudgetStatus] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, rows: list[BudgetStatus]) -> None:
        self.rows = sorted(rows, key=lambda r: r.ratio, reverse=True)
        self.setFixedHeight(max(1, len(self.rows)) * self.ROW)
        self.update()

    def paintEvent(self, _):
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        name_font = _small_font(self.font(), 13, bold=True)
        sub_font = _small_font(self.font(), 12)
        value_font = _small_font(self.font(), 13, bold=True)
        left_w = min(220.0, w * 0.28)
        right_w = 170.0
        bar_left = left_w + 16
        bar_w = max(40.0, w - bar_left - right_w - 16)

        for i, row in enumerate(self.rows):
            y = i * self.ROW
            if i:
                painter.setPen(QPen(p.q("border"), 1))
                painter.drawLine(QPointF(0, y), QPointF(w, y))
            color = {Severity.CRITICAL: "crit", Severity.WARNING: "warn"}.get(row.state, "accent")

            painter.setFont(name_font)
            painter.setPen(p.q("text"))
            painter.drawText(QRectF(0, y + 9, left_w, 18), Qt.AlignmentFlag.AlignLeft, row.team_name)
            painter.setFont(sub_font)
            painter.setPen(p.q("text_3"))
            painter.drawText(QRectF(0, y + 28, left_w, 16), Qt.AlignmentFlag.AlignLeft, row.department_name)

            track = QRectF(bar_left, y + self.ROW / 2 - 4, bar_w, 8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(p.q("track"))
            painter.drawRoundedRect(track, 4, 4)
            ratio = min(1.0, row.ratio)
            if ratio > 0:
                painter.setBrush(p.q(color))
                painter.drawRoundedRect(QRectF(track.left(), track.top(), max(8.0, bar_w * ratio), 8), 4, 4)
            # uyarı eşiği işareti
            wx = track.left() + bar_w * row.warn_percent / 100
            painter.setPen(QPen(p.q("text_3"), 1.5))
            painter.drawLine(QPointF(wx, track.top() - 4), QPointF(wx, track.bottom() + 4))

            painter.setFont(value_font)
            painter.setPen(p.q(color) if color != "accent" else p.q("text"))
            painter.drawText(QRectF(w - right_w, y + 9, right_w, 18), Qt.AlignmentFlag.AlignRight,
                             fmt.percent(row.ratio))
            painter.setFont(sub_font)
            painter.setPen(p.q("text_3"))
            painter.drawText(QRectF(w - right_w, y + 28, right_w, 16), Qt.AlignmentFlag.AlignRight,
                             f"{fmt.credits(row.spent)} / {fmt.credits(row.credit_limit)}")
        painter.end()


class MiniBar(QWidget):
    """Tablo dışı tek satırlık kullanım çubuğu."""

    def __init__(self, ratio: float = 0.0, warn: int = 80):
        super().__init__()
        self.ratio, self.warn = ratio, warn
        self.setFixedHeight(8)

    def set(self, ratio: float, warn: int) -> None:
        self.ratio, self.warn = ratio, warn
        self.update()

    def paintEvent(self, _):
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(p.q("track"))
        painter.drawRoundedRect(QRectF(self.rect()), 4, 4)
        token = "crit" if self.ratio >= 1 else "warn" if self.ratio * 100 >= self.warn else "accent"
        painter.setBrush(p.q(token))
        painter.drawRoundedRect(QRectF(0, 0, self.width() * min(1.0, self.ratio), self.height()), 4, 4)
        painter.end()


__all__ = ["AreaChart", "BudgetList", "MiniBar", "ShareBars"]
