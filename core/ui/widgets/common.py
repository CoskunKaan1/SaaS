"""Sayfalarda tekrar eden küçük yapı taşları."""

from __future__ import annotations

from typing import Callable, Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def button(text: str, variant: str | None = None, on_click: Callable | None = None,
           tooltip: str | None = None) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if variant:
        btn.setProperty("variant", variant)
    if on_click:
        btn.clicked.connect(lambda _=False: on_click())
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


def hbox(*items, spacing: int = 8, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for item in items:
        if item is None:
            lay.addStretch(1)
        elif isinstance(item, int):
            lay.addSpacing(item)
        elif isinstance(item, QWidget):
            lay.addWidget(item)
        else:
            lay.addLayout(item)
    return lay


class Card(QFrame):
    """Kenarlıklı yüzey; isteğe bağlı başlık ve sağ üst eylem alanı."""

    def __init__(self, title: str | None = None, hint: str | None = None, padding: int = 18):
        super().__init__()
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding - 2, padding, padding)
        self.body.setSpacing(12)
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(6)
        if title:
            titles = QVBoxLayout()
            titles.setSpacing(2)
            titles.addWidget(label(title, "SectionTitle"))
            if hint:
                self.hint = label(hint, "SectionHint", wrap=True)
                titles.addWidget(self.hint)
            head = QHBoxLayout()
            head.addLayout(titles, 1)
            head.addLayout(self.header_actions)
            self.body.addLayout(head)


class KpiCard(Card):
    def __init__(self, title: str):
        super().__init__(padding=16)
        self.body.setSpacing(4)
        self.title = label(title, "KpiLabel")
        self.value = label("—", "KpiValue")
        self.caption = label("", "KpiCaption")
        self.body.addWidget(self.title)
        self.body.addWidget(self.value)
        self.body.addWidget(self.caption)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set(self, value: str, caption: str = "") -> None:
        self.value.setText(value)
        self.caption.setText(caption)


class Pill(QLabel):
    def __init__(self, text: str = "", tone: str = "neutral"):
        super().__init__(text)
        self.setObjectName("Pill")
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


class Segmented(QFrame):
    """Birbirini dışlayan küçük seçenek grubu (iOS benzeri bölmeli seçici)."""

    changed = Signal(object)

    def __init__(self, options: Iterable[tuple[str, object]], current: object | None = None):
        super().__init__()
        self.setObjectName("Segmented")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._values: dict[int, object] = {}
        for i, (text, value) in enumerate(options):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(btn, i)
            self._values[i] = value
            lay.addWidget(btn)
            if value == current or (current is None and i == 0):
                btn.setChecked(True)
        self.group.idClicked.connect(lambda i: self.changed.emit(self._values[i]))

    def value(self) -> object:
        return self._values[self.group.checkedId()]

    def set_value(self, value: object) -> None:
        for i, v in self._values.items():
            if v == value:
                self.group.button(i).setChecked(True)


class Page(QWidget):
    """Başlık + alt başlık + sağda eylemler; altında içerik."""

    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 26, 32, 26)
        outer.setSpacing(20)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(label(title, "PageTitle"))
        self.subtitle = label(subtitle, "PageSubtitle", wrap=True)
        if subtitle:
            titles.addWidget(self.subtitle)
        head.addLayout(titles, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        head.addLayout(self.actions)
        outer.addLayout(head)
        self.content = QVBoxLayout()
        self.content.setSpacing(16)
        outer.addLayout(self.content, 1)

    def refresh(self) -> None:  # alt sınıflar doldurur
        pass
