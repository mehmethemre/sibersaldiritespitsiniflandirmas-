# 9. Hafta Özeti — Uygulamanın İlk Çalışan Sürümü

Eğitim zamanı: 2026-11-26 17:31 · tam veri · model sürümü `hafta9-rf-1`

## 1. Seçilen ayarların ana koda işlenmesi

8. hafta doğrulama deneylerinde seçilen yapılandırma `src/config.py` ve `run_pipeline.py`'ye işlendi: etiketi çakışan gruplar eğitimden silinir, ExtraTrees seçimi yok (korelasyon sonrası 45 öznitelik), SMOTE hedefi 10.000, Random Forest parametreleri 7. haftadaki gibi, Botnet karar eşiği 0,30. Model tüm eğitim kümesinde yeniden eğitildi (1.758.753 satır; çakışma işlemi 412 satırı sildi) ve test kümesinde (439.792 satır) değerlendirildi.

| Metrik (test kümesi, Random Forest) | 7. Hafta | 8. Hafta final | 9. Hafta (ana pipeline) |
| --- | --- | --- | --- |
| Accuracy | %99,85 | %99,86 | %99,87 |
| Macro F1 | %93,04 | %93,94 | %93,86 |
| Botnet F1 | %68,19 | %74,04 | %74,22 |
| Botnet Precision | %53,59 | %62,44 | %62,53 |
| Botnet Recall | %93,73 | %90,94 | %91,29 |
| PortScan F1 | %94,13 | %95,29 | %94,92 |
| Benign→Botnet hatası | 233 | 157 | 157 |

**Tutarlılık:** Macro F1 farkı -0,08 puan, Botnet F1 farkı 0,18 puan. Fark küçük ve nedeni belli: 8. hafta finalinde öznitelik kümesi alt-eğitimde seçilmişti, ana pipeline korelasyon elemesini tüm eğitim kümesinde yapıyor. Korelasyonu 0,95 eşiğine çok yakın olan bir çiftte farklı üye kaldı (8. hafta: Bwd Header Length; 9. hafta: Fwd Header Length) ve öznitelik sırası değişti (Random Forest her düğümde rastgele öznitelik alt kümesi seçtiği için sıra sonucu az da olsa etkiler).

Sınıf bazında F1 (test): Benign %99,92, DoS/DDoS %99,77, PortScan %94,92, Brute Force %98,53, Web Attack %95,78, Botnet %74,22.

Diğer ölçümler: Random Forest eğitim süresi 115,8 sn, model dosyası 29,0 MB, tek kayıt tahmin gecikmesi (medyan) 4,71 ms, tüm pipeline 3,44 dk.

Not: Decision Tree temel modeli de SMOTE 10.000 ile güçlendi: Macro F1 %93,85 (7. haftada %87,61), Botnet F1 %71,79; tek kayıt gecikmesi 0,075 ms. Uygulamada Random Forest kullanılıyor.

## 2. Demo dosyalarıyla uçtan uca kontrol

Demo dosyaları test kümesinden üretildi (`scripts/make_demo_files.py`; model bu satırları eğitimde görmedi). Analiz, arayüzün kullandığı akışla (`src/service.py::run_analysis`) yapıldı (`scripts/check_demo_files.py`). Süre = CSV okuma + doğrulama + tahmin; her dosya 3 kez analiz edildi, medyan verildi. Aynı dosyalar Streamlit arayüzünde tarayıcıdan da yüklenerek denendi; sonuçlar ve alarmlar birebir aynıydı.

| Dosya | Satır | Atlanan | Doğruluk | Macro F1* | Süre (sn) |
| --- | --- | --- | --- | --- | --- |
| demo_normal.csv | 3.000 | 0 | %99,90 | %99,95 | 0,075 |
| demo_ddos.csv | 3.000 | 0 | %99,70 | %99,57 | 0,108 |
| demo_portscan.csv | 1.991 | 0 | %99,55 | %99,41 | 0,096 |
| demo_karma.csv | 3.800 | 0 | %98,42 | %97,63 | 0,138 |
| demo_10000_satir.csv | 10.000 | 0 | %99,94 | %97,66 | 0,259 |
| demo_bozuk.csv | 500 | 45 | %97,80 | %96,60 | 0,068 |
| demo_eksik_sutun.csv | — | — | — | — | uyarı: Dosyada modelin ihtiyaç duyduğu 45 sütundan 3 tanesi eksik: Flow Duration, Bwd IAT Total, Fwd IAT Max. CICFlowMeter / CICIDS2017 biçiminde bir CSV yükleyin. |

