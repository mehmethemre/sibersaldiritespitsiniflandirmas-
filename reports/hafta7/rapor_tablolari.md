# 7. Hafta Raporu İçin Otomatik Üretilen Tablolar

Çalıştırma zamanı: 2026-11-25 14:58 · Örneklem oranı: tam veri

## 4.1 Temizlik Sonuçları

| Adım | Kalan Satır | Silinen Satır |
| --- | --- | --- |
| Ham veri (8 CSV birleşik) | 2.830.743 | — |
| Kapsam dışı sınıfların çıkarılması | 2.830.696 | 47 |
| Inf/NaN temizliği | 2.827.829 | 2.867 |
| Tekrarlayan kayıtların silinmesi | 2.198.957 | 628.872 |
| Eğitim kümesi (%80) / Test kümesi (%20) | 1.759.165 / 439.792 | — |

Sabit olduğu için çıkarılan sütun sayısı: 8. Korelasyon elemesinden sonra kalan: 47. Seçilen öznitelik sayısı: **27**.

Seçilen öznitelikler (önem sırasıyla): Bwd Packet Length Max, Average Packet Size, Fwd IAT Max, Fwd IAT Std, Packet Length Variance, Max Packet Length, Idle Min, Flow IAT Std, Flow Duration, ACK Flag Count, PSH Flag Count, FIN Flag Count, Init_Win_bytes_forward, Fwd Header Length.1, Flow IAT Mean, Fwd IAT Mean, Bwd IAT Max, Bwd IAT Total, Down/Up Ratio, Min Packet Length, Fwd Packet Length Max, Fwd PSH Flags, act_data_pkt_fwd, Bwd IAT Std, Avg Fwd Segment Size, Fwd IAT Min, URG Flag Count

## Sınıf Dağılımı

| Sınıf | Eğitim (SMOTE öncesi) | Eğitim (SMOTE sonrası) | Test |
| --- | --- | --- | --- |
| Benign | 1.490.021 | 1.490.021 | 372.506 |
| DoS/DDoS | 257.395 | 257.395 | 64.349 |
| PortScan | 1.565 | 100.000 | 391 |
| Brute Force | 7.320 | 100.000 | 1.830 |
| Web Attack | 1.714 | 100.000 | 429 |
| Botnet | 1.150 | 100.000 | 287 |

SMOTE yöntemi: imblearn.SMOTE

## 4.2 Model Karşılaştırması

| Kriter | Decision Tree | Random Forest | Hedef |
| --- | --- | --- | --- |
| Accuracy | %99,61 | %99,85 | ≥ %95 (N1) |
| Ağırlıklı F1 | %99,64 | %99,85 | — |
| Macro F1 | %87,61 | %93,04 | — |
| Eğitim süresi (sn) | 31,92 | 106,84 | — |
| Tek kayıt gecikmesi, medyan (ms) | 0,070 | 3,528 | < 50 ms (N2) |
| Toplu tahminde akış başına ortalama (ms) | 0,0001 | 0,0014 | — |
| Model dosya boyutu (MB) | 0,14 | 32,75 | — |

## 4.3 Random Forest Sınıf Bazında Başarım

| Sınıf | Precision | Recall | F1 | Test Örnek Sayısı |
| --- | --- | --- | --- | --- |
| Benign | %99,92 | %99,90 | %99,91 | 372.506 |
| DoS/DDoS | %99,86 | %99,61 | %99,74 | 64.349 |
| PortScan | %90,16 | %98,47 | %94,13 | 391 |
| Brute Force | %99,94 | %97,92 | %98,92 | 1.830 |
| Web Attack | %96,99 | %97,67 | %97,33 | 429 |
| Botnet | %53,59 | %93,73 | %68,19 | 287 |

Kritik saldırı sınıflarında F1 ≥ %90 (N1): karşılanmadı → Botnet

## 4.4 Hata Matrisi

Görsel: `reports/confusion_matrix_random_forest.png`. En çok karıştırılan çift: gerçek **Benign** → tahmin **Botnet** (233 örnek).

## Donanım

- isletim_sistemi: Windows 10
- islemci: 12th Gen Intel(R) Core(TM) i5-12500H
- mantiksal_cekirdek: 16
- ram_gb: 31.8
- python: 3.11.9
- pandas: 3.1.1
- numpy: 2.4.6
- scikit_learn: 1.9.1