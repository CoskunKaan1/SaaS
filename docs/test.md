# Testler

```powershell
python -m pytest            # tümü
python -m pytest -v -rs     # ayrıntılı, atlanan testlerin nedeniyle
```

| Dosya | Kapsam | SQL Server gerekir mi? |
|---|---|---|
| `test_credit_service.py` | Maliyet hesabı, kredi düşme, hata/ret kuralları, eşik ve limit bildirimlerinin **bir kez** üretilmesi, sıfırlama ve geçmişin korunması, yetki/pasif kullanıcı kontrolleri, olay yayını, eşzamanlı çağrılarda limitin aşılmaması | Hayır |
| `test_testusers.py` | Test kullanıcısı oluşturma ve doğrulama, ID ile dahil etme, Poisson dağılımı, personalar, sahte bağlayıcı, motor adımı, otomatik sıfırlama, tek çağrı, iş parçacığının başlayıp durması | Hayır |
| `test_db_layer.py` | Şema betiğinin bölünmesi ve 10 tablonun tanımı, ODBC sürücü seçimi, bağlantı dizesi, ayar dosyası, ortam değişkenleri, eski sürücü tarih dönüşümü, örnek verinin idempotent oluşu | Hayır |
| `test_ui_smoke.py` | Arayüzün ekransız (offscreen) kurulması, her sayfanın yenilenmesi, bildirim kartı ve rozet, test panelinden kullanıcı oluşturma, tema değişimi, Türkçe biçimlendirme | Hayır |
| `test_sqlserver_integration.py` | Gerçek SQL Server'da şemanın iki kez uygulanabilmesi, örnek veri, kredi düşme ve görünüm, limit reddi ve bildirimler, `sp_ResetTeamBudget`, tek açık dönem indeksi, CHECK kısıtları, simülasyon motoru | **Evet.** Sunucu yoksa otomatik atlanır |

SQL Server testleri ayrı bir `ApiKrediTakip_Test` veritabanı oluşturur ve test
bitince siler. Uygulamanın asıl veritabanına dokunmaz. Farklı bir sunucu için:

```powershell
$env:KREDI_DB_SERVER = ".\SQLEXPRESS"
python -m pytest tests/test_sqlserver_integration.py -v
```

Birim testleri SQL Server yerine `tests/fakes.py` içindeki `InMemoryRepository`
ile çalışır. Bu sınıf `Repository` arayüzünü uygular ve benzersizlik, tek açık
dönem, pozitif fiyat gibi kısıtları şemayla aynı şekilde denetler.
