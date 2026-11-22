"""İlk açılışta boş veritabanına örnek organizasyon verisi yükler."""

from __future__ import annotations

from decimal import Decimal

from core.db.repository import Repository

DEPARTMENTS = [
    ("Ürün Geliştirme", "CC-110"),
    ("Veri ve Analitik", "CC-220"),
    ("Müşteri Deneyimi", "CC-330"),
]

# (departman, ekip, limit, uyarı %)
TEAMS = [
    ("Ürün Geliştirme", "Mobil", 2500, 80),
    ("Ürün Geliştirme", "Web Platform", 2000, 75),
    ("Veri ve Analitik", "Veri Bilimi", 4000, 85),
    ("Veri ve Analitik", "Raporlama", 600, 80),
    ("Müşteri Deneyimi", "Destek", 900, 70),
]

PROVIDERS = [
    ("Nimbus AI", "external"),
    ("GeoPoint", "external"),
    ("SMSPort", "external"),
    ("İç Platform", "internal"),
]

# (sağlayıcı, servis, birim, birim başına kredi)
SERVICES = [
    ("Nimbus AI", "Metin üretimi", "1K token", "0.80"),
    ("Nimbus AI", "Embedding", "1K token", "0.05"),
    ("GeoPoint", "Adres doğrulama", "istek", "0.20"),
    ("GeoPoint", "Rota hesaplama", "istek", "0.50"),
    ("SMSPort", "SMS gönderimi", "mesaj", "0.35"),
    ("İç Platform", "Kimlik doğrulama", "istek", "0.02"),
    ("İç Platform", "Belge OCR", "sayfa", "0.40"),
]

ACCESS = {
    "Mobil": ["Metin üretimi", "Adres doğrulama", "SMS gönderimi", "Kimlik doğrulama"],
    "Web Platform": ["Metin üretimi", "Kimlik doğrulama", "Rota hesaplama"],
    "Veri Bilimi": ["Metin üretimi", "Embedding", "Belge OCR"],
    "Raporlama": ["Embedding", "Belge OCR", "Kimlik doğrulama"],
    "Destek": ["Metin üretimi", "SMS gönderimi", "Kimlik doğrulama"],
}

# (ekip, ad, e-posta, rol, simüle mi, persona, dk başı çağrı, hata oranı)
USERS = [
    ("Mobil", "Deniz Aksoy", "deniz.aksoy@sirket.local", "lead", False, None, 0, 0.0),
    ("Mobil", "mobil-app-bot", "mobil-bot@sirket.local", "service", True, "steady", 30, 0.02),
    ("Web Platform", "web-gateway", "web-gw@sirket.local", "service", True, "wave", 36, 0.03),
    ("Veri Bilimi", "Selin Kara", "selin.kara@sirket.local", "member", True, "heavy", 10, 0.01),
    ("Veri Bilimi", "etl-nightly", "etl@sirket.local", "service", True, "bursty", 20, 0.02),
    ("Raporlama", "rapor-zamanlayici", "rapor@sirket.local", "service", True, "steady", 16, 0.01),
    ("Destek", "destek-asistani", "destek-bot@sirket.local", "service", True, "bursty", 24, 0.04),
    ("Destek", "Mert Yılmaz", "mert.yilmaz@sirket.local", "lead", False, None, 0, 0.0),
]


def seed_demo_data(repo: Repository) -> bool:
    """Veritabanı boşsa örnek veriyi yükler; yüklediyse True döner."""
    if not repo.is_empty():
        return False

    dept_ids = {name: repo.add_department(name, cc) for name, cc in DEPARTMENTS}
    team_ids: dict[str, int] = {}
    for dept, team, limit, warn in TEAMS:
        tid = repo.add_team(dept_ids[dept], team)
        team_ids[team] = tid
        repo.open_budget(tid, Decimal(limit), warn)

    prov_ids = {name: repo.add_provider(name, kind) for name, kind in PROVIDERS}
    svc_ids = {
        name: repo.add_service(prov_ids[prov], name, unit, Decimal(price)) for prov, name, unit, price in SERVICES
    }
    for team, services in ACCESS.items():
        repo.set_team_access(team_ids[team], [svc_ids[s] for s in services])

    for team, name, email, role, simulated, persona, cpm, err in USERS:
        uid = repo.add_user(team_ids[team], name, email, role, simulated)
        if simulated and persona:
            repo.upsert_profile(uid, persona, cpm, err, True)
    return True
