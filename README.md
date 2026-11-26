# Ağ Trafiği Verilerinden Siber Saldırı Türlerinin Sınıflandırılması

Fırat Üniversitesi Bilgisayar Mühendisliği · Mühendislik Tasarımı · 23. Grup
(Murat Tunç, Mehmet Emre Erdoğan, Bilal Demir)

CICIDS2017 ağ akış kayıtlarından normal trafiği (Benign) ve 5 saldırı sınıfını
(DoS/DDoS, PortScan, Brute Force, Web Attack, Botnet) ayırt eden makine öğrenmesi sistemi.

## Boru hattı (veri sızıntısı olmadan)

1. 8 CSV birleştirilir, sütun adları düzeltilir, `Destination Port` ve birebir kopya `Fwd Header Length.1` çıkarılır
2. Kapsam dışı sınıflar (Infiltration, Heartbleed), Inf/NaN satırlar, tekrarlayan satırlar ve sabit sütunlar silinir
3. Katmanlı %80 eğitim / %20 test bölmesi — **bundan sonra test kümesine dokunulmaz**
4. Öznitelikleri aynı ama etiketi farklı satır grupları eğitimden silinir
5. Öznitelik seçimi: korelasyon > 0,95 elemesi (ExtraTrees adımı 9. haftada kaldırıldı) — yalnızca eğitim kümesinde
6. `StandardScaler` — yalnızca eğitim kümesine fit edilir
7. SMOTE — yalnızca eğitim kümesinde; küçük sınıflar 10.000 örneğe tamamlanır
8. Decision Tree ve Random Forest eğitimi; Random Forest'ta Botnet karar eşiği 0,30; test kümesinde değerlendirme

Bu ayarlar 8. haftada doğrulama kümesi üzerinde yapılan deneylerle seçildi
(`reports/hafta8/rapor_tablolari_hafta8.md`). Tüm ayarlar `src/config.py` dosyasındadır.

## Windows kurulumu

