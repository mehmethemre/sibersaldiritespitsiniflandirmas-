# Ağ Trafiği Verilerinden Siber Saldırı Türlerinin Sınıflandırılması

Fırat Üniversitesi Bilgisayar Mühendisliği · Mühendislik Tasarımı · 23. Grup
(Murat Tunç, Mehmet Emre Erdoğan, Bilal Demir)

CICIDS2017 ağ akış kayıtlarından normal trafiği (Benign) ve 5 saldırı sınıfını
(DoS/DDoS, PortScan, Brute Force, Web Attack, Botnet) ayırt eden makine öğrenmesi sistemi.

## Boru hattı (veri sızıntısı olmadan)

1. 8 CSV birleştirilir, sütun adları düzeltilir, `Destination Port` çıkarılır
2. Kapsam dışı sınıflar (Infiltration, Heartbleed), Inf/NaN satırlar, tekrarlayan satırlar ve sabit sütunlar silinir
3. Katmanlı %80 eğitim / %20 test bölmesi — **bundan sonra test kümesine dokunulmaz**
4. Öznitelik seçimi (korelasyon > 0,95 elemesi + ExtraTrees önem sıralaması) — yalnızca eğitim kümesinde
5. `StandardScaler` — yalnızca eğitim kümesine fit edilir
6. SMOTE — yalnızca eğitim kümesinde; küçük sınıflar 100.000 örneğe tamamlanır
7. Decision Tree ve Random Forest eğitimi, test kümesinde değerlendirme

Tüm ayarlar `src/config.py` dosyasındadır.

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
`4 passed` görmelisiniz.

### 6. Hızlı deneme (%5 örneklem, birkaç dakika)
```powershell
python run_pipeline.py --sample-frac 0.05
```
Bu yalnızca her şeyin çalıştığını görmek içindir; **bu sonuçlar rapora yazılmaz**.

### 7. Asıl çalıştırma (tam veri)
```powershell
python run_pipeline.py
```
32 GB RAM'li bir bilgisayarda yaklaşık 15–45 dakika sürmesi beklenir (işlemciye bağlı).
Çalışırken bilgisayarı uyku moduna almayın.

## Çıktılar

| Dosya | İçerik |
| --- | --- |
| `reports/rapor_tablolari.md` | Haftalık rapora doğrudan aktarılacak, Türkçe biçimli tablolar |
| `reports/metrics.json` | Tüm sayısal sonuçlar |
| `reports/run_log.txt` | Adım adım çalışma günlüğü ve donanım bilgisi |
| `reports/confusion_matrix_*.png` | Hata matrisi görselleri |
| `reports/feature_selection.json` | Elenen öznitelikler ve önem skorları |
| `artifacts/*.pkl`, `features.json`, `label_map.json` | Model, ölçekleyici, öznitelik listesi, sınıf kodları |

## Proje yapısı

```
run_pipeline.py        # tek komutla tüm süreç
src/config.py          # yollar, sınıf eşlemesi, hiperparametreler
src/data_loader.py     # CSV okuma ve birleştirme
src/preprocess.py      # temizlik, bölme, öznitelik seçimi, ölçekleme, SMOTE
src/evaluate.py        # metrikler, hata matrisi, gecikme ölçümü
tests/                 # sahte veriyle birim testleri
```
