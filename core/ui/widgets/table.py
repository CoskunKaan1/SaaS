"""Satır listesinden beslenen genel amaçlı tablo modeli ve görünümü."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from core.ui import theme

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


def tr_upper(text: str) -> str:
    """Türkçe kurallarla büyük harf: i -> İ, ı -> I."""
    return text.replace("i", "İ").replace("ı", "I").upper()


@dataclass
class Column:
    title: str
    value: Callable[[Any], Any]
    align: Qt.AlignmentFlag = LEFT
    tone: Callable[[Any], str | None] | None = None  # palet belirteci: "crit", "warn", "text_3"...
    width: int | None = None
    stretch: bool = False


class RowsModel(QAbstractTableModel):
    def __init__(self, columns: Sequence[Column], key: Callable[[Any], Any] | None = None):
        super().__init__()
        self.columns = list(columns)
        self.rows: list[Any] = []
        self.key = key or (lambda r: getattr(r, "id", id(r)))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return tr_upper(self.columns[section].title)
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(self.columns[section].align)
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = self.columns[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            value = col.value(row)
            return "" if value is None else str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(col.align)
        if role == Qt.ItemDataRole.ForegroundRole and col.tone:
            token = col.tone(row)
            if token:
                return QColor(getattr(theme.current(), token))
        if role == Qt.ItemDataRole.UserRole:
            return row
        return None

    def set_rows(self, rows: Sequence[Any]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()


class DataTable(QTableView):
    """Seçimi yenilemeler arasında koruyan, sade görünümlü tablo."""

    def __init__(self, columns: Sequence[Column], key: Callable[[Any], Any] | None = None):
        super().__init__()
        self.model_ = RowsModel(columns, key)
        self.setModel(self.model_)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(38)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        for i, col in enumerate(columns):
            if col.stretch:
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            elif col.width:
                self.setColumnWidth(i, col.width)
            else:
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

    def set_rows(self, rows: Sequence[Any]) -> None:
        selected = self.selected()
        key = self.model_.key(selected) if selected is not None else None
        scroll = self.verticalScrollBar().value()
        self.model_.set_rows(rows)
        if key is not None:
            for i, row in enumerate(self.model_.rows):
                if self.model_.key(row) == key:
                    self.selectRow(i)
                    break
        self.verticalScrollBar().setValue(scroll)

    def selected(self) -> Any | None:
        indexes = self.selectionModel().selectedRows() if self.selectionModel() else []
        if not indexes:
            return None
        return self.model_.rows[indexes[0].row()] if indexes[0].row() < len(self.model_.rows) else None
