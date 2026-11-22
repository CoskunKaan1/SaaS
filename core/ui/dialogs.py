"""Form diyalogları."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pyodbc
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import DatabaseSettings
from core.db.connection import DatabaseUnavailable, connect
from core.models import ApiService, Department, Provider, Team
from core.ui.widgets.common import Segmented, button, hbox, label


class FormDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, subtitle: str = "", primary: str = "Kaydet",
                 width: int = 420):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(width)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)
        root.addWidget(label(title, "PageTitle"))
        if subtitle:
            root.addWidget(label(subtitle, "Muted", wrap=True))
        self.error = QLabel()
        self.error.setObjectName("Banner")
        self.error.setWordWrap(True)
        self.error.hide()
        root.addWidget(self.error)
        self.form = QVBoxLayout()
        self.form.setSpacing(12)
        root.addLayout(self.form)
        root.addStretch(1)
        self.primary = button(primary, "primary", self._submit)
        self.primary.setDefault(True)
        self.cancel = button("Vazgeç", "ghost", self.reject)
        self.footer = hbox(None, self.cancel, self.primary)
        root.addLayout(self.footer)

    def field(self, title: str, widget: QWidget, hint: str = "") -> QWidget:
        box = QVBoxLayout()
        box.setSpacing(5)
        lbl = QLabel(title)
        lbl.setProperty("role", "field")
        box.addWidget(lbl)
        box.addWidget(widget)
        if hint:
            box.addWidget(label(hint, "Faint", wrap=True))
        self.form.addLayout(box)
        return widget

    def fail(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()

    def validate(self) -> str | None:
        """Hata mesajı döndürürse diyalog kapanmaz."""
        return None

    def _submit(self) -> None:
        problem = self.validate()
        if problem:
            self.fail(problem)
            return
        self.accept()



# --- organizasyon ---------------------------------------------------------
class DepartmentDialog(FormDialog):
    def __init__(self, parent):
        super().__init__(parent, "Yeni departman", "Ekipler bir departmana bağlıdır; masraf merkezi raporlamada kullanılır.")
        self.name = self.field("Departman adı", QLineEdit())
        self.cost_center = self.field("Masraf merkezi", QLineEdit(), "Örn. CC-550")

    def validate(self):
        if not self.name.text().strip():
            return "Departman adı gerekli."
        if not self.cost_center.text().strip():
            return "Masraf merkezi gerekli."
        return None


class TeamDialog(FormDialog):
    def __init__(self, parent, departments: list[Department], services: list[ApiService]):
        super().__init__(parent, "Yeni ekip", "Ekip oluşturulduğunda ilk bütçe dönemi de açılır.", width=460)
        self.department = self.field("Departman", QComboBox())
        for d in departments:
            self.department.addItem(d.name, d.id)
        self.name = self.field("Ekip adı", QLineEdit())
        self.limit = self.field("Dönem kredi limiti", _spin(1, 10_000_000, 1000))
        self.warn = self.field("Uyarı eşiği (%)", _spin(1, 99, 80))
        self.services = _ServiceChecklist(services, set())
        self.field("Erişebileceği servisler", self.services)

    def validate(self):
        if self.department.count() == 0:
            return "Önce bir departman oluşturun."
        if not self.name.text().strip():
            return "Ekip adı gerekli."
        return None


class BudgetDialog(FormDialog):
    def __init__(self, parent, team_name: str, limit: Decimal, warn: int):
        super().__init__(parent, "Bütçeyi düzenle", f"{team_name} ekibinin açık dönem limiti. "
                         "Değişiklik mevcut harcamayı silmez.")
        self.limit = self.field("Kredi limiti", _dspin(1, 10_000_000, float(limit)))
        self.warn = self.field("Uyarı eşiği (%)", _spin(1, 99, warn),
                               "Harcama bu orana ulaştığında uyarı bildirimi gönderilir.")


class AccessDialog(FormDialog):
    def __init__(self, parent, team: Team, services: list[ApiService], granted: set[int]):
        super().__init__(parent, "Servis izinleri", f"{team.name} ekibinin çağırabileceği servisler.", width=460)
        self.services = _ServiceChecklist(services, granted)
        self.form.addWidget(self.services)


class _ServiceChecklist(QScrollArea):
    def __init__(self, services: list[ApiService], checked: set[int]):
        super().__init__()
        self.setWidgetResizable(True)
        self.setMinimumHeight(min(260, 34 * max(1, len(services)) + 8))
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.boxes: list[tuple[QCheckBox, int]] = []
        for s in services:
            box = QCheckBox(f"{s.name}   ·   {s.provider_name}, {s.credit_per_unit.normalize():f} kredi / {s.unit_name}")
            box.setChecked(s.id in checked)
            lay.addWidget(box)
            self.boxes.append((box, s.id))
        lay.addStretch(1)
        self.setWidget(inner)

    def selected(self) -> list[int]:
        return [sid for box, sid in self.boxes if box.isChecked()]


# --- katalog -------------------------------------------------------------
class ProviderDialog(FormDialog):
    def __init__(self, parent):
        super().__init__(parent, "Yeni sağlayıcı")
        self.name = self.field("Sağlayıcı adı", QLineEdit())
        self.kind = Segmented([("Harici", "external"), ("Dahili", "internal")])
        self.field("Tür", self.kind)

    def validate(self):
        return None if self.name.text().strip() else "Sağlayıcı adı gerekli."


class ServiceDialog(FormDialog):
    def __init__(self, parent, providers: list[Provider]):
        super().__init__(parent, "Yeni servis", "Servis eklendikten sonra ekiplere erişim izni verilmelidir.")
        self.provider = self.field("Sağlayıcı", QComboBox())
        for p in providers:
            self.provider.addItem(p.name, p.id)
        self.name = self.field("Servis adı", QLineEdit())
        self.unit = self.field("Ücretlendirme birimi", QComboBox())
        self.unit.setEditable(True)
        self.unit.addItems(["istek", "1K token", "sayfa", "mesaj", "dakika", "MB"])
        self.price = self.field("Birim başına kredi", _dspin(0.0001, 100000, 1.0, decimals=4))

    def validate(self):
        if self.provider.count() == 0:
            return "Önce bir sağlayıcı ekleyin."
        if not self.name.text().strip():
            return "Servis adı gerekli."
        if not self.unit.currentText().strip():
            return "Birim gerekli."
        return None


class PriceDialog(FormDialog):
    def __init__(self, parent, service: ApiService):
        super().__init__(parent, "Birim fiyatı", f"{service.name} · {service.unit_name}. "
                         "Yeni fiyat sonraki çağrılardan itibaren geçerli olur; geçmiş kayıtlar değişmez.")
        self.price = self.field("Birim başına kredi", _dspin(0.0001, 100000, float(service.credit_per_unit), 4))


# --- bağlantı --------------------------------------------------------------
class ConnectionDialog(FormDialog):
    """SQL Server'a bağlanılamadığında açılır."""

    def __init__(self, parent, settings: DatabaseSettings, error: str = ""):
        super().__init__(
            parent, "SQL Server bağlantısı",
            "Uygulama verilerini Microsoft SQL Server'da tutar. Veritabanı yoksa otomatik oluşturulur.",
            primary="Bağlan", width=480,
        )
        self.settings = settings
        if error:
            self.fail(_short_error(error))
        self.server = self.field("Sunucu", QLineEdit(settings.server),
                                 r"Varsayılan kurulum için localhost, Express için .\SQLEXPRESS")
        self.database = self.field("Veritabanı", QLineEdit(settings.database))
        self.auth = Segmented([("Windows kimlik doğrulama", True), ("SQL kullanıcı", False)],
                              settings.trusted_connection)
        self.field("Kimlik doğrulama", self.auth)
        self.username = self.field("Kullanıcı adı", QLineEdit(settings.username))
        self.password = self.field("Parola", QLineEdit(settings.password))
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.driver = self.field("ODBC sürücüsü", QComboBox())
        self.driver.addItem("Otomatik seç", "auto")
        for name in pyodbc.drivers():
            if "SQL Server" in name:
                self.driver.addItem(name, name)
        idx = self.driver.findData(settings.driver)
        self.driver.setCurrentIndex(max(0, idx))
        self.status = label("", "Faint", wrap=True)
        self.form.addWidget(self.status)
        self.test_btn = button("Bağlantıyı dene", None, self._test)
        self.footer.insertWidget(0, self.test_btn)
        self.cancel.setText("Çıkış")
        self.auth.changed.connect(self._toggle_auth)
        self._toggle_auth(settings.trusted_connection)

    def _toggle_auth(self, trusted) -> None:
        self.username.setEnabled(not trusted)
        self.password.setEnabled(not trusted)

    def result_settings(self) -> DatabaseSettings:
        return replace(
            self.settings,
            server=self.server.text().strip() or "localhost",
            database=self.database.text().strip() or "ApiKrediTakip",
            trusted_connection=bool(self.auth.value()),
            username=self.username.text().strip(),
            password=self.password.text(),
            driver=self.driver.currentData(),
        )

    def _test(self) -> None:
        self.error.hide()
        self.status.setText("Bağlanılıyor…")
        self.status.repaint()
        try:
            conn = connect(self.result_settings(), database="master")
            version = conn.cursor().execute("SELECT CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(32)), "
                                            "CAST(SERVERPROPERTY('Edition') AS NVARCHAR(64))").fetchone()
            conn.close()
            self.status.setText(f"Bağlantı başarılı · SQL Server {version[0]} ({version[1]})")
        except (DatabaseUnavailable, pyodbc.Error) as exc:
            self.status.setText("")
            self.fail(_short_error(str(exc)))


