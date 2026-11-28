# Botnet – Benign öznitelik önem analizi (doğrulama kümesi)

Alt-eğitim 1.407.332 satır, doğrulama 351.833 satır, 45 öznitelik, Botnet eşiği 0,30.

| Grup | Akış |
| --- | --- |
| TP — Doğru Botnet | 218 |
| FP — Botnet'e kaçan Benign | 128 |
| FN — Benign'e kaçan Botnet | 12 |
| TN — Doğru Benign | 297.790 |

Botnet → diğer saldırı: yok · diğer saldırı → Botnet: yok

Temel puan: Macro F1 0,941, Botnet F1 0,757. Permutation: 5 tekrar, 4.4 dk.

## Öznitelik önemi (Botnet F1 permutation sırasına göre ilk 15)

| # | Öznitelik | Impurity (sıra) | Perm. Macro F1 (sıra) | Perm. Botnet F1 (sıra) |
| --- | --- | --- | --- | --- |
| 1 | Init_Win_bytes_forward | 0,0229 (13) | 0,0145 (4) | 0,0397 ± 0,00431 (1) |
| 2 | Init_Win_bytes_backward | 0,0341 (9) | 0,0166 (2) | 0,0309 ± 0,00428 (2) |
| 3 | Flow Packets/s | 0,00944 (24) | 0,0073 (7) | 0,0297 ± 0,00219 (3) |
| 4 | URG Flag Count | 0,00224 (40) | 0,00831 (5) | 0,0278 ± 0,00171 (4) |
| 5 | Total Length of Bwd Packets | 0,081 (4) | 0,00741 (6) | 0,013 ± 0,0033 (5) |
| 6 | Packet Length Variance | 0,12 (2) | 0,00527 (9) | 0,0114 ± 0,00277 (6) |
| 7 | Total Length of Fwd Packets | 0,0391 (8) | 0,00408 (10) | 0,01 ± 0,00194 (7) |
| 8 | Average Packet Size | 0,082 (3) | 0,00528 (8) | 0,00641 ± 0,00363 (8) |
| 9 | Max Packet Length | 0,052 (5) | 0,00276 (17) | 0,00579 ± 0,00229 (9) |
| 10 | Fwd Packet Length Max | 0,0228 (14) | 0,00304 (15) | 0,00577 ± 0,00328 (10) |
| 11 | Fwd Packet Length Min | 0,00686 (28) | 0,00133 (23) | 0,00554 ± 0,000427 (11) |
| 12 | Bwd Packet Length Min | 0,0124 (21) | 0,0019 (21) | 0,005 ± 0,00299 (12) |
| 13 | Bwd Packet Length Max | 0,126 (1) | 0,00149 (22) | 0,00457 ± 0,00351 (13) |
| 14 | Bwd IAT Min | 0,00483 (36) | 0,00383 (12) | 0,00397 ± 0,00307 (14) |
| 15 | Bwd IAT Max | 0,00525 (34) | 0,000766 (26) | 0,00378 ± 0,00522 (15) |

## Impurity'de ilk 10 ve en ilintili ikizleri (doğrulama, |r|)

| Öznitelik | Impurity sırası | Perm. Botnet sırası | En ilintili | abs r |
| --- | --- | --- | --- | --- |
| Bwd Packet Length Max | 1 | 13 | Max Packet Length | 0,946 |
| Packet Length Variance | 2 | 6 | Max Packet Length | 0,895 |
| Average Packet Size | 3 | 8 | Max Packet Length | 0,913 |
| Total Length of Bwd Packets | 4 | 5 | act_data_pkt_fwd | 0,792 |
| Max Packet Length | 5 | 9 | Bwd Packet Length Max | 0,946 |
| Flow IAT Std | 6 | 16 | Fwd IAT Max | 0,935 |
| Fwd IAT Std | 7 | 28 | Fwd IAT Max | 0,916 |
| Total Length of Fwd Packets | 8 | 7 | act_data_pkt_fwd | 0,657 |
| Init_Win_bytes_backward | 9 | 2 | URG Flag Count | 0,176 |
| Fwd IAT Max | 10 | 20 | Idle Min | 0,947 |

## Dört grubun dağılımı (medyan [Q1–Q3]; sıfır oranı)

