# 10. Hafta Sonuçları — Test Haftası

Tarih: 26.11.2026 · Model: `hafta9-rf-1` (9. haftada eğitilen Random Forest; bu hafta yeniden
eğitilmedi). Bu dosyadaki her sayı aşağıda adı geçen betiklerin gerçek çıktısından alınmıştır;
ham çıktılar `reports/hafta10/` klasöründedir.

**Kural:** test kümesi yalnızca son ölçüm için kullanıldı. Alarm eşiği yalnızca doğrulama
kümesinde seçildi; seçim ölçütü deneyden önce yazılıp commit edildi
(`reports/hafta10/esik_secim_olcutu.md`, commit `2e299b8`).

## 1. Ölçüm bilgisayarı

Kaynak: `reports/hafta10/ortam.json` (`scripts/measure_memory.py`).

| Özellik | Değer |
| --- | --- |
| İşlemci | 12th Gen Intel Core i5-12500H (12 fiziksel / 16 mantıksal çekirdek) |
| RAM | 31,8 GB |
| İşletim sistemi | Windows 11 Pro for Workstations, sürüm 10.0.26300 (Python `platform` modülü "Windows 10" olarak bildiriyor; 26300 numaralı yapı Windows 11'dir) |
| Python | 3.11.9 |
| Kütüphaneler | pandas 3.1.1 · numpy 2.4.6 · scikit-learn 1.9.1 · joblib 1.6.0 · streamlit 1.67.0 · psutil 7.2.2 |

## 2. N3 — Bellek ve süre ölçümü

### 2.1 Komut satırından (arayüzün kullandığı akış)

Betik: `scripts/measure_memory.py`. Ölçüm dosyaları test kümesinden örneklendi (yalnızca
performans ölçümünde kullanıldı; `data/perf/`, GitHub'a yüklenmez). Her durum **ayrı bir alt
süreçte**, **3 kez** ölçüldü; tepe bellek önceki ölçümden miras kalmasın diye her seferinde yeni
süreç açıldı. Tepe bellek = sürecin `peak_wset` değeri (Windows'ta peak RSS). Analiz akışı
`src/service.py::run_analysis` (CSV okuma → doğrulama → tahmin → SQLite → alarm/log), geçici
veritabanı ve geçici log dosyasıyla.

| Durum | Dosya | Tepe bellek ort. (MB) | Tepe bellek en kötü (MB) | Analiz süresi ort. (sn) | Analiz süresi en kötü (sn) | Uçtan uca ort. / en kötü (sn)* |
| --- | --- | --- | --- | --- | --- | --- |
| Yalnızca kütüphaneler | — | 175,5 | 175,8 | — | — | — |
| Model yüklendi | — | 243,7 | 244,0 | yükleme 0,174 | yükleme 0,203 | — |
| 1 satır | 0,001 MB | 243,6 | 243,9 | 0,056 | 0,073 | 0,080 / 0,097 |
| 10.000 satır | 3,9 MB | 243,8 | 244,2 | 0,169 | 0,172 | 0,219 / 0,240 |
| 100.000 satır | 38,6 MB | 407,5 | 407,8 | 1,190 | 1,201 | 1,252 / 1,266 |
| 439.792 satır (tüm test kümesi) | 169,6 MB | 1.058,2 | 1.058,3 | 5,105 | 5,126 | 5,172 / 5,198 |

\* Analiz süresi = CSV okuma + doğrulama + ölçekleme + tahmin (arayüzde gösterilen süre).
Uçtan uca = analiz + SQLite kaydı + alarm/log yazımı.

500.000 satırlık dosya üretilmedi: test kümesi 439.792 satır; tekrarlı satırla şişirmek yerine
en büyük dosya olarak tüm test kümesi kullanıldı (kullanıcı kararı).

### 2.2 Streamlit sürecinin kendisi

Kaynak: `reports/hafta10/streamlit_bellek.json`. `streamlit run app.py` her dosya için yeniden
başlatıldı (taze süreç); dosya tarayıcıda yükleme alanına verilip "Analiz et" ile analiz edildi;
bellek psutil ile süreçten okundu. Her dosya **bir kez** ölçüldü.

| Durum | Tepe bellek (MB) | Arayüzde gösterilen analiz süresi (sn) |
| --- | --- | --- |
| Taze süreç, sayfa açılmadan önce | 202,6 | — |
| 100.000 satır (38,6 MB) | 508,7 | 2,19 |
| 439.792 satır (169,6 MB) | 1.290,4 | 6,95 |

Streamlit süreci aynı dosyada komut satırına göre daha fazla bellek kullanıyor (439.792 satırda
1.290,4 MB ve 1.058,2 MB). Bunun nedeni muhtemelen yüklenen dosyanın bayt kopyasının ve sonucun
`session_state`'te tutulmasıdır; ayrıştırılarak ölçülmedi.

**Yükleme sınırı:** `.streamlit/config.toml` → `server.maxUploadSize = 500` MB. En büyük dosya
(tüm test kümesi) 169,6 MB; arayüzde sınır hatası vermeden yüklendi ve analiz edildi.

**N3 sonucu (hedef: tepe bellek < 1,5 GB):** sağlandı. En kötü durum Streamlit sürecinde tüm
test kümesi: 1.290,4 MB (hedefin 245,6 MB altında). Komut satırında en kötü 1.058,3 MB. Hedef
aşılmadığı için parça parça okuma (chunk) uygulanmadı.

## 3. N2 — Gecikme

| Ölçüm | Sonuç | Hedef |
| --- | --- | --- |
| Tek kayıt `predict()` medyanı (N2 tanımı; n_jobs=1, 3 tekrar × 1.000 çağrı, CSV okuma ve ölçekleme hariç) | ortalama 4,48 ms, en kötü tekrar 5,10 ms (%95'lik ≈ 8,5 ms) | < 50 ms ✔ |
| Tek satırlık CSV, uçtan uca analiz (okuma dahil; bkz. 2.1) | ortalama 56 ms, en kötü 73 ms | (N2 tanımı değil) |
| 10.000 satır analiz (bkz. 2.1) | ortalama 0,169 sn, en kötü 0,172 sn | < 5 sn ✔ |

Kaynak: `reports/hafta10/gecikme.json` (`python scripts/measure_memory.py --latency`). Tek satırlık
dosyada sürenin çoğu CSV okuma ve pandas/numpy hazırlığıdır; modelin kendisi ~4,5 ms.

## 4. Oran tabanlı alarm eşiği

### 4.1 Neden?

9. haftadaki sabit eşik (N = 9) 10.000 satırlık dosyalar için seçilmişti. Yanlış saldırı akışı
sayısı dosya boyutuyla orantılı büyüdüğü için büyük dosyalarda yetersiz kalıyordu (aşağıda S0:
eski kuralla 30.000 satırlık normal dosyaların %93,9'unda, 100.000 satırda %100'ünde yanlış KRİTİK).

### 4.2 Kural ve seçim yöntemi

    esik(sınıf, n) = max(N_min, ceil(oran_sınıf × n))      n = analiz edilen akış sayısı

Bir sınıftan `esik`'ten az akış → WARNING + "incelenmeli" (9. haftadaki gibi; tahmin değişmez,
hiçbir tespit gizlenmez). Kural tek yerde: `src/alarm.py::alarm_threshold`.

* **Veri:** yalnızca doğrulama kümesi (351.833 satır). Model 9. hafta ayarlarıyla yalnızca
  alt-eğitimde (1.407.332 satır) eğitildi (`experiments/alarm_threshold.py::validation_predictions`);
  uygulamadaki model doğrulama satırlarını eğitimde gördüğü için kullanılmadı.
* **Parçalar:** boyutlar 1.000 / 3.000 / 10.000 / 30.000 / 100.000 / 250.000 satır; her
  (senaryo, boyut, sınıf, k) hücresi için **2.000 parça**, tohum **42** (her hücrede yeniden).
  Parçadaki (gerçek, tahmin) sayıları karışıklık tablosundan çok değişkenli hipergeometrik
  dağılımla örneklendi (yerine koymadan satır çekmekle aynı dağılım).
* **Senaryolar:** S0 yalnızca Benign; S1 Benign + tek bir saldırı sınıfından k = 10 / 50 / 200
  akış; S2 aynı yapı, k = %0,1 ve %1 × n (yalnızca rapor); S3 doğal dağılım (yalnızca rapor).
* **Ölçüt (önceden yazıldı):** (1) her boyutta S0'da yanlış KRİTİK ≤ %5; (2) bunu sağlayan
  (N_min, oran) adayları içinde S1 ortalama kaçırma oranı en düşük olan; (3) eşitlikte küçük oran,
  sonra küçük N_min. Izgara: N_min 1–50, oran 0–0,002 (0,00001 adım). PortScan ayrı oranla,
  aynı ölçütle (N_min ortak). Sınıf bazında oran: her KRİTİK sınıfın kendi yanlış alarm oranı
  ≤ %1,25; toplam ≤ %5 sağlanır ve S1 kaçırma tek orana göre en az 5 puan düşerse seçilir.
* **Neden ortalama kaçırma?** Planda "en kötü boyuttaki kaçırma" yazıyordu; büyük boyutlarda
  k = 10 akış kısıtı sağlayan her adayda kaçırıldığı için en kötü durum adayları ayırt etmiyor.
  Ortalama 4 KRİTİK sınıf × 3 k × 6 boyut = 72 hücre üzerinden eşit ağırlıkla (PortScan için 18 hücre).
* **Gerekçe:** önce yanlış alarm yükü sınırlanır (sürekli yanlış KRİTİK veren sistem görmezden
  gelinir; 9. haftadaki %5 politikası tüm boyutlara genişletildi), sonra bu sınır içinde gerçek
  saldırıların alarm alma oranı en yükseğe çıkarılır.
* **Yetersiz örnek (kullanıcı kararı: senaryoyu sınırla):** doğrulamada Botnet 230, PortScan 313,
  Web Attack 343, Brute Force 1.464 akış var. k sınıfın havuzundan büyükse hücre ölçülmedi
  (tekrarlı örnekleme yapılmadı). Bu yalnızca S2'yi etkiler (ör. %1 × 100.000 = 1.000 akış:
  Botnet, PortScan, Web Attack). S1'de k ≤ 200 olduğundan tüm hücreler ölçüldü; Botnet k = 200'de
  230 akışın 200'ü çekildiği için o hücrenin değişkenliği düşüktür.
* **Örtüşme:** 100.000 ve 250.000 satırlık S0 parçaları 298.004 satırlık Benign havuzundan
  çekildiği için büyük ölçüde örtüşür (250.000'lik iki parça ortalama ≈ %84 ortak satır); bu
  boyutlardaki S0 oranları bağımsız ölçüm sayılmaz.

### 4.3 Seçim sonucu (doğrulama)

Kaynak: `reports/hafta10/esik_dogrulama_ozet.json`, `esik_dogrulama.md`
(`python experiments/ratio_threshold.py`; aynı tohumla ikinci çalıştırma birebir aynı sonucu verdi).

| Aday | N_min | Oranlar | S1 ortalama kaçırma (KRİTİK) | Kısıtı sağlayan aday |
| --- | --- | --- | --- | --- |
| Tek oran | 9 | KRİTİK 0,00061 | %23,41 | 6.836 |
| **Sınıf bazında (seçilen)** | **9** | **DoS/DDoS 0,00044 · Botnet 0,00101 · Brute Force 0 · Web Attack 0** | **%12,70** | toplam yanlış KRİTİK ≤ %5 sağlandı |
| PortScan | 9 (ortak) | **0,0001** | PortScan S1 ortalama %3,47 | 191 |

Sınıf bazında oran S1 kaçırmayı tek orana göre **10,71 puan** düşürdü (koşul: ≥ 5 puan) ve
seçildi. Brute Force ve Web Attack doğrulamada hiç yanlış alarm üretmediği için (Benign → Brute
Force 0, Benign → Web Attack 0) oranları 0, yani eşikleri sabit 9.

**Seçilen kural:** `config.ALARM_MIN_FLOWS = 9`, `config.ALARM_RATES = {DoS/DDoS: 0,00044,
Botnet: 0,00101, Brute Force: 0, Web Attack: 0, PortScan: 0,0001}`.

### 4.4 Alarm için gereken en az saldırı akışı (= eşik)

| Dosya (satır) | Eski (tüm sınıflar) | DoS/DDoS | PortScan | Brute Force | Web Attack | Botnet |
| --- | --- | --- | --- | --- | --- | --- |
| 1.000 | 9 | 9 | 9 | 9 | 9 | 9 |
| 3.000 | 9 | 9 | 9 | 9 | 9 | 9 |
| 10.000 | 9 | 9 | 9 | 9 | 9 | 11 |
| 30.000 | 9 | 14 | 9 | 9 | 9 | 31 |
| 100.000 | 9 | 44 | 10 | 9 | 9 | 101 |
| 250.000 | 9 | 110 | 25 | 9 | 9 | 253 |
| 439.792 (tüm test kümesi) | 9 | 194 | 44 | 9 | 9 | 445 |

### 4.5 Yanlış alarm (S0: yalnızca Benign parçalar) — eski N=9 ve yeni kural

| Dosya | Doğrulama: yanlış KRİTİK eski / yeni | Doğrulama: yanlış UYARI (PortScan) eski / yeni | **Test:** yanlış KRİTİK eski / yeni | **Test:** yanlış UYARI eski / yeni |
| --- | --- | --- | --- | --- |
| 1.000 | %0,0 / %0,0 | %0,0 / %0,0 | %0,0 / %0,0 | %0,0 / %0,0 |
| 3.000 | %0,0 / %0,0 | %0,0 / %0,0 | %0,0 / %0,0 | %0,0 / %0,0 |
| 10.000 | %3,4 / %0,6 | %0,0 / %0,0 | %2,8 / %0,4 | %0,0 / %0,0 |
| 30.000 | %93,9 / %0,8 | %0,0 / %0,0 | %89,8 / %0,1 | %0,0 / %0,0 |
| 100.000 | %100,0 / %0,0 | %8,2 / %3,1 | %100,0 / %0,0 | %25,1 / **%13,6** |
| 250.000 | %100,0 / %0,0 | %99,9 / %0,0 | %100,0 / %0,0 | %100,0 / %0,0 |

Test kümesinde (uygulamadaki model, 439.792 satır; Benign havuzu 372.506) KRİTİK yanlış alarm
her boyutta ≤ %5 kaldı. **PortScan'de 100.000 satırda yanlış UYARI %13,6** (doğrulamada %3,1):
%5 hedefi test kümesinde tutmadı. Kural test sonucuna göre değiştirilmedi. Not: 10.000 satırda
eski kuralın doğrulama değeri (%3,4) 9. hafta raporundakinden (%2,55) farklı; örnekleme yöntemi
ve parçalar farklı (9. hafta satır satır çekim, bu hafta hipergeometrik), ikisi de aynı %5
sınırının altında.

### 4.6 Kaçırma bedeli (S1: k saldırı akışı eklenmiş Benign dosya)

S1 ortalama kaçırma oranı (tüm boyutlar ve k değerleri, eşit ağırlık):

| Sınıf | Doğrulama eski / yeni | Test eski / yeni |
| --- | --- | --- |
| DoS/DDoS | %0,01 / %15,49 | %0,02 / %17,95 |
| Botnet | %0,55 / %28,38 | %1,27 / %29,33 |
| Brute Force | %1,04 / %1,04 | %0,89 / %0,89 |
| Web Attack | %5,89 / %5,89 | %5,75 / %5,75 |
| KRİTİK ortalama | %1,87 / %12,70 | %1,98 / %13,48 |
| PortScan | %0,26 / %3,47 | %0,24 / %1,00 |

Eski kuralın kaçırma oranı düşük, ama aynı kural büyük dosyalarda neredeyse her normal dosyada
yanlış KRİTİK alarm veriyor (4.5); eski kural ölçütün yanlış alarm kısıtını sağlamıyor.

Yeni kuralın bedelinin yoğunlaştığı hücreler (test kümesi; kaçırma oranı eski / yeni):

| Dosya | k | DoS/DDoS | Botnet | PortScan |
| --- | --- | --- | --- | --- |
| 10.000 | 10 | %0,1 / %0,1 | %0,7 / %8,3 | %1,0 / %1,0 |
| 30.000 | 10 | %0,0 / %22,9 | %0,0 / %99,2 | %0,4 / %0,4 |
| 100.000 | 10 | %0,0 / %100,0 | %0,0 / %100,0 | %0,0 / %0,0 |
| 100.000 | 50 | %0,0 / %0,0 | %0,0 / %98,2 | %0,0 / %0,0 |
| 250.000 | 10 | %0,0 / %100,0 | %0,0 / %100,0 | %0,0 / %13,6 |
| 250.000 | 50 | %0,0 / %100,0 | %0,0 / %100,0 | %0,0 / %0,0 |
| tüm boyutlar | 200 | %0,0 / %0,0 | %0,0 / %0,0 | %0,0 / %0,0 |

Açıkça: **büyük dosyalarda az sayıdaki saldırı artık KRİTİK alarm vermez.** 100.000 satırlık bir
dosyada 10 DoS/DDoS akışı ya da 50 Botnet akışı neredeyse her zaman "incelenmeli" bilgisine düşer
(gizlenmez, kartta ve logda görünür). 200 akışlık saldırılar her boyutta alarm aldı. Brute Force ve
Web Attack için davranış eskisiyle aynı (eşik 9). Küçük boyutlardaki kaçırmalar (ör. Web Attack
k=10'da ~%17) eşikten değil modelin o sınıftaki tespit oranından gelir; eski ve yeni kuralda aynıdır.

**Botnet'in doğal oranındaki durum:** Botnet eşiği akışların binde 1,01'i; Botnet'in veri setindeki
oranı bunun altında (test: 287 / 439.792 ≈ binde 0,65). Bu yüzden doğal dağılımlı büyük dosyalarda
Botnet çoğunlukla "incelenmeli"ye düşer. Gerçek örnek: arayüzde tüm test kümesi analiz edildiğinde
Botnet 419 akışla tespit edildi, eşik 445 olduğu için KRİTİK değil "incelenmeli" gösterildi;
100.000 satırlık dosyada 100 tespit, eşik 101. S3 (doğal dağılım) "düşürülen gerçek saldırı" oranı
da bu yüzden büyük dosyalarda arttı (test: 100.000 satırda %0,0 → %18,3, 250.000 satırda
%0,0 → %23,0; yanlış KRİTİK her boyutta %0,0).

Botnet oranının bu kadar yüksek çıkmasının nedeni kuralın biçimi: 10.000 satırda Botnet'in
yanlış alarmını %1,25'in altında tutmak için eşik 11 gerekiyor; `oran × n` sıfırdan doğrusal
büyüdüğü için bu oran 250.000 satırda gerekenden çok yüksek bir eşik (253) veriyor. Bu bir tasarım
sınırıdır (bkz. 7).

### 4.7 Küçük dosyalarda 9. haftayla aynı mı?

`python scripts/check_demo_files.py hafta10` → `reports/hafta10/demo_sonuclari.csv`. Altı demo
dosyasının hepsinde (demo_normal, demo_ddos, demo_portscan, demo_karma, demo_10000_satir,
demo_bozuk; 455–10.000 akış) yeni kuralın alarmları 9. hafta kuralıyla **birebir aynı**
(`hafta9_ile_ayni = True`). Ayrıca birim testi: 1.000 satırda tüm eşikler N_min = 9'a iner.

### 4.8 Arayüz, log ve veritabanı

* Kart renkleri aynı: kırmızı KRİTİK, turuncu UYARI, gri/mavi incelenmeli
  (kart seçimi `src/alarm.py::card_type`).
* Sonuç sayfası, bu dosyada uygulanan eşikleri yazar, ör. "Alarm eşikleri (bu dosya, 100.000 akış):
  DoS/DDoS 44 (max(9, 0,00044 × 100.000)); PortScan 10 (…); Brute Force 9 (sabit); …".
  İncelenmeli kartı sınıfın kendi eşiğini gösterir.
* Kenar çubuğu: N_min değiştirilebilir, oranlar yalnızca gösterilir.
* `security.log`: incelenmeli satırı 9. haftadaki biçimde (`dusuk_sayi(esik=101) incelenmeli`);
  normal alarm satırlarının sonuna yalnızca ` esik=X` eklendi.
* SQLite tabloları değişmedi; `alarmlar.esik` sütununa artık sınıfın kendi eşiği yazılıyor.

## 5. Testler

`python -m pytest -q` → **80 test, hepsi geçti**; süre iki çalıştırmada 27,84 sn ve 28,59 sn
(9. hafta sonunda 55 test). En uzun testler 8. hafta deney duman testleridir (12,4 sn ve 8,4 sn).

| Dosya | Test | Bu hafta |
| --- | --- | --- |
| tests/test_inference.py | 24 | +9: CSV olmayan dosyalar (zip/xlsx, xls, PNG, PDF, NUL baytı, tutarsız alan sayısı, noktalı virgül), UTF-16, tek satır + fazladan sütun |
| tests/test_e2e.py | 12 | yeni: tam akış (CSV → inference → 3 SQLite tablosu → security.log → kartlar), az akışta incelenmeli kartı, 7 hatalı girdi (Türkçe mesaj, DB ve loga yazılmaz), kısmen bozuk değerler + boşluklu sütun adları, 2 Streamlit AppTest |
| tests/test_alarm.py | 8 | +1: oran tabanlı eşik (eşik büyük dosyada ölçeklenir, küçük dosyada 9'a iner; DB, log ve kart) |
| tests/test_ratio_threshold.py | 3 | yeni: eşik formülü (kayan nokta yuvarlama dahil), yetersiz örnek hücreleri, seçim kısıtı |
| tests/test_experiments.py | 10 | — |
| tests/test_database.py | 8 | — |
| tests/test_followup.py | 5 | — |
| tests/test_alarm_threshold.py | 4 | — |
| tests/test_pipeline.py | 4 | — |
| tests/test_dedup_analysis.py | 2 | — |

Hatalı girdi kapsamı: boş dosya, yalnızca başlık, eksik sütun, fazladan sütun, başında/sonunda
boşluk olan sütun adları, NaN / inf / sayı olmayan değerler, tek satır, CSV olmayan dosya. Hiçbirinde
uygulama çökmedi; başarısız analizler veritabanına ve loga yazılmadı.

**Streamlit duman testi** (`streamlit.testing.v1.AppTest`): sayfa açılır, dosya yükleme alanına
CSV verilip "Analiz et" tıklanır; 4 kırmızı KRİTİK kartı, turuncu port taraması kartı ve eşik
yazısı görünür, analiz geçici veritabanına yazılır. Bozuk dosyada uyarı gösterilir, hata yok.
Testler küçük sahte modelle ve geçici veritabanı / log klasörüyle çalışır (gerçek dosyalara
yazmadıkları doğrulandı).

## 6. Bulunan hatalar ve düzeltmeler

| Bulgu | Önce | Düzeltme |
| --- | --- | --- |
| Zip / Excel .xlsx yüklenince | Sıkıştırmasız zip'in içindeki CSV okunup "45 sütundan 1 tanesi eksik: Flow Duration" gibi yanıltıcı mesaj | İkili dosya imzası tanınır: "Dosya bir CSV metin dosyası değil (zip veya Excel .xlsx)…" |
| Rastgele bayt / PNG | pandas'ın İngilizce iç hatası: "Error tokenizing data. C error: …" | İkili veri olarak tanınır; metin dosyasındaki ayrıştırma hatası "N. satırda başlıktakinden farklı sayıda alan var" diye Türkçe verilir |
| Yalnızca NUL baytlı dosya | "Dosyada başlık satırı var ama veri satırı yok" (yanlış) | "CSV metin dosyası değil (ikili veri)" |
| Noktalı virgüllü CSV (Türkçe Excel) | "45 sütunun hepsi eksik" (asıl neden söylenmiyor) | "Sütunlar virgülle değil, noktalı virgül veya sekmeyle ayrılmış görünüyor…" |
| UTF-16 CSV (Excel "Unicode metin") | "45 sütunun hepsi eksik" | UTF-16 okunur, analiz edilir |
| `app.py` model/log yolları | İçe aktarma anında sabitleniyordu; testler gerçek dosyalara yazabilirdi | Çağrı anında `config`'ten okunur |

## 7. Kalan sınırlar

* **Botnet ve DoS/DDoS için büyük dosyalarda az sayıdaki saldırı KRİTİK alarm almaz** (4.6). Doğal
  oranındaki Botnet, büyük dosyalarda çoğunlukla "incelenmeli"ye düşer (tüm test kümesinde 419 tespit
  / eşik 445). Neden kuralın biçimi `max(N_min, oran × n)`: oran küçük dosyadaki (10.000 satır)
  istatistiksel dalgalanmaya göre seçiliyor, büyük dosyada gereğinden yüksek eşik veriyor. İleride
  düşünülebilecek seçenek: eşiği beklenen yanlış alarm sayısı + dalgalanma payı olarak tanımlamak
  (ör. Poisson üst sınırı). Bu hafta denenmedi.
* **PortScan oranı test kümesinde tutmadı:** 100.000 satırda yanlış UYARI %13,6 (hedef %5,
  doğrulamada %3,1). Muhtemel neden: doğrulamada kullanılan alt-eğitim modeli ile uygulamadaki model
  farklı; uygulamadaki model test kümesinde Benign'i daha sık PortScan sanıyor olabilir. Ölçülmedi.
* Parçalar satırların rastgele örneklenmesiyle oluşturuldu; gerçek trafik dosyalarında saldırılar
  zamanda toplu gelir. 100.000 ve 250.000 satırlık parçalar aynı havuzdan çekildiği için örtüşür.
* Doğrulama ve testte Botnet, PortScan, Web Attack örnekleri az (230–429 akış); S2'nin bazı
  hücreleri ölçülemedi.
* Streamlit bellek ölçümü her dosya için tek kez yapıldı; arayüzdeki süreler tek ölçümdür.
  Streamlit'te belleğin komut satırına göre fazlalığının nedeni ayrıştırılmadı.
* Arayüz ölçümleri uygulamanın gerçek veritabanına (analiz #14–#17) ve `logs/security.log`'a yazıldı.
