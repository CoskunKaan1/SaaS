"""SQL Server bağlantı yönetimi (pyodbc)."""

from __future__ import annotations

import threading

import pyodbc

from core.config import DatabaseSettings

# Tercih sırası: en yeni sürücü önce. "SQL Server" Windows'la gelen eski
# sürücüdür; diğerleri yoksa son çare olarak kullanılır.
PREFERRED_DRIVERS = (
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
    "SQL Server Native Client 11.0",
    "SQL Server",
)


class DatabaseUnavailable(RuntimeError):
    """Sunucuya bağlanılamadığında fırlatılır; arayüz bunu kullanıcıya gösterir."""


def detect_driver(requested: str = "auto") -> str:
    installed = set(pyodbc.drivers())
    if requested and requested != "auto":
        if requested not in installed:
            raise DatabaseUnavailable(
                f"ODBC sürücüsü bulunamadı: {requested!r}. Kurulu sürücüler: {sorted(installed)}"
            )
        return requested
    for name in PREFERRED_DRIVERS:
        if name in installed:
            return name
    raise DatabaseUnavailable(
        "SQL Server için ODBC sürücüsü bulunamadı. 'ODBC Driver 18 for SQL Server' kurun."
    )


def build_connection_string(settings: DatabaseSettings, database: str | None = None) -> str:
    driver = detect_driver(settings.driver)
    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={settings.server}",
        f"DATABASE={database or settings.database}",
    ]
    if settings.trusted_connection:
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={settings.username}")
        parts.append(f"PWD={settings.password}")
    if driver.startswith("ODBC Driver 1"):
        # Yerel kurulumlar kendinden imzalı sertifika kullanır; şifreleme açık
        # kalır, sertifika zinciri doğrulaması ise ayara bağlıdır.
        parts.append("Encrypt=yes")
        if settings.trust_server_certificate:
            parts.append("TrustServerCertificate=yes")
    parts.append("APP=KrediTakip")
    return ";".join(parts) + ";"


def connect(settings: DatabaseSettings, database: str | None = None, autocommit: bool = True):
    try:
        return pyodbc.connect(
            build_connection_string(settings, database),
            autocommit=autocommit,
            timeout=settings.timeout,
        )
    except pyodbc.Error as exc:  # pragma: no cover - sunucu ortamına bağlı
        raise DatabaseUnavailable(str(exc)) from exc


class ConnectionPool:
    """İş parçacığı başına bir bağlantı.

    pyodbc bağlantıları iş parçacıkları arasında güvenle paylaşılamaz. Arayüz
    ana iş parçacığında, simülasyon motoru ise arka planda çalıştığı için her
    iş parçacığı kendi bağlantısını tembel olarak açar.
    """

    def __init__(self, settings: DatabaseSettings):
        self.settings = settings
        self._local = threading.local()
        self._all: list = []
        self._lock = threading.Lock()

    def get(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = connect(self.settings)
            self._local.conn = conn
            with self._lock:
                self._all.append(conn)
        return conn

    def close_all(self) -> None:
        with self._lock:
            for conn in self._all:
                try:
                    conn.close()
                except pyodbc.Error:
                    pass
            self._all.clear()
        self._local = threading.local()