\* Macro F1, dosyada gerçekte bulunan sınıflar üzerinden hesaplanır.

**10.000 satır:** 0,259 sn (ilk çalıştırma 0,252 sn); N2 hedefi < 5 sn. Arayüzde aynı dosya 0,23 sn gösterdi (tarayıcıdan sunucuya yükleme süresi hariç).

Tarayıcıda ayrıca denenen hatalı girdiler: boş dosya → "Dosya boş." uyarısı; CSV olmayan metin → 45 sütunun eksik olduğunu söyleyen uyarı; `demo_eksik_sutun.csv` → eksik 3 sütunu adıyla sayan uyarı; `demo_bozuk.csv` → 45 bozuk satır nedenleriyle (boş hücre 10, sayıya çevrilemeyen 20, Inf 15) atlandı, kalan 455 satır analiz edildi. Hiçbirinde uygulama çökmedi; başarısız analizler veritabanına yazılmadı.

## 3. Alarm eşiği

İlk sürümde tek bir akış bile KRİTİK alarm üretiyordu; yalnızca Benign içeren `demo_normal.csv` 3 yanlış tahmin yüzünden 2 KRİTİK alarm verdi. Kural eklendi: bir saldırı sınıfı için alarm, o sınıftan en az N akış tespit edilince verilir. N'nin altında kalırsa gri/mavi bir bilgi kartında "düşük sayıda şüpheli akış, incelenmeli" gösterilir ve günlüğe WARNING yazılır; hiçbir tespit gizlenmez. Tahminler, tablo ve sınıf dağılımı değişmez. Arayüzde üç görünüm ayrıdır: kırmızı kart KRİTİK alarm, turuncu kart eşiği geçen WARNING seviyeli alarm (ör. "UYARI: Port taraması tespit edildi (383 akış)"), gri/mavi kart eşik altı "incelenmeli" bilgisi. N `config.ALARM_MIN_FLOWS` ile ayarlanır (varsayılan **9**) ve arayüzün kenar çubuğundan da değiştirilebilir.

**N nasıl seçildi (yalnızca doğrulama kümesi, `experiments/alarm_threshold.py`):** 9. hafta ayarlarıyla yalnızca alt-eğitimde (1.407.332 satır) bir model eğitildi; model, görmediği doğrulama kümesinde (351.833 satır) tahmin yaptı. Uygulamadaki model doğrulama satırlarını eğitimde gördüğü için bu ölçümde kullanılmadı; test kümesine dokunulmadı. Doğrulamadaki 298.004 Benign akışın %0,07'si saldırı sanıldı (DoS/DDoS 69, PortScan 17, Brute Force 0, Web Attack 0, Botnet 128). Bu akışlardan her boyut için 2.000 rastgele "dosya" (parça) çekildi ve her N için kaç dosyada yanlış KRİTİK alarm çıktığı sayıldı. Seçim kuralı sonuçlara bakmadan önce belirlendi: 10.000 satırlık Benign parçalarda yanlış KRİTİK oranı <= %5 olan en küçük N.

Yalnızca normal trafik içeren dosyalarda yanlış KRİTİK alarm çıkan dosya oranı:

| N | 3.000 satır | 10.000 satır | 100.000 satır |
| --- | --- | --- | --- |
| 1 | %86,45 | %99,85 | %100,00 |
| 2 | %45,55 | %97,45 | %100,00 |
| 3 | %16,50 | %88,90 | %100,00 |
| 5 | %1,00 | %47,00 | %100,00 |
| 8 | %0,00 | %6,80 | %100,00 |
| 9 (seçilen) | %0,00 | %2,55 | %100,00 |
| 10 | %0,00 | %0,95 | %100,00 |
| 50 | %0,00 | %0,00 | %10,75 |

