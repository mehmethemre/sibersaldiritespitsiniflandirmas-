# Ana Pipeline Sonuçları (9. hafta ayarları)

Model sürümü: hafta9-rf-1 · Çakışma modu: sil · SMOTE hedefi: 10.000 · Random Forest Botnet eşiği: 0,30 · ExtraTrees seçimi: kapalı

Çalıştırma zamanı: 2026-11-26 17:31 · Örneklem oranı: tam veri

## 4.1 Temizlik Sonuçları

| Adım | Kalan Satır | Silinen Satır |
| --- | --- | --- |
| Ham veri (8 CSV birleşik) | 2.830.743 | — |
| Kapsam dışı sınıfların çıkarılması | 2.830.696 | 47 |
| Inf/NaN temizliği | 2.827.829 | 2.867 |
| Tekrarlayan kayıtların silinmesi | 2.198.957 | 628.872 |
| Eğitim kümesi (%80) / Test kümesi (%20) | 1.759.165 / 439.792 | — |
| Etiketi çakışan grupların silinmesi (yalnızca eğitim) | 1.758.753 | 412 |

Sabit olduğu için çıkarılan sütun sayısı: 8. Korelasyon elemesinden sonra kalan: 45. Kullanılan öznitelik sayısı: **45**.

Kullanılan öznitelikler: Flow Duration, Bwd IAT Total, Fwd IAT Max, Idle Min, Bwd IAT Max, Fwd IAT Mean, Fwd IAT Std, Bwd IAT Mean, Fwd IAT Min, Bwd IAT Min, Flow IAT Std, Bwd IAT Std, Flow Bytes/s, Idle Std, Flow IAT Mean, Flow IAT Min, Total Length of Bwd Packets, Packet Length Variance, Active Max, Active Mean, Active Min, Fwd Header Length, Active Std, Flow Packets/s, Bwd Packets/s, Init_Win_bytes_forward, Init_Win_bytes_backward, Total Length of Fwd Packets, Max Packet Length, Bwd Packet Length Max, Fwd Packet Length Max, act_data_pkt_fwd, Average Packet Size, Avg Fwd Segment Size, Bwd Packet Length Min, Fwd Packet Length Min, Min Packet Length, Down/Up Ratio, PSH Flag Count, ACK Flag Count, URG Flag Count, Fwd PSH Flags, FIN Flag Count, ECE Flag Count, Fwd URG Flags

## Sınıf Dağılımı

| Sınıf | Eğitim (SMOTE öncesi) | Eğitim (SMOTE sonrası) | Test |
| --- | --- | --- | --- |
| Benign | 1.489.815 | 1.489.815 | 372.506 |
| DoS/DDoS | 257.288 | 257.288 | 64.349 |
| PortScan | 1.496 | 10.000 | 391 |
| Brute Force | 7.320 | 10.000 | 1.830 |
| Web Attack | 1.714 | 10.000 | 429 |
| Botnet | 1.120 | 10.000 | 287 |

SMOTE yöntemi: imblearn.SMOTE

## 4.2 Model Karşılaştırması

| Kriter | Decision Tree | Random Forest | Hedef |
| --- | --- | --- | --- |
| Accuracy | %99,86 | %99,87 | ≥ %95 (N1) |
| Ağırlıklı F1 | %99,87 | %99,87 | — |
| Macro F1 | %93,85 | %93,86 | — |
| Eğitim süresi (sn) | 44,19 | 115,80 | — |
| Tek kayıt gecikmesi, medyan (ms) | 0,075 | 4,711 | < 50 ms (N2) |
| Toplu tahminde akış başına ortalama (ms) | 0,0001 | 0,0019 | — |
| Model dosya boyutu (MB) | 0,13 | 28,99 | — |

## 4.3 Random Forest Sınıf Bazında Başarım (Botnet eşiği uygulanmış)

| Sınıf | Precision | Recall | F1 | Test Örnek Sayısı |
| --- | --- | --- | --- | --- |
| Benign | %99,91 | %99,93 | %99,92 | 372.506 |
| DoS/DDoS | %99,90 | %99,65 | %99,77 | 64.349 |
| PortScan | %92,07 | %97,95 | %94,92 | 391 |
| Brute Force | %99,94 | %97,16 | %98,53 | 1.830 |
| Web Attack | %99,25 | %92,54 | %95,78 | 429 |
| Botnet | %62,53 | %91,29 | %74,22 | 287 |

Kritik saldırı sınıflarında F1 ≥ %90 (N1): karşılanmadı → Botnet

## 4.4 Hata Matrisi

Görsel: `reports/confusion_matrix_random_forest.png`. En çok karıştırılan çift: gerçek **DoS/DDoS** → tahmin **Benign** (216 örnek).

## Donanım

- isletim_sistemi: Windows 10
- islemci: 12th Gen Intel(R) Core(TM) i5-12500H
- mantiksal_cekirdek: 16
- ram_gb: 31.8
- python: 3.11.9
- pandas: 3.1.1
- numpy: 2.4.6
- scikit_learn: 1.9.1