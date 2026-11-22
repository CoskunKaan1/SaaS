"""Uygulama ayarları.

Ayarlar proje kökündeki ``config.ini`` dosyasından okunur. Dosya yoksa
varsayılanlar kullanılır. Ortam değişkenleri (``KREDI_DB_SERVER`` vb.)
dosyadaki değerleri ezer; bu sayede CI veya test ortamında dosyaya
dokunmadan farklı bir sunucu gösterilebilir.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.ini"


@dataclass(frozen=True)
class DatabaseSettings:
    server: str = "localhost"
    database: str = "ApiKrediTakip"
    driver: str = "auto"
    trusted_connection: bool = True
    username: str = ""
    password: str = ""
    trust_server_certificate: bool = True
    timeout: int = 5


@dataclass(frozen=True)
class SimulationSettings:
    autostart: bool = True
    tick_seconds: float = 0.5
    auto_reset_seconds: int = 0
    seed_demo_data: bool = True


@dataclass(frozen=True)
class UiSettings:
    theme: str = "light"


@dataclass(frozen=True)
class Settings:
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    simulation: SimulationSettings = field(default_factory=SimulationSettings)
    ui: UiSettings = field(default_factory=UiSettings)


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "evet", "on"}


def load_settings(path: Path | None = None) -> Settings:
    path = path or CONFIG_PATH
    parser = configparser.ConfigParser()
    if path.exists():
        parser.read(path, encoding="utf-8")

    db = DatabaseSettings()
    if parser.has_section("database"):
        s = parser["database"]
        db = replace(
            db,
            server=s.get("server", db.server),
            database=s.get("database", db.database),
            driver=s.get("driver", db.driver),
            trusted_connection=_bool(s.get("trusted_connection", str(db.trusted_connection))),
            username=s.get("username", db.username),
            password=s.get("password", db.password),
            trust_server_certificate=_bool(
                s.get("trust_server_certificate", str(db.trust_server_certificate))
            ),
            timeout=s.getint("timeout", db.timeout),
        )

    env = os.environ
    db = replace(
        db,
        server=env.get("KREDI_DB_SERVER", db.server),
        database=env.get("KREDI_DB_NAME", db.database),
        driver=env.get("KREDI_DB_DRIVER", db.driver),
        username=env.get("KREDI_DB_USER", db.username),
        password=env.get("KREDI_DB_PASSWORD", db.password),
    )
    if "KREDI_DB_USER" in env:
        db = replace(db, trusted_connection=False)

    sim = SimulationSettings()
    if parser.has_section("simulation"):
        s = parser["simulation"]
        sim = replace(
            sim,
            autostart=_bool(s.get("autostart", str(sim.autostart))),
            tick_seconds=s.getfloat("tick_seconds", sim.tick_seconds),
            auto_reset_seconds=s.getint("auto_reset_seconds", sim.auto_reset_seconds),
            seed_demo_data=_bool(s.get("seed_demo_data", str(sim.seed_demo_data))),
        )

    ui = UiSettings()
    if parser.has_section("ui"):
        ui = replace(ui, theme=parser["ui"].get("theme", ui.theme))

    return Settings(database=db, simulation=sim, ui=ui)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = path or CONFIG_PATH
    parser = configparser.ConfigParser()
    d = settings.database
    parser["database"] = {
        "server": d.server,
        "database": d.database,
        "driver": d.driver,
        "trusted_connection": "yes" if d.trusted_connection else "no",
        "username": d.username,
        "password": d.password,
        "trust_server_certificate": "yes" if d.trust_server_certificate else "no",
        "timeout": str(d.timeout),
    }
    s = settings.simulation
    parser["simulation"] = {
        "autostart": "yes" if s.autostart else "no",
        "tick_seconds": str(s.tick_seconds),
        "auto_reset_seconds": str(s.auto_reset_seconds),
        "seed_demo_data": "yes" if s.seed_demo_data else "no",
    }
    parser["ui"] = {"theme": settings.ui.theme}
    with path.open("w", encoding="utf-8") as fh:
        parser.write(fh)
