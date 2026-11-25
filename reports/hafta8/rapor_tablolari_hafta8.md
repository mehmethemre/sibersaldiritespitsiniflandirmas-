# 8. Hafta Raporu İçin Otomatik Üretilen Tablolar

Çalıştırma zamanı: 2026-11-25 21:00 · Örneklem oranı: tam veri · Toplam süre: 37,1 dk

## Deney Düzeni

| Küme | Satır |
| --- | --- |
| Eğitim (%80) | 1.759.165 |
| → Alt-eğitim (eğitimin %80'i) | 1.407.332 |
| → Doğrulama (eğitimin %20'si) | 351.833 |
| Test (%20, 7. haftayla aynı) | 439.792 |

Tüm karşılaştırmalar doğrulama kümesinde yapıldı; seçim ölçütü doğrulama Macro F1. Test kümesi yalnızca en sonda seçilen tek yapılandırma için bir kez kullanıldı. Yüklemede birebir kopya olan `Fwd Header Length.1` sütunu silindi.

Öznitelik kümesi Deney 1'de alt-eğitimde bir kez seçildi ve sonraki tüm deneylerde ve finalde sabit tutuldu (26 öznitelik). Neden: ilk denemede Deney 2'de seçim her modda yeniden yapılınca, 254 satırlık değişiklik bile seçilen kümeyi değiştirdi (`Fwd IAT Min` düştü) ve Web Attack F1 sert düştü; etki çakışma işleminden değil seçimin kararsızlığından geliyordu.

Sabit öznitelikler: Average Packet Size, Bwd Packet Length Max, Fwd IAT Std, Fwd IAT Max, Idle Min, Packet Length Variance, Max Packet Length, Flow Duration, Flow IAT Std, ACK Flag Count, Init_Win_bytes_forward, FIN Flag Count, PSH Flag Count, Bwd IAT Total, Bwd IAT Max, Down/Up Ratio, Fwd IAT Mean, Avg Fwd Segment Size, Flow IAT Mean, Fwd Packet Length Max, Min Packet Length, Total Length of Fwd Packets, act_data_pkt_fwd, URG Flag Count, Fwd PSH Flags, Fwd IAT Min

## Deney 1 — SMOTE Düzeyi (Random Forest, port yok, doğrulama kümesi)

| Ayar | Accuracy | Macro F1 | Botnet F1 | Botnet Precision | Botnet Recall | PortScan F1 | Benign→Botnet | Eğitim (sn) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SMOTE 100.000 | %99,83 | %92,11 | %67,27 | %51,63 | %96,52 | %92,95 | 208 | 86,8 |
| SMOTE 25.000 | %99,84 | %92,79 | %71,12 | %57,72 | %92,61 | %94,06 | 156 | 71,2 |
| SMOTE 10.000 | %99,84 | %93,15 | %72,10 | %59,94 | %90,43 | %95,06 | 139 | 71,3 |
| SMOTE yok + class_weight=balanced | %99,20 | %77,61 | %19,50 | %10,82 | %99,13 | %94,06 | 1.880 | 53,8 |
| SMOTE yok | %99,86 | %92,48 | %68,31 | %91,91 | %54,35 | %95,40 | 11 | 72,3 |

Botnet precision'ın SMOTE hedefine göre değişimi: 100.000: %51,63 → 25.000: %57,72 → 10.000: %59,94. SMOTE yok: %91,91; SMOTE yok + balanced: %10,82.

Seçilen ayar (en yüksek doğrulama Macro F1): **SMOTE 10.000**

| ayar | F1 Benign | F1 DoS/DDoS | F1 PortScan | F1 Brute Force | F1 Web Attack | F1 Botnet |
| --- | --- | --- | --- | --- | --- | --- |
| SMOTE 100.000 | %99,91 | %99,70 | %92,95 | %99,76 | %93,05 | %67,27 |
| SMOTE 25.000 | %99,91 | %99,70 | %94,06 | %98,62 | %93,35 | %71,12 |
| SMOTE 10.000 | %99,91 | %99,71 | %95,06 | %98,61 | %93,50 | %72,10 |
| SMOTE yok + class_weight=balanced | %99,53 | %99,69 | %94,06 | %98,28 | %54,61 | %19,50 |
| SMOTE yok | %99,92 | %99,72 | %95,40 | %98,54 | %93,00 | %68,31 |

## Deney 2 — Etiketi Çakışan Satırlar (yalnızca alt-eğitimde)

Çakışma: `Destination Port` hariç tüm öznitelikleri birebir aynı, sınıfı farklı satır grubu. Çoğunluk oyu ham veri kopya sayısıyla verilir; oyları eşit olan grup silinir. Doğrulama kümesine dokunulmadı.

| Yöntem | Çakışan grup | Çakışan satır | Silinen satır | Eşit oylu grup | Accuracy | Macro F1 | Botnet F1 | Botnet Precision | Botnet Recall | PortScan F1 | Benign→Botnet | Eğitim (sn) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Olduğu gibi bırak | 127 | 254 | 0 | 0 | %99,84 | %93,15 | %72,10 | %59,94 | %90,43 | %95,06 | 139 | 80,8 |
| Çakışan grupları sil | 127 | 254 | 254 | 0 | %99,85 | %93,21 | %72,32 | %60,06 | %90,87 | %95,21 | 139 | 78,8 |
| Çoğunluk etiketine ata | 127 | 254 | 143 | 16 | %99,84 | %93,07 | %71,75 | %59,65 | %90,00 | %95,21 | 140 | 75,1 |

Seçilen yöntem: **Çakışan grupları sil**

## Deney 3 — Port Bilgisi

> **Not:** Port tekrar silmeden önce eklendiği için her varyantta farklı satırlar silinir ve bölme değişir. Doğrulama kümeleri birebir aynı **değildir**; karşılaştırma yaklaşık yorumlanmalıdır. Tüm varyantlarda Deney 1'deki sabit öznitelik kümesi kullanıldı; port sütunu bu kümeye zorla eklendi. (Küme port yok varyantının alt-eğitiminde seçildiği için B/C doğrulama kümeleriyle küçük bir örtüşme olabilir.)

| Varyant | Tekrar silinen | Alt-eğitim | Doğrulama | Doğrulamada Botnet | Accuracy | Macro F1 | Botnet F1 | Botnet Precision | Botnet Recall | PortScan F1 | Benign→Botnet | Eğitim (sn) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A) Port yok (mevcut) | 628.872 | 1.407.332 | 351.833 | 230 | %99,85 | %93,21 | %72,32 | %60,06 | %90,87 | %95,21 | 139 | 78,2 |
| B) Ham Destination Port | 329.896 | 1.598.676 | 399.670 | 312 | %99,87 | %95,43 | %76,03 | %64,79 | %91,99 | %99,43 | 156 | 84,9 |
| C) Port kategorisi (0-1023 / 1024-49151 / 49152+) | 610.329 | 1.419.200 | 354.800 | 236 | %99,87 | %93,89 | %71,55 | %59,83 | %88,98 | %94,40 | 141 | 72,7 |