### 1. Python 3.11 kurun
[python.org/downloads](https://www.python.org/downloads/) adresinden **Python 3.11** indirin.
Kurulumun ilk ekranında **"Add python.exe to PATH"** kutusunu işaretleyin.

### 2. Proje klasöründe PowerShell açın
Zip'i açın (ör. `C:\projeler\siber-saldiri-siniflandirma`). Klasörün içinde boş bir yere
sağ tıklayıp **"Terminalde aç"** seçin.

### 3. Sanal ortam ve kütüphaneler
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
`Activate.ps1` "betik çalıştırma devre dışı" hatası verirse bir kez şunu çalıştırıp `Y` deyin,
sonra etkinleştirme komutunu tekrarlayın:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
Satırın başında `(.venv)` görünüyorsa ortam etkin demektir. Bilgisayarı her açtığınızda
yalnızca `.venv\Scripts\Activate.ps1` komutunu çalıştırmanız yeterlidir.

### 4. Veri setini yerleştirin
[CIC-IDS2017 sayfasındaki](https://www.unb.ca/cic/datasets/ids-2017.html) "Download this dataset"
bağlantısından **MachineLearningCSV.zip** dosyasını indirin. Zip'in içindeki
`MachineLearningCVE` klasöründe bulunan **8 CSV dosyasını** projedeki `data\raw\` klasörüne kopyalayın.

### 5. Kodu test edin (gerçek veri gerekmez)
```powershell
python -m pytest -q
```
Tüm testlerin `passed` olduğunu görmelisiniz.

### 6. Hızlı deneme (%5 örneklem, birkaç dakika)
```powershell
python run_pipeline.py --sample-frac 0.05
```
Bu yalnızca her şeyin çalıştığını görmek içindir; **bu sonuçlar rapora yazılmaz**.

### 7. Asıl çalıştırma (tam veri)
```powershell
python run_pipeline.py
```
Geliştirme bilgisayarında (i5-12500H, 32 GB RAM) yaklaşık 3,5 dakika sürdü.
Model ve yardımcı dosyalar `artifacts/` altına yazılır; uygulama bunları kullanır.

## Uygulamayı çalıştırma

Önce modelin eğitilmiş olması gerekir (yukarıdaki 7. adım; `artifacts/random_forest_model.pkl`
GitHub'da yoktur). Sonra:
```powershell
streamlit run app.py
```
Tarayıcıda `http://localhost:8501` açılır.

* **Analiz** sayfası: CSV yükleyin, **Analiz et**'e basın. Özet kartları, sınıf dağılımı,
  güven skorlu ilk 100 tahmin, kritik saldırılar için kırmızı alarm kartları ve tüm tahminleri
  CSV olarak indirme düğmesi gösterilir. Dosyada `Label` sütunu varsa tahminler gerçek
  etiketlerle de karşılaştırılır.
* **Geçmiş Analizler** sayfası: önceki analizler ve alarmlar (`data/analizler.db`).
* Alarmlar `logs/security.log` dosyasına da yazılır (sınıf başına tek satır; DoS/DDoS, Botnet,
  Web Attack, Brute Force -> CRITICAL, PortScan -> WARNING).
* **Alarm eşiği:** bir saldırı sınıfından en az N akış (varsayılan 9) bulunursa alarm verilir;
  daha azsa gri/mavi "düşük sayıda şüpheli akış, incelenmeli" bilgisi gösterilir ve günlüğe WARNING
  yazılır. Tahminler değişmez. N kenar çubuğundan değiştirilebilir; varsayılan değer
  `src/config.py::ALARM_MIN_FLOWS`'tadır ve doğrulama kümesinde seçilmiştir
  (`python experiments/alarm_threshold.py`, sonuçlar `reports/hafta9/alarm_esigi.md`).
* Yükleme sınırı 500 MB'tır (`.streamlit/config.toml`).

### Demo dosyaları

`demo/` klasöründeki dosyalar test kümesinden (model eğitimde görmedi) üretilmiştir ve gerçek
etiketi içerir: `demo_normal.csv`, `demo_ddos.csv`, `demo_portscan.csv`, `demo_karma.csv`,
`demo_10000_satir.csv`; hata yönetimini denemek için `demo_bozuk.csv` (bozuk hücreler) ve
`demo_eksik_sutun.csv` (eksik sütunlar). Yeniden üretmek için (veri seti gerekir):
```powershell
python scripts/make_demo_files.py
```
Tüm demo dosyalarını arayüz açmadan analiz edip süreleri ölçmek için:
```powershell
python scripts/check_demo_files.py
```

## Çıktılar

| Dosya | İçerik |
| --- | --- |
| `reports/rapor_tablolari.md` | Son eğitimin Türkçe biçimli tabloları |
| `reports/metrics.json` | Tüm sayısal sonuçlar |
| `reports/run_log.txt` | Adım adım çalışma günlüğü ve donanım bilgisi |
| `reports/confusion_matrix_*.png` | Hata matrisi görselleri |
| `reports/feature_selection.json` | Korelasyonla elenen öznitelikler |
| `reports/hafta7/`, `hafta8/`, `hafta9/` | Haftalık sonuçların arşivi |
| `artifacts/*.pkl`, `features.json`, `label_map.json` | Model, ölçekleyici, öznitelik listesi, sınıf kodları |
| `artifacts/model_config.json` | Model sürümü, sınıf sırası, Botnet eşiği, eğitim ayarları |

## Proje yapısı

```
run_pipeline.py        # tek komutla eğitim ve değerlendirme
app.py                 # Streamlit arayüzü
src/config.py          # yollar, sınıf eşlemesi, hiperparametreler, alarm seviyeleri
src/data_loader.py     # CSV okuma ve birleştirme
src/preprocess.py      # temizlik, bölme, çakışma silme, öznitelik seçimi, ölçekleme, SMOTE
src/evaluate.py        # metrikler, Botnet eşik kuralı, hata matrisi, gecikme ölçümü
src/inference.py       # yeni CSV için doğrulama + tahmin + güven skoru
src/database.py        # SQLite analiz geçmişi
src/alarm.py           # security.log ve alarm üretimi
src/service.py         # analiz akışı: tahmin -> veritabanı -> alarm
experiments/           # 8. hafta deney betikleri
scripts/               # demo dosyası üretimi ve kontrolü
demo/                  # test kümesinden demo CSV'leri
tests/                 # sahte veriyle birim testleri
```