| Öznitelik | TP | FP | FN | TN |
| --- | --- | --- | --- | --- |
| Init_Win_bytes_forward | 8.192 [8.192–8.192]; %0 | 8.192 [8.192–8.192]; %0 | 734 [243–3.041]; %0 | 60 [-1–8.192]; %1 |
| Init_Win_bytes_backward | 237 [0–237]; %36 | 0 [0–0]; %88 | 256 [251–256]; %8 | -1 [-1–243]; %4 |
| Flow Packets/s | 79 [6,02–106]; %0 | 5,99 [5,89–6,02]; %0 | 90.000 [28.527–375.000]; %0 | 65,6 [3,15–5.464]; %0 |
| URG Flag Count | 0 [0–0]; %89 | 0 [0–0]; %89 | 1 [0–1]; %33 | 0 [0–0]; %91 |
| Total Length of Bwd Packets | 134 [18–134]; %0 | 18 [18–18]; %0 | 6 [6–6]; %0 | 172 [46–468]; %17 |
| Packet Length Variance | 4.699 [10,3–5.712]; %11 | 10,3 [10,3–10,3]; %12 | 0 [0–0]; %83 | 1.240 [76,8–25.851]; %19 |
| Total Length of Fwd Packets | 206 [0–207]; %36 | 0 [0–0]; %88 | 6 [6–6]; %8 | 74 [45–376]; %10 |
| Average Packet Size | 39,7 [3–48,7]; %0 | 3 [3–3]; %0 | 9 [9–9]; %0 | 85 [39,2–146]; %10 |
| Max Packet Length | 194 [6–195]; %0 | 6 [6–6]; %0 | 6 [6–6]; %0 | 111 [47–517]; %10 |
| Fwd Packet Length Max | 194 [0–195]; %36 | 0 [0–0]; %88 | 6 [6–6]; %8 | 44 [31–201]; %10 |
| Flow Duration | 99.448 [67.772–997.331]; %0 | 1.002.336 [996.918–1.019.441]; %0 | 22,5 [5,5–77,5]; %0 | 58.496 [460–4.097.494]; %0 |
| ACK Flag Count | 0 [0–0]; %89 | 0 [0–0]; %88 | 1 [1–1]; %17 | 0 [0–0]; %77 |
| PSH Flag Count | 1 [1–1]; %11 | 1 [1–1]; %12 | 0 [0–0]; %83 | 0 [0–1]; %72 |
| FIN Flag Count | 0 [0–0]; %100 | 0 [0–0]; %100 | 0 [0–0]; %100 | 0 [0–0]; %99 |

## Botnet olasılığı (medyan [Q1–Q3])

- TP: 0,955 [0,818–1], n=218
- FP: 0,795 [0,644–0,873], n=128
- FN: 0,153 [0,116–0,207], n=12
- TN: 0 [0–0], n=297.790

## Yanlış sınıflanan akışlar neye benziyor?

Alt-eğitimin Benign + Botnet satırları arasında (ölçekli uzay) en yakın 10 komşu. TN için rastgele 5.000 satır sorgulandı.

| Grup | n | Komşularda Botnet oranı (ort.) | Komşularının çoğu Botnet | En yakın komşu Botnet | En yakın uzaklık (medyan) |
| --- | --- | --- | --- | --- | --- |
| TP | 218 | %66,5 | %59,6 | %71,6 | 3,58e-05 |
| FP | 128 | %34,8 | %16,4 | %43,0 | 2,9e-05 |
| FN | 12 | %6,7 | %8,3 | %8,3 | 0,00139 |
| TN | 5.000 | %0,0 | %0,0 | %0,0 | 0,00038 |

Zıt etiketli birebir eşleşme (tekrar silme tüm veride yapıldığı için aynı etiketli eşleşme tanım gereği olamaz):

- FP vektörlerinin alt-eğitimde birebir **Botnet** olarak geçme oranı %3,1
- FN vektörlerinin alt-eğitimde birebir **Benign** olarak geçme oranı %16,7

(İlk 10'dan sonraki satırlar önem sırasından değil, betimleme için eklendi: Flow Duration, ACK Flag Count, PSH Flag Count, FIN Flag Count.)

## FP şablonu

FP akışlarda en sık görülen değer birleşimi: Init_Win_bytes_forward = 8.192, Init_Win_bytes_backward = 0, Total Length of Fwd Packets = 0, Total Length of Bwd Packets = 18, Max Packet Length = 6.

| Küme | Satır | Şablona uyan | Oran |
| --- | --- | --- | --- |
| Doğrulama TP | 218 | 79 | %36,2 |
| Doğrulama FP | 128 | 111 | %86,7 |
| Doğrulama FN | 12 | 1 | %8,3 |
| Doğrulama TN | 297.790 | 132 | %0,0 |
| Alt-eğitim Benign | 1.191.890 | 1.077 | %0,09 |
| Alt-eğitim Botnet | 900 | 315 | %35,00 |

## Eşik duyarlılığı (yalnızca betimleyici; eşik 8. haftada seçildi)

| Botnet eşiği | TP | FP (Benign→Botnet) | Kaçan Botnet |
| --- | --- | --- | --- |
| 0,3 | 218 | 128 | 12 |
| 0,5 | 197 | 108 | 33 |
| 0,7 | 179 | 88 | 51 |

Süre: 8.4 dk. Grafikler: onem_karsilastirma.png, dort_grup_dagilim.png, botnet_olasilik.png