def _short_error(message: str) -> str:
    text = message
    if "[ODBC" in text or "[Microsoft]" in text:
        tail = text.split("]")[-1]
        text = tail.split("(")[0].strip() or text
    if "Named Pipes" in message or "could not open a connection" in message.lower() or "08001" in message:
        text = ("Sunucuya ulaşılamadı. SQL Server kurulu ve çalışır durumda mı? Sunucu adını kontrol edin "
                "(ör. localhost veya .\\SQLEXPRESS).")
    elif "Login failed" in message or "28000" in message:
        text = "Oturum açılamadı. Kullanıcı adı/parola veya Windows yetkisini kontrol edin."
    return text[:400]


def _spin(lo: int, hi: int, value: int) -> QSpinBox:
    s = QSpinBox()
    s.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    s.lineEdit().setTextMargins(8, 0, 0, 0)
    s.setRange(lo, hi)
    s.setValue(value)
    s.setGroupSeparatorShown(True)
    s.setAlignment(Qt.AlignmentFlag.AlignLeft)
    return s


def _dspin(lo: float, hi: float, value: float, decimals: int = 2) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    s.lineEdit().setTextMargins(8, 0, 0, 0)
    s.setDecimals(decimals)
    s.setRange(lo, hi)
    s.setValue(value)
    s.setGroupSeparatorShown(True)
    return s


__all__ = [
    "AccessDialog", "BudgetDialog", "ConnectionDialog", "DepartmentDialog", "FormDialog", "PriceDialog",
    "ProviderDialog", "ServiceDialog", "TeamDialog"
]