Port, CLAUDE.md'deki tasarım kararı gereği final seçimine dahil edilmedi (port ezberi riski); bu deney yalnızca bilgi amaçlıdır.

## Deney 4 — Hiperparametre Araması (RandomizedSearchCV)

imblearn Pipeline(StandardScaler → SMOTE → RandomForest), alt-eğitimden katmanlı 300.000 satırlık örneklem, 3 katlı StratifiedKFold, scoring=f1_macro, 20 deneme. Katta SMOTE hedefi: 1.421. Arama süresi: 14,3 dk.

| Parametre | Denenen değerler | En iyi |
| --- | --- | --- |
| n_estimators | 100, 200, 300 | 300 |
| max_depth | 10, 20, 30, None | 30 |
| min_samples_split | 2, 5, 10 | 10 |
| min_samples_leaf | 1, 2, 4 | 2 |
| max_features | sqrt, log2, 0.5 | sqrt |

En iyi CV Macro F1: %92,85. Tüm denemeler: `deney4_arama_sonuclari.csv`. Not: öznitelik seçimi aramadan önce tüm alt-eğitimde yapıldığı için CV skoru hafif iyimser olabilir; asıl karşılaştırma doğrulama kümesindedir.

## Deney 5 — Model Karşılaştırması (doğrulama kümesi)

| Model | Accuracy | Macro F1 | Botnet F1 | Botnet Precision | Botnet Recall | PortScan F1 | Benign→Botnet | Eğitim (sn) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Random Forest (ayarlanmış) | %99,86 | %93,10 | %71,43 | %61,71 | %84,78 | %95,37 | 121 | 210,6 |
| LightGBM | %99,86 | %92,81 | %69,59 | %55,58 | %93,04 | %94,03 | 171 | 85,4 |

LightGBM parametreleri: {'n_estimators': 500, 'learning_rate': 0.05, 'num_leaves': 63, 'random_state': 42, 'n_jobs': -1, 'verbose': -1}

| model | F1 Benign | F1 DoS/DDoS | F1 PortScan | F1 Brute Force | F1 Web Attack | F1 Botnet |
| --- | --- | --- | --- | --- | --- | --- |
| Random Forest (ayarlanmış) | %99,92 | %99,76 | %95,37 | %98,61 | %93,50 | %71,43 |
| LightGBM | %99,92 | %99,78 | %94,03 | %99,32 | %94,20 | %69,59 |

## Final — Test Kümesi (tek değerlendirme)

Seçilen yapılandırma: **Random Forest (7. hafta parametreleri)**, dengesizlik: SMOTE 10.000, çakışma: Çakışan grupları sil, port yok. Tüm eğitim kümesinde yeniden eğitildi (26 öznitelik).

| Metrik | 7. Hafta | 8. Hafta (final) | Fark (puan) |
| --- | --- | --- | --- |
| Accuracy | %99,85 | %99,86 | 0,01 |
| Macro F1 | %93,04 | %93,65 | 0,61 |
| Botnet F1 | %68,19 | %73,20 | 5,01 |
| PortScan F1 | %94,13 | %95,18 | 1,05 |
| Benign→Botnet hatası | 233 | 153 | -80 |

7. hafta: DT/RF, SMOTE 100.000, çakışma işlemi yok; `Fwd Header Length.1` o zaman veri içindeydi.

| Sınıf | F1 (test) |
| --- | --- |
| Benign | %99,92 |
| DoS/DDoS | %99,76 |
| PortScan | %95,18 |
| Brute Force | %98,56 |
| Web Attack | %95,26 |
| Botnet | %73,20 |

Hata matrisi: `hata_matrisi_final.png`.