**Bedeli:** gerçek saldırı içeren (doğal dağılımlı) rastgele dosyalarda, dosyada gerçekten bulunan bir saldırı sınıfının N'den az akışla tespit edilip "incelenmeli" bilgisine düşme oranı N=9 için 3.000 satırda %51,25, 10.000 satırda %19,98, 100.000 satırda %0,00. Bunlar dosyada çok az akışı olan saldırılardır (satırlar rastgele örneklendiği için nadir sınıflar küçük dosyalarda birkaç akışla temsil edilir); gizlenmez, "incelenmeli" olarak görünür. Gerçek trafikte saldırılar zamanda toplu geldiği için bu oran muhtemelen daha düşüktür, ancak bu ölçülmedi.

**Sınır:** Yanlış saldırı akışı sayısı dosya boyutuyla orantılı büyüdüğü için sabit bir N büyük dosyalarda yetersiz kalır: 100.000 satırlık normal dosyalarda N=9 ile dosyaların %100,00'ünde yanlış KRİTİK alarm çıkıyor; N=50'de bile %10,75. Çok büyük dosyalar için oran tabanlı bir eşik (sınıfın akışların binde kaçı olduğu) daha uygun olur; bu ileride verilecek bir tasarım kararıdır.

**Demo dosyalarında eşiksiz (N=1) ve eşikli (N=9) alarmlar** (tahminler aynı):

| Dosya | KRİTİK (N=1) | KRİTİK (N=9) | İncelenmeli (N=9) | Eşikli alarmlar |
| --- | --- | --- | --- | --- |
| demo_normal.csv | 2 | 0 | 2 | DoS/DDoS 2 incelenmeli; Botnet 1 incelenmeli |
| demo_ddos.csv | 1 | 1 | 1 | DoS/DDoS 2393 CRITICAL; PortScan 1 incelenmeli |
| demo_portscan.csv | 2 | 0 | 2 | PortScan 383 WARNING; DoS/DDoS 4 incelenmeli; Web Attack 1 incelenmeli |
| demo_karma.csv | 4 | 4 | 0 | DoS/DDoS 799 CRITICAL; Brute Force 385 CRITICAL; Web Attack 184 CRITICAL; Botnet 181 CRITICAL; PortScan 195 WARNING |
| demo_10000_satir.csv | 4 | 3 | 2 | DoS/DDoS 1458 CRITICAL; Brute Force 31 CRITICAL; Web Attack 10 CRITICAL; PortScan 8 incelenmeli; Botnet 6 incelenmeli |
| demo_bozuk.csv | 4 | 4 | 0 | DoS/DDoS 78 CRITICAL; Brute Force 58 CRITICAL; Botnet 25 CRITICAL; Web Attack 18 CRITICAL; PortScan 25 WARNING |

Gerçek saldırı dosyalarında (`demo_ddos`, `demo_karma`, `demo_bozuk`) bütün KRİTİK alarmlar eşikle de korunuyor. `demo_normal` ve `demo_portscan`'deki tek tük yanlış KRİTİK alarmlar "incelenmeli"ye düştü. `demo_10000_satir`'da dosyada gerçekten 5 Botnet akışı var; model 6 akışa Botnet dedi ve bu sayı eşiğin altında kaldığı için KRİTİK yerine "incelenmeli" gösterildi: eşiğin bedeli bu tür az akışlı gerçek saldırılardır.

## 4. Eklenen bileşenler

| Dosya | Görev |
| --- | --- |
| `src/inference.py` | CSV doğrulama, bozuk satır ayıklama, tahmin + güven skoru, Label ile karşılaştırma |
| `src/database.py` | SQLite: analizler, sinif_ozetleri, alarmlar (FK açık, parametreli sorgular) |
| `src/alarm.py` | logs/security.log (RotatingFileHandler), sınıf başına tek satır alarm |
| `src/service.py` | analiz akışı: tahmin → veritabanı → alarm |
| `app.py` | Streamlit: Analiz ve Geçmiş Analizler sayfaları |
| `scripts/make_demo_files.py` | test kümesinden demo CSV'leri |
| `scripts/check_demo_files.py` | demo dosyalarını uçtan uca analiz edip süre ölçer; eşikli/eşiksiz alarm karşılaştırması |
| `experiments/alarm_threshold.py` | alarm eşiği N'nin doğrulama kümesinde seçimi |
| `artifacts/model_config.json` | model sürümü, sınıf sırası, Botnet eşiği, eğitim ayarları |

Testler: `python -m pytest -q` (inference, database, alarm testleri dahil).
