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

| Dosya | Satır | Atlanan | Doğruluk | Macro F1* | Alarm (kritik) | Süre (sn) |
| --- | --- | --- | --- | --- | --- | --- |
| demo_normal.csv | 3.000 | 0 | %99,90 | %99,95 | 2 (2) | 0,072 |
| demo_ddos.csv | 3.000 | 0 | %99,70 | %99,57 | 2 (1) | 0,076 |
| demo_portscan.csv | 1.991 | 0 | %99,55 | %99,41 | 3 (2) | 0,069 |
| demo_karma.csv | 3.800 | 0 | %98,42 | %97,63 | 5 (4) | 0,136 |
| demo_10000_satir.csv | 10.000 | 0 | %99,94 | %97,66 | 5 (4) | 0,229 |
| demo_bozuk.csv | 500 | 45 | %97,80 | %96,60 | 5 (4) | 0,058 |
| demo_eksik_sutun.csv | — | — | — | — | — | uyarı: Dosyada modelin ihtiyaç duyduğu 45 sütundan 3 tanesi eksik: Flow Duration, Bwd IAT Total, Fwd IAT Max. CICFlowMeter / CICIDS2017 biçiminde bir CSV yükleyin. |

\* Macro F1, dosyada gerçekte bulunan sınıflar üzerinden hesaplanır.

**10.000 satır:** 0,229 sn (ilk çalıştırma 0,233 sn); N2 hedefi < 5 sn. Arayüzde aynı dosya 0,23 sn gösterdi (tarayıcıdan sunucuya yükleme süresi hariç).

Tarayıcıda ayrıca denenen hatalı girdiler: boş dosya → "Dosya boş." uyarısı; CSV olmayan metin → 45 sütunun eksik olduğunu söyleyen uyarı; `demo_eksik_sutun.csv` → eksik 3 sütunu adıyla sayan uyarı; `demo_bozuk.csv` → 45 bozuk satır nedenleriyle (boş hücre 10, sayıya çevrilemeyen 20, Inf 15) atlandı, kalan 455 satır analiz edildi. Hiçbirinde uygulama çökmedi; başarısız analizler veritabanına yazılmadı.

- `demo_normal.csv` alarmları: DoS/DDoS (2, CRITICAL); Botnet (1, CRITICAL)
- `demo_ddos.csv` alarmları: DoS/DDoS (2393, CRITICAL); PortScan (1, WARNING)
- `demo_portscan.csv` alarmları: DoS/DDoS (4, CRITICAL); Web Attack (1, CRITICAL); PortScan (383, WARNING)
- `demo_karma.csv` alarmları: DoS/DDoS (799, CRITICAL); Brute Force (385, CRITICAL); Web Attack (184, CRITICAL); Botnet (181, CRITICAL); PortScan (195, WARNING)
- `demo_10000_satir.csv` alarmları: DoS/DDoS (1458, CRITICAL); Brute Force (31, CRITICAL); Web Attack (10, CRITICAL); Botnet (6, CRITICAL); PortScan (8, WARNING)
- `demo_bozuk.csv` alarmları: DoS/DDoS (78, CRITICAL); Brute Force (58, CRITICAL); Botnet (25, CRITICAL); Web Attack (18, CRITICAL); PortScan (25, WARNING)

## 3. Dikkat çeken bulgu: normal trafikte yanlış alarm

`demo_normal.csv` yalnızca Benign akış içeriyor; 3.000 akıştan 3'ü saldırı sanıldı (2 DoS/DDoS, 1 Botnet) ve bu 2 KRİTİK alarm üretti. Şu anki kural tek bir akış için bile alarm veriyor. Yanlış alarmların ortalama güveni gerçek saldırılardan düşük (bu dosyada 0,81 ve 0,75; gerçek saldırı sınıflarında çoğunlukla 0,90'ın üstü). Bir alarm eşiği (en az N akış veya en az belirli bir güven) bu yanlış alarmları azaltabilir; bu bir tasarım kararı olduğu için ekibe bırakıldı.

## 4. Eklenen bileşenler

| Dosya | Görev |
| --- | --- |
| `src/inference.py` | CSV doğrulama, bozuk satır ayıklama, tahmin + güven skoru, Label ile karşılaştırma |
| `src/database.py` | SQLite: analizler, sinif_ozetleri, alarmlar (FK açık, parametreli sorgular) |
| `src/alarm.py` | logs/security.log (RotatingFileHandler), sınıf başına tek satır alarm |
| `src/service.py` | analiz akışı: tahmin → veritabanı → alarm |
| `app.py` | Streamlit: Analiz ve Geçmiş Analizler sayfaları |
| `scripts/make_demo_files.py` | test kümesinden demo CSV'leri |
| `scripts/check_demo_files.py` | demo dosyalarını uçtan uca analiz edip süre ölçer |
| `artifacts/model_config.json` | model sürümü, sınıf sırası, Botnet eşiği, eğitim ayarları |

Testler: `python -m pytest -q` (inference, database, alarm testleri dahil).
