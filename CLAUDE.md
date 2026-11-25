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

## Verilmiş tasarım kararları (değiştirmeden önce kullanıcıya sor)
- Sınıflar (6): Benign, DoS/DDoS, PortScan, Brute Force, Web Attack, Botnet.
  Infiltration ve Heartbleed (47 örnek) kapsam dışı. Eşleme: `src/config.py::map_label`.
- `Destination Port` çıkarılır (port ezberini önlemek için).
- Sızıntısız sıra: temizlik (Inf/NaN + **tekrarlayan satır silme**) → katmanlı %80/%20 bölme →
  öznitelik seçimi (korelasyon > 0,95 + ExtraTrees kümülatif önem %90) **yalnızca eğitimde** →
  StandardScaler **yalnızca eğitime fit** → SMOTE **yalnızca eğitimde** (küçük sınıflar 100.000'e,
  en büyük sınıf asla çoğaltılmaz).
- Modeller: Decision Tree (baseline: gini, max_depth=15, min_samples_split=10),
  Random Forest (n_estimators=100, max_depth=20, min_samples_split=5, n_jobs=-1), random_state=42.
- Gecikme: tek kayıtlık predict() medyanı (n_jobs=1) ayrı, toplu akış başı ortalama ayrı raporlanır.
- Metrikler `classification_report` çıktısından alınır; Macro F1 de raporlanır.

## Yol haritası
| Hafta | İş |
| --- | --- |
| 7 | Kod altyapısı, sızıntısız pipeline, DT/RF gerçek sonuçlar (mevcut kod) |
| 8 | Çapraz doğrulamalı hiperparametre arama (SMOTE imblearn Pipeline içinde, gerekirse örneklemle) + XGBoost/LightGBM karşılaştırması |
| 9 | `src/inference.py` + Streamlit `app.py` (CSV yükle, tahmin + güven skoru, dağılım grafiği, kritik saldırıda st.error) + `logging` ile `security.log` (RotatingFileHandler, CRITICAL; alarmları dosya bazında özetle) |
| 10 | Test: N2 (<50 ms tek kayıt, 10.000 satır <5 sn), N3 (RAM <1,5 GB), N4 (bozuk/eksik sütunlu CSV'de çökmeme), demo CSV'leri (test kümesinden: normal, ddos, karma) üreten betik |
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
