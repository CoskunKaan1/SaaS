"""Renk belirteçleri ve Qt stil sayfası.

Tüm renkler tek bir ``Palette`` içinde tanımlanır; hem QSS hem de elle
çizilen grafikler buradan okur. Böylece açık/koyu tema geçişi tek noktadan
yapılır ve arayüzde rastgele renk kullanılmaz.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    surface: str
    surface_2: str
    sidebar: str
    border: str
    border_strong: str
    text: str
    text_2: str
    text_3: str
    accent: str
    accent_hover: str
    accent_soft: str
    on_accent: str
    warn: str
    warn_soft: str
    crit: str
    crit_soft: str
    ok: str
    track: str

    def q(self, token: str, alpha: int | None = None) -> QColor:
        color = QColor(getattr(self, token))
        if alpha is not None:
            color.setAlpha(alpha)
        return color


LIGHT = Palette(
    name="light",
    bg="#F6F5F2",
    surface="#FFFFFF",
    surface_2="#FAF9F7",
    sidebar="#EFEEEA",
    border="#E5E3DD",
    border_strong="#D2CFC7",
    text="#1D1D1B",
    text_2="#5C5B56",
    text_3="#8B8981",
    accent="#1E6B5A",
    accent_hover="#185A4B",
    accent_soft="#E2EFEA",
    on_accent="#FFFFFF",
    warn="#A8650F",
    warn_soft="#FAEFDC",
    crit="#B3261E",
    crit_soft="#FBE7E5",
    ok="#2E7D4F",
    track="#EDEBE6",
)

DARK = Palette(
    name="dark",
    bg="#131312",
    surface="#1B1B1A",
    surface_2="#212120",
    sidebar="#171716",
    border="#2B2B29",
    border_strong="#3A3A37",
    text="#ECEBE6",
    text_2="#A9A79F",
    text_3="#77756E",
    accent="#5BB59D",
    accent_hover="#6FC4AC",
    accent_soft="#1C332D",
    on_accent="#0F1F1A",
    warn="#E2A64B",
    warn_soft="#33281A",
    crit="#EE7466",
    crit_soft="#3A1F1C",
    ok="#6CC08A",
    track="#2A2A28",
)

_current: Palette = LIGHT


def current() -> Palette:
    return _current


def set_current(name: str) -> Palette:
    global _current
    _current = DARK if name == "dark" else LIGHT
    return _current


def base_font() -> QFont:
    families = set(QFontDatabase.families())
    for family in ("Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", "Arial"):
        if family in families:
            font = QFont(family, 10)
            break
    else:
        font = QFont()
        font.setPointSize(10)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def _icons(p: Palette) -> dict[str, str]:
    """QSS yalnızca dosya yolundan simge okuyabildiği için, palete göre
    renklendirilmiş küçük SVG'leri geçici klasöre yazar."""
    folder = Path(tempfile.gettempdir()) / "kredi_takip_icons" / p.name
    folder.mkdir(parents=True, exist_ok=True)
    svgs = {
        "check": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7" '
                 f'fill="none" stroke="{p.on_accent}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "chevron": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M4 6l4 4 4-4" '
                   f'fill="none" stroke="{p.text_2}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    }
    paths = {}
    for name, svg in svgs.items():
        path = folder / f"{name}.svg"
        if not path.exists() or path.read_text(encoding="utf-8") != svg:
            path.write_text(svg, encoding="utf-8")
        paths[name] = path.as_posix()
    return paths


def stylesheet(p: Palette) -> str:
    icons = _icons(p)
    return f"""
* {{ outline: none; }}
QWidget {{ color: {p.text}; font-size: 13px; }}
QMainWindow, #Root {{ background: {p.bg}; }}
QToolTip {{ background: {p.text}; color: {p.surface}; border: none; padding: 6px 8px; border-radius: 6px; }}

/* --- kenar çubuğu --- */
#Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
#Brand {{ font-size: 15px; font-weight: 600; color: {p.text}; }}
#BrandSub {{ font-size: 11px; color: {p.text_3}; }}
#NavButton {{
    text-align: left; padding: 8px 12px; border: none; border-radius: 7px;
    color: {p.text_2}; background: transparent; font-size: 13px;
}}
#NavButton:hover {{ background: {p.surface_2}; color: {p.text}; }}
#NavButton:checked {{ background: {p.surface}; color: {p.text}; font-weight: 600; border: 1px solid {p.border}; }}
#NavBadge {{
    background: {p.crit}; color: white; border-radius: 8px; padding: 0 6px;
    font-size: 11px; font-weight: 600; min-height: 16px;
}}
#SidebarFooter {{ color: {p.text_3}; font-size: 11px; }}

/* --- sayfa --- */
#PageTitle {{ font-size: 22px; font-weight: 600; }}
#PageSubtitle {{ color: {p.text_2}; font-size: 13px; }}
#SectionTitle {{ font-size: 13px; font-weight: 600; color: {p.text}; }}
#SectionHint {{ font-size: 12px; color: {p.text_3}; }}
#Muted {{ color: {p.text_2}; }}
#Faint {{ color: {p.text_3}; font-size: 12px; }}
#Mono {{ font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px; }}

#Divider {{ background: {p.border}; border: none; min-height: 1px; max-height: 1px; }}
#Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; }}
#KpiLabel {{ color: {p.text_2}; font-size: 12px; }}
#KpiValue {{ font-size: 26px; font-weight: 600; }}
#KpiCaption {{ color: {p.text_3}; font-size: 12px; }}

/* --- düğmeler --- */
QPushButton {{
    background: {p.surface}; color: {p.text}; border: 1px solid {p.border_strong};
    border-radius: 7px; padding: 6px 12px; font-weight: 500;
}}
QPushButton:hover {{ background: {p.surface_2}; border-color: {p.text_3}; }}
QPushButton:pressed {{ background: {p.track}; }}
QPushButton:disabled {{ color: {p.text_3}; border-color: {p.border}; }}
QPushButton[variant="primary"] {{ background: {p.accent}; color: {p.on_accent}; border: 1px solid {p.accent}; }}
QPushButton[variant="primary"]:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton[variant="danger"] {{ color: {p.crit}; }}
QPushButton[variant="danger"]:hover {{ background: {p.crit_soft}; border-color: {p.crit}; }}
QPushButton[variant="ghost"] {{ border-color: transparent; background: transparent; color: {p.text_2}; }}
QPushButton[variant="ghost"]:hover {{ background: {p.track}; color: {p.text}; }}

#Segmented {{ background: {p.track}; border-radius: 8px; }}
#Segmented QPushButton {{ border: none; background: transparent; padding: 5px 12px; color: {p.text_2}; border-radius: 6px; }}
#Segmented QPushButton:checked {{ background: {p.surface}; color: {p.text}; font-weight: 600; }}

/* --- form öğeleri --- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 7px;
    padding: 5px 8px; min-height: 20px; selection-background-color: {p.accent_soft}; selection-color: {p.text};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {p.accent}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {p.text_3}; background: {p.surface_2}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({icons["chevron"]}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {p.surface}; border: 1px solid {p.border_strong}; selection-background-color: {p.accent_soft};
    selection-color: {p.text}; padding: 4px; outline: none;
}}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border; width: 0px; border: none; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {p.border_strong}; background: {p.surface}; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; image: url({icons["check"]}); }}
QLabel[role="field"] {{ color: {p.text_2}; font-size: 12px; }}

/* --- tablolar --- */
QTableView {{
    background: {p.surface}; border: none; gridline-color: transparent;
    selection-background-color: {p.accent_soft}; selection-color: {p.text}; alternate-background-color: {p.surface_2};
}}
QTableView::item {{ padding: 0 10px; border-bottom: 1px solid {p.border}; }}
QHeaderView::section {{
    background: {p.surface}; color: {p.text_3}; border: none; border-bottom: 1px solid {p.border};
    padding: 8px 10px; font-size: 11px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {p.surface}; border: none; }}

QListWidget {{ background: transparent; border: none; }}
QListWidget::item {{ border: none; }}

QPlainTextEdit {{
    background: {p.surface_2}; border: 1px solid {p.border}; border-radius: 8px; padding: 6px;
    font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px; color: {p.text_2};
}}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border_strong}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.text_3}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border_strong}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QDialog {{ background: {p.bg}; }}
QMessageBox {{ background: {p.surface}; }}

/* --- bildirim kartı (toast) --- */
#Toast {{ background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 10px; }}
#ToastTitle {{ font-weight: 600; font-size: 13px; }}
#ToastBody {{ color: {p.text_2}; font-size: 12px; }}

#Pill {{ border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}
#Pill[tone="ok"] {{ background: {p.accent_soft}; color: {p.accent}; }}
#Pill[tone="warning"] {{ background: {p.warn_soft}; color: {p.warn}; }}
#Pill[tone="critical"] {{ background: {p.crit_soft}; color: {p.crit}; }}
#Pill[tone="neutral"] {{ background: {p.track}; color: {p.text_2}; }}

#Banner {{ background: {p.crit_soft}; border: 1px solid {p.crit}; border-radius: 8px; color: {p.crit}; padding: 8px 10px; }}
"""
