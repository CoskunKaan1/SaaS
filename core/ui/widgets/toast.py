"""Sağ altta beliren, kendiliğinden kapanan bildirim kartları."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.ui import theme

_TONE = {"critical": "crit", "warning": "warn", "info": "accent"}


class _Stripe(QWidget):
    def __init__(self, tone: str):
        super().__init__()
        self.tone = tone
        self.setFixedWidth(4)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.current().q(self.tone))
        painter.drawRoundedRect(QRectF(self.rect()), 2, 2)
        painter.end()


class Toast(QFrame):
    WIDTH = 340

    def __init__(self, parent: QWidget, severity: str, title: str, body: str, timeout_ms: int):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setFixedWidth(self.WIDTH)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 12, 14, 12)
        lay.setSpacing(12)
        lay.addWidget(_Stripe(_TONE.get(severity, "accent")))
        texts = QVBoxLayout()
        texts.setSpacing(3)
        t = QLabel(title)
        t.setObjectName("ToastTitle")
        t.setWordWrap(True)
        b = QLabel(body)
        b.setObjectName("ToastBody")
        b.setWordWrap(True)
        texts.addWidget(t)
        if body:
            texts.addWidget(b)
        lay.addLayout(texts, 1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Kapatmak için tıklayın")

        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.fade = QPropertyAnimation(self.effect, b"opacity", self)
        self.fade.setDuration(180)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)
        self.fade.start()
        QTimer.singleShot(timeout_ms, self.dismiss)
        self._closing = False

    def mousePressEvent(self, _):
        self.dismiss()

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.fade.stop()
        self.fade.setStartValue(self.effect.opacity())
        self.fade.setEndValue(0.0)
        self.fade.finished.connect(self._remove)
        self.fade.start()

    def _remove(self) -> None:
        host = self.parent()
        self.deleteLater()
        if isinstance(host, QWidget) and hasattr(host, "_toast_host"):
            host._toast_host.forget(self)


class ToastHost:
    """Ana pencerenin içinde, sağ alta yığılan kartları yönetir."""

    MAX = 4
    MARGIN = 20

    def __init__(self, window: QWidget):
        self.window = window
        window._toast_host = self  # type: ignore[attr-defined]
        self.toasts: list[Toast] = []

    def show(self, severity: str, title: str, body: str = "", timeout_ms: int = 6000) -> None:
        toast = Toast(self.window, severity, title, body, timeout_ms)
        toast.adjustSize()
        toast.show()
        toast.raise_()
        self.toasts.append(toast)
        while len(self.toasts) > self.MAX:
            self.toasts.pop(0).dismiss()
        self.layout()

    def forget(self, toast: Toast) -> None:
        if toast in self.toasts:
            self.toasts.remove(toast)
        self.layout()

    def layout(self) -> None:
        y = self.window.height() - self.MARGIN
        for toast in reversed(self.toasts):
            toast.adjustSize()
            y -= toast.height()
            toast.move(self.window.width() - toast.width() - self.MARGIN, y)
            y -= 10
