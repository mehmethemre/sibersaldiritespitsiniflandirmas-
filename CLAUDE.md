# Proje bağlamı — Claude Code için

## Proje
Fırat Üniversitesi Bilgisayar Mühendisliği, Mühendislik Tasarımı dersi (13 hafta), 23. Grup:
Murat Tunç, Mehmet Emre Erdoğan, Bilal Demir. Konu: **Ağ Trafiği Verilerinden Siber Saldırı
Türlerinin Sınıflandırılması** (CICIDS2017, çok sınıflı makine öğrenmesi). Haftalık ilerleme
raporu yazılıyor; her hafta kaptan değişiyor (ekip kendi belirliyor).

## Çok önemli kural
1–6. hafta raporları kod yazılmadan hazırlandı; içlerindeki sayılar (ör. %99,41 doğruluk,
0,142 ms, 48,6 MB) **gerçek değildir**. Kodlama 7. haftada sıfırdan başladı.
**Rapora, sunuma veya README'ye yalnızca bu koddan gerçekten çıkan sayılar yazılır.**
Sayı uydurma, tahmini değeri ölçülmüş gibi sunma. Sonuç yoksa "[doldurulacak]" yaz.

## Ortam
- Windows, 32 GB RAM, Python 3.11, sanal ortam `.venv` (PowerShell: `.venv\Scripts\Activate.ps1`)
- Veri: `data\raw\` içinde MachineLearningCSV.zip'ten çıkan 8 CSV (GitHub'a yüklenmez)
- Çalıştırma: `python run_pipeline.py` (hızlı deneme: `--sample-frac 0.05`), test: `python -m pytest -q`
- Çıktılar: `reports\rapor_tablolari.md`, `metrics.json`, `run_log.txt`, hata matrisi PNG'leri
  (haftalık arşiv: `reports\hafta7\`, `hafta8\`, `hafta9\`); uygulama: `streamlit run app.py`
- Uygulama verisi: `data\analizler.db` (SQLite), `logs\security.log` (ikisi de GitHub'a yüklenmez)

## Verilmiş tasarım kararları (değiştirmeden önce kullanıcıya sor)
- Sınıflar (6): Benign, DoS/DDoS, PortScan, Brute Force, Web Attack, Botnet.
  Infiltration ve Heartbleed (47 örnek) kapsam dışı. Eşleme: `src/config.py::map_label`.
- `Destination Port` çıkarılır (port ezberini önlemek için; 8. hafta Deney 3 ezberi doğruladı).
  Birebir kopya `Fwd Header Length.1` yüklemede silinir.
- Sızıntısız sıra: temizlik (Inf/NaN + **tekrarlayan satır silme**) → katmanlı %80/%20 bölme →
  **yalnızca eğitimde**: etiketi çakışan grupların silinmesi → öznitelik seçimi (yalnızca korelasyon
  > 0,95 elemesi; ExtraTrees adımı 9. haftada kaldırıldı, kalan 45 öznitelik) → StandardScaler fit →
  SMOTE (küçük sınıflar **10.000**'e, en büyük sınıf asla çoğaltılmaz).
  Bu ayarlar 8. haftada doğrulama kümesinde seçildi (`reports/hafta8/`).
- Modeller: Decision Tree (baseline: gini, max_depth=15, min_samples_split=10),
  Random Forest (n_estimators=100, max_depth=20, min_samples_split=5, n_jobs=-1), random_state=42.
  Uygulamada Random Forest kullanılır; **Botnet karar eşiği 0,30** (Botnet olasılığı ≥ 0,30 ise
  Botnet, değilse kalan en olası sınıf). Eşik kuralı tek yerde: `src/evaluate.py::predict_classes`.
- Alarm seviyeleri: DoS/DDoS, Botnet, Web Attack, Brute Force → CRITICAL; PortScan → WARNING;
  analiz başına sınıf başına tek log satırı (`src/alarm.py`).
- Alarm eşiği (10. haftadan beri oran tabanlı): sınıfın eşiği = max(`ALARM_MIN_FLOWS` = 9,
  ceil(`ALARM_RATES[sınıf]` × analiz edilen akış)); eşik altı → WARNING + "düşük sayıda şüpheli
  akış, incelenmeli" (gizlenmez, tahminler değişmez). Oranlar: DoS/DDoS 0,00044, Botnet 0,00101,
  PortScan 0,0001, Brute Force 0, Web Attack 0. Kural tek yerde: `src/alarm.py::alarm_threshold`.
  Doğrulama kümesinde önceden yazılmış ölçütle seçildi (`experiments/ratio_threshold.py`,
  `reports/hafta10/esik_secim_olcutu.md`). N_min 9. haftada seçilmişti (`experiments/alarm_threshold.py`).
- Gecikme: tek kayıtlık predict() medyanı (n_jobs=1) ayrı, toplu akış başı ortalama ayrı raporlanır.
- Metrikler `classification_report` çıktısından alınır; Macro F1 de raporlanır.

## Yol haritası
| Hafta | İş |
| --- | --- |
| 7 | Kod altyapısı, sızıntısız pipeline, DT/RF gerçek sonuçlar (mevcut kod) |
| 8 | Çapraz doğrulamalı hiperparametre arama (SMOTE imblearn Pipeline içinde, gerekirse örneklemle) + XGBoost/LightGBM karşılaştırması |
| 9 | `src/inference.py` + Streamlit `app.py` (CSV yükle, tahmin + güven skoru, dağılım grafiği, kritik saldırıda st.error) + `logging` ile `security.log` (RotatingFileHandler, CRITICAL; alarmları dosya bazında özetle) + SQLite geçmiş + demo dosyaları — **tamamlandı** |
| 10 | Test: N2 (<50 ms tek kayıt, 10.000 satır <5 sn), N3 (RAM <1,5 GB), N4 (bozuk/eksik sütunlu CSV'de çökmeme), oran tabanlı alarm eşiği, uçtan uca testler — **tamamlandı** (`reports/hafta10_sonuclar.md`) |
| 11 | Öznitelik önem analizi, arayüz iyileştirme, README; isteğe bağlı VirtualBox laboratuvarında nmap + CICFlowMeter canlı demo denemesi |
| 12 | Dönem sonu teknik raporu |
| 13 | Final sunumu ve canlı demo |

## Gereksinimler (2. hafta raporundan)
F1 CSV yükleme · F2 temizlik · F3 öznitelik seçimi · F4 normalizasyon · F5 dengesizlik giderme ·
F6 çok sınıflı model · F7 metrikler + hata matrisi · F8 yeni akış için sınıf + güven skoru ·
F9 grafik/tablo ile raporlama · F10 model kaydetme (joblib) · F11 kritik saldırıda alarm + log.
N1 doğruluk ≥ %95, kritik sınıflarda F1 ≥ %90 · N2 gecikme · N3 bellek · N4 hata yönetimi ·
N5 sade arayüz · N6 Python 3.10+, Windows/Linux.

## Çalışma tarzı
- Kullanıcıyla Türkçe konuş; kod yorumları ve çıktılar Türkçe.
- Değişiklikten sonra `python -m pytest -q` çalıştır; yeni modüle test ekle.
- Büyük veriyle uzun çalıştırmalardan önce `--sample-frac` ile dene.
- Commit/push yalnızca kullanıcı isteyince.
- Commit mesajlarına ve PR açıklamalarına "Co-Authored-By: Claude" veya benzeri imza satırı ekleme.

## 10. hafta özeti (26.11.2026; ayrıntı ve tüm sayılar: `reports/hafta10_sonuclar.md`)
- Ölçüm bilgisayarı: i5-12500H, 31,8 GB RAM, Windows 11 (26300), Python 3.11.9, scikit-learn 1.9.1.
- N3 sağlandı: tepe bellek en kötü 1.058,3 MB (komut satırı, tüm test kümesi 439.792 satır,
  `scripts/measure_memory.py`, ayrı süreç × 3 tekrar); Streamlit sürecinde 1.290,4 MB (tek ölçüm).
  Chunk okuma gerekmedi. Yükleme sınırı 500 MB, en büyük dosya 169,6 MB.
- N2 sağlandı: tek kayıt predict() medyanı ort. 4,48 ms (en kötü 5,10 ms); 10.000 satır 0,169 sn.
  Tek satırlık CSV uçtan uca 56 ms (okuma dahil; N2 tanımı değil).
- Oran tabanlı eşik: ölçüt deneyden önce commit edildi (her boyutta yanlış KRİTİK ≤ %5; S1 ortalama
  kaçırma en düşük). Sınıf bazında oran tek orana göre kaçırmayı 10,71 puan düşürdü → seçildi.
  Test (bir kez): KRİTİK yanlış alarm her boyutta ≤ %5; **PortScan 100.000 satırda yanlış UYARI %13,6**
  (doğrulamada %3,1). Bedel: büyük dosyada az sayıda DoS/Botnet akışı incelenmeliye düşer; doğal
  orandaki Botnet büyük dosyalarda KRİTİK almaz (tüm test kümesi: 419 tespit / eşik 445).
  Demo dosyalarında alarmlar 9. haftayla birebir aynı.
- N4: CSV olmayan dosya (zip/xlsx, resim, NUL), noktalı virgüllü ve UTF-16 CSV için yanıltıcı mesajlar
  düzeltildi. Testler: 55 → 80 (27,84–28,59 sn), `tests/test_e2e.py` (uçtan uca + AppTest) eklendi.
- Kalan sınır / 11. hafta için aday: `max(N_min, oran × n)` biçimi büyük dosyada gereğinden yüksek
  eşik veriyor; beklenen yanlış alarm + dalgalanma payı (Poisson üst sınırı) düşünülebilir.

## 11. hafta: Botnet SMOTE denemesi (ölçüt deneyden ÖNCE yazıldı, 28.11.2026)
Ayrıntı: `reports/hafta11/botnet_secim_olcutu.md` (deney: `experiments/botnet_smote.py`).
- Mevcut ayar (SMOTE 10.000, eşik 0,30, tohum 42) doğrulamada: 230 Botnet satırı, recall %94,78,
  precision %63,01, F1 %75,69. Recall %90'ı sağladığı için sınır mutlak kalır.
- Izgara: Botnet SMOTE hedefi {yok (900), 2.500, 5.000, 10.000} × Botnet eşiği {0,30; 0,50; 0,70}
  × tohum {42, 43, 44} (SMOTE ve RF tohumu). Diğer küçük sınıflar hep 10.000. Yalnızca doğrulama.
- Uygunluk: ortalama Botnet recall ≥ %90 (R'nin 3 tohum ortalaması %90'ın altındaysa: R − 2 puan);
  Botnet dışı her sınıfın ortalama F1'i ≥ R − 0,5 puan. R = (10.000; 0,30), aynı 3 tohum.
- Seçim: uygunlar içinde en yüksek ortalama Botnet F1. Benimseme: Δ ≥ 1 puan VE
  Δ > max(std seçilen, std R). Değilse mevcut ayar kalır ve test kümesi kullanılmaz.
- Benimsenirse: son model tüm eğitimde (tohum 42); alarm oranları/N_min doğrulamada 10. hafta
  yöntemiyle yeniden; N2/N3 yeniden ölçülür; uygulama ve testler güncellenir; testte yalnızca
  seçilen ayar bir kez ölçülür (testin **ikinci** kullanımı, 9. hafta test sonuçları yanında kalır).

## Güncel durum (26.11.2026)
- 10. hafta tamamlandı ve GitHub'a push edildi (`303dd00`). Sıradaki iş: 11. hafta (yol haritası).
- Arayüz ölçüm analizleri (#14–#17, perf_*.csv) veritabanından ve `logs/security.log`'dan silindi;
  silmeden önceki yedek `data/yedek_hafta10/` (gitignore'da). Geçmişte yalnızca demo analizleri var.
- Geliştirme araçları kuruldu: superpowers, ponytail (bu projede kapalı; 10. hafta oturumunda kullanıcı komutuyla geçici olarak lite modda açıktı), andrej-karpathy-skills, find-skills, graphify, caveman, claude-mem.
- **caveman bu projede kullanılmaz**: açıklamalı, öğretici cevaplar isteniyor.
- graphify bilgi grafiği `graphify-out/` altında (424 düğüm, 17 topluluk; `graphify-out/GRAPH_REPORT.md`). Klasör `.gitignore`'da; kod değişince `/graphify . --update` ile yenilenir.
- graphify kancası yalnızca yerelde: `.claude/settings.local.json` (gitignore'da; ekip arkadaşlarında graphify yok). `graphify claude install` CLAUDE.md'ye yazdığı için kullanılmadı.
- claude-mem şimdilik **kapalı** (`~/.claude/settings.json` → `"claude-mem@thedotmack": false`): arka plan servisi (localhost:37777) yanıt vermedi, `/learn-codebase` hafızaya kaydedilmedi. Açınca `/learn-codebase` yeniden çalıştırılmalı.
