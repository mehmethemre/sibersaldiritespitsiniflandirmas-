# 11. Hafta Sonuçları

Tarih: 28.11.2026. Ölçüm bilgisayarı 10. haftayla aynı: i5-12500H, 31,8 GB RAM, Windows 11,
Python 3.11.9, scikit-learn 1.9.1.

**Bu dosyadaki bütün sayılar çalıştırılan koddan alındı.** Her sayının kaynak dosyası başlıklarda
yazıyor. Analizler ve seçimler yalnızca **doğrulama kümesinde** yapıldı. **Test kümesi bu hafta
hiç kullanılmadı**, çünkü denenen iyileştirme benimsenmedi (bkz. 2. bölüm).

Doğrulama modeli: 9. hafta ayarlarıyla yalnızca alt-eğitim kümesinde eğitilen Random Forest
(`experiments/alarm_threshold.py::validation_model`). Alt-eğitim 1.407.332 satır, doğrulama
351.833 satır, 45 öznitelik, Botnet eşiği 0,30. Uygulamadaki model ise tüm eğitim kümesiyle
eğitildi. Bu yüzden bu bölümdeki sayılar uygulama modelinin test sonuçlarıyla aynı değildir.

---

## 1. Botnet – Benign karışıklığı: öznitelik önem analizi

Betikler ve çıktılar:
- `experiments/botnet_importance.py` → `reports/hafta11/botnet_analiz.md`, `onem_tablosu.csv`,
  `gruplar_ceyrekler.csv`, `botnet_analiz_ozet.json` (8,4 dk; bunun 4,4 dk'sı permutation)
- `experiments/botnet_template_check.py` → `reports/hafta11/sablon_kontrol.md`

### 1.1 Dört grup (doğrulama)

| Grup | Tanım | Akış |
| --- | --- | --- |
| TP | Doğru Botnet | 218 |
| FP | Botnet'e kaçan Benign | 128 |
| FN | Benign'e kaçan Botnet | 12 |
| TN | Doğru Benign | 297.790 |

Botnet hiçbir zaman başka bir saldırı sınıfıyla karışmadı (iki yönde de 0 akış). Bu ayarla
doğrulamada Botnet recall %94,78 (218 / 230), precision %63,01 (218 / 346), F1 %75,69.
Macro F1 %94,06.

### 1.2 Genel öznitelik önemi: impurity ve permutation

İki yöntem kullanıldı:
- **Impurity:** RF'nin kendi önemi. Eğitim verisinden hesaplanır (alt-eğitim, SMOTE sonrası).
- **Permutation:** doğrulama kümesinin tamamında (351.833 satır), 5 tekrarla hesaplandı. Puan
  eşik kuralıyla alındı: hem Macro F1 hem Botnet F1. Bir sütun karıştırılınca puanın ne kadar
  düştüğü ölçülür.

**SHAP neden yok:** kurulu değil ve 100 ağaçlı, derinliği 20 olan RF'de yavaş. Yeni bağımlılık
eklemek yerine permutation önemi ve dağılım karşılaştırması seçildi.

Botnet F1 permutation sırasına göre ilk 15 (kaynak `reports/hafta11/botnet_analiz.md`, grafik `onem_karsilastirma.png`):

| # | Öznitelik | Impurity (sıra) | Perm. Macro F1 (sıra) | Perm. Botnet F1 ± std (sıra) |
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

**İki yöntem neden farklı?**
- **Ne ölçtükleri farklı.** Impurity, eğitim sırasında bir özniteliğin bölmelerde sağladığı
  saflık artışıdır. Modelin o sütunu ne kadar kullandığını gösterir, genellemeyi değil.
  Permutation ise sütun bozulunca görülmemiş veride puanın ne kadar düştüğüdür.
- **İlintili sütunlar önemi paylaşır.** Impurity'de 1. sıradaki `Bwd Packet Length Max`
  permutation'da yalnızca 13. sırada. Doğrulamada `Max Packet Length` ile |r| = 0,946 ilintili:
  biri karıştırılınca model ikizini kullanmaya devam ediyor, puan az düşüyor. Benzer örnekler:
  `Flow IAT Std` (impurity 6., perm. Botnet 16.; `Fwd IAT Max` ile |r| = 0,935) ve
  `Fwd IAT Std` (7. → 28.; |r| = 0,916). Tablo: `botnet_analiz.md` → "Impurity'de ilk 10 ve en ilintili ikizleri".
- **Impurity çoğunluk sınıflarına bakar.** Bölmelerin çoğu Benign ve DoS/DDoS gibi büyük
  sınıfları ayırmak için yapılır. Botnet'i ayıran sütunlar az sayıda bölmede kullanılır, bu yüzden
  impurity'de geride kalırlar. `Init_Win_bytes_forward` impurity'de 13., Botnet permutation'da
  1. sırada; `URG Flag Count` 40. → 4.
- **Dağılımdaki fark.** Impurity çok değerli, sürekli sütunlara yanlı olabilir (paket uzunlukları).
  TCP pencere değerleri ise az sayıda ayrık değer alır.

### 1.3 Dört grubun karşılaştırması

Botnet permutation sırasında ilk 10 öznitelik ve betimleme için eklenen 4 sütun.
Hücrede medyan [Q1–Q3]; sıfır oranı. Kaynak `gruplar_ceyrekler.csv`, grafik `dort_grup_dagilim.png`
(log ölçeği, TN için rastgele 50.000 satır, aykırı değerler gizli).

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
| Flow Duration (µs) | 99.448 [67.772–997.331]; %0 | 1.002.336 [996.918–1.019.441]; %0 | 22,5 [5,5–77,5]; %0 | 58.496 [460–4.097.494]; %0 |
| ACK Flag Count | 0 [0–0]; %89 | 0 [0–0]; %88 | 1 [1–1]; %17 | 0 [0–0]; %77 |
| PSH Flag Count | 1 [1–1]; %11 | 1 [1–1]; %12 | 0 [0–0]; %83 | 0 [0–1]; %72 |
| FIN Flag Count | 0 [0–0]; %100 | 0 [0–0]; %100 | 0 [0–0]; %100 | 0 [0–0]; %99 |

**Botnet olasılığı** (medyan [Q1–Q3]): TP 0,955 [0,818–1]; **FP 0,795 [0,644–0,873]**;
FN 0,153 [0,116–0,207]; TN 0 [0–0]. Grafik `botnet_olasilik.png`.

**Eşik duyarlılığı** (yalnızca betimleyici; eşik 8. haftada seçildi, bu tabloyla seçim yapılmadı):

| Botnet eşiği | TP | FP | Kaçan Botnet |
| --- | --- | --- | --- |
| 0,30 | 218 | 128 | 12 |
| 0,50 | 197 | 108 | 33 |
| 0,70 | 179 | 88 | 51 |

**En yakın komşu:** alt-eğitimdeki Benign ve Botnet satırları arasında, ölçekli uzayda en yakın
10 komşuya bakıldı. TN için rastgele 5.000 satır sorgulandı.

| Grup | n | Komşularda Botnet oranı (ort.) | Komşularının çoğu Botnet | En yakın komşu Botnet |
| --- | --- | --- | --- | --- |
| TP | 218 | %66,5 | %59,6 | %71,6 |
| FP | 128 | %34,8 | %16,4 | %43,0 |
| FN | 12 | %6,7 | %8,3 | %8,3 |
| TN | 5.000 | %0,0 | %0,0 | %0,0 |

### 1.4 Yanlış pozitif Benign akışların ortak özelliği: tek bir akış şablonu

FP'lerin çeyrek aralıkları sıfır genişlikte; yani FP'ler neredeyse aynı akışlar. En sık değer
birleşimi (şablon): `Init_Win_bytes_forward` = 8.192, `Init_Win_bytes_backward` = 0, ileri yük
0 bayt, geri yük 18 bayt, `Max Packet Length` = 6. Medyan süre yaklaşık 1,0 sn, saniyede yaklaşık
6 paket, PSH bayrağı 1.

| Küme | Satır | Şablona uyan | Oran |
| --- | --- | --- | --- |
| Doğrulama TP | 218 | 79 | %36,2 |
| **Doğrulama FP** | 128 | **111** | **%86,7** |
| Doğrulama FN | 12 | 1 | %8,3 |
| Doğrulama TN | 297.790 | 132 | %0,04 |
| Alt-eğitim Benign | 1.191.890 | 1.077 | %0,09 |
| Alt-eğitim Botnet | 900 | 315 | %35,00 |

**Şablondaki Benign ve Botnet satırları birebir aynı mı?** Hayır. Karşılaştırma 45 öznitelik
üzerinden yapıldı (`sablon_kontrol.md`):

| Küme | Benign satır | Botnet satır | İki etikette ortak vektör |
| --- | --- | --- | --- |
| Alt-eğitim (çakışma silmeden önce) | 1.077 | 315 | 0 |
| Alt-eğitim (çakışma silindikten sonra) | 1.077 | 315 | 0 |
| Doğrulama | 243 | 80 | 0 |
| Alt-eğitim + doğrulama birlikte | 1.320 | 395 | 0 |

Satırlar birebir aynı değil ama yalnızca zamanlama sütunlarında ayrışıyorlar ve aralıklar
örtüşüyor. Alt-eğitim, medyan [Q1–Q3]:
- `Flow Duration`: Benign 1.045.150 [1.002.570–1.269.500] µs, Botnet 1.009.430 [998.025–1.027.530] µs.
- `Flow IAT Min`: Benign 728 [470–86.584], Botnet 454 [403,5–512].
- `Fwd IAT Mean`: Benign 515.394 [501.014–591.697], Botnet 504.402 [498.652–513.548].

Botnet akışları yaklaşık 1,0 sn ve ~500 ms aralıklarla daha dar bir bantta toplanıyor. Benign
akışlar daha yayılmış ama Botnet bandının üstünü de kapsıyor.

Önceki analizdeki "zıt etiketli birebir eşleşme" ölçümü (FP'lerin %3,1'i, FN'lerin %16,7'si)
45 özniteliğin hepsiyle değil, analiz betiğinin vektörüyle yapılmıştı. Şablona özel kontrol
yukarıdaki tablodur.

### 1.5 Botnet neden akış düzeyinde normal trafikten ayrışmıyor?

Veriye dayanan açıklama:
1. **Hataların çoğu tek bir akış türünden geliyor.** Doğrulamadaki 128 FP'nin 111'i aynı şablona
   uyuyor: ileri yönde yük yok, geri yönde 18 bayt, yaklaşık 1 sn süren kısa bir TCP akışı.
2. **Bu akış türü iki sınıfta da var.** Alt-eğitimde şablonu taşıyan 1.392 satırın 1.077'si
   Benign, 315'i Botnet; Botnet payı yaklaşık %23. Botnet akışlarının %35'i bu şablonda. Yani
   şablon, Botnet'in akışlarında sık görülen ama normal trafikte de bulunan bir akış türü.
3. **İki etiketi ayıran bilgi akış özniteliklerinde zayıf.** Şablon içinde Benign ve Botnet
   satırları yalnızca süre ve paket arası zamanlarda ayrışıyor, aralıklar örtüşüyor. En yakın
   komşulara bakınca FP'lerin %43'ünün en yakın eğitim komşusu Botnet.
4. **SMOTE Botnet'i ağırlaştırıyor.** Botnet 900'den 10.000'e çoğaltıldığı için (~11 kat) model
   bu bölgede Botnet'e yüksek olasılık veriyor. FP'lerin medyan Botnet olasılığı 0,795, yani
   eşiğin çok üstünde. Bu yüzden eşiği yükseltmek FP'yi ancak recall'u da düşürerek azaltıyor
   (1.3'teki duyarlılık tablosu).
5. **Ayırt edici bilgi akışta değil.** Bir Botnet'i normal trafikten ayırabilecek bilgiler
   tek bir akışın özniteliklerinde yok: hangi adrese bağlanıldığı, bağlantıların düzenli
   aralıklarla tekrar etmesi, aynı makinenin diğer akışları. Hedef port da port ezberini önlemek
   için bilinçli olarak çıkarıldı. Bu bir çıkarımdır, bu hafta ölçülmedi.

---

## 2. İyileştirme denemesi: Botnet'e özel SMOTE hedefi

### 2.1 Ölçütün zamanı

Seçim ölçütü deney çalıştırılmadan **önce** yazıldı ve commit edildi:
`reports/hafta11/botnet_secim_olcutu.md` ve CLAUDE.md'deki "11. hafta: Botnet SMOTE denemesi"
bölümü, commit `f7c5d54` (28.11.2026 16:02:05).

Görev listesinde ölçütün "çalıştırmadan önce yazıldığı ama sonradan commit edildiği" yazılması
istenmişti. Git kayıtları bunu doğrulamıyor; ölçüt deneyden **önce** commit edildi:
- %5 örneklemle kod denemesi 16:03:58'de başladı (`reports/hafta11/deneme_frac0.05/`; sayıları kullanılmadı).
- Tam veri çalıştırması 16:05:29'da başladı ve 16:30:45'te bitti (`smote_deneme_log.txt`).

Bilinmesi gereken iki ayrıntı:
- **Önceden bilinen değerler:** ölçüt yazılırken mevcut ayarın doğrulamadaki tek tohumluk değerleri
  (F1 %75,69, recall %94,78) biliniyordu ve ölçüt dosyasına bu haliyle yazıldı.
- **Betik sonra yazıldı:** deney betiği (`experiments/botnet_smote.py`) ölçüt commit'inden sonra
  yazıldı ve deneyle birlikte ayrı bir commit'te (`367fd5e`) kaydedildi. Betik ölçütü olduğu gibi uygular.

### 2.2 Düzen

Ölçütün özeti:
- **Izgara:** Botnet SMOTE hedefi {yok (900), 2.500, 5.000, 10.000} × Botnet eşiği {0,30; 0,50; 0,70}
  × tohum {42, 43, 44}. Tohum hem SMOTE'un hem RF'nin `random_state` değeri.
- **Sabit tutulanlar:** diğer küçük sınıflar her zaman 10.000'e tamamlandı; bölme tohumu 42.
  Yalnızca doğrulama kullanıldı. Toplam 12 RF eğitimi, 25,3 dk.
- **Referans:** R = (10.000; 0,30), yani mevcut ayar. Kontrol için: tohum 42'de mevcut ayar önem
  analizindeki sonucu birebir tekrarladı (F1 0,7569, FP 128).
- **Uygunluk:** ortalama Botnet recall ≥ %90. Botnet dışındaki her sınıfta ortalama F1 en fazla
  0,5 puan düşebilir (R'ye göre). R'nin recall'u %94,93 olduğu için göreli sınır gerekmedi.
- **Seçim ve benimseme:** uygunlar içinde en yüksek ortalama Botnet F1 seçilir. Yeni ayar ancak
  kazanç Δ ≥ 1 puan **ve** Δ > max(std seçilen, std R) ise benimsenir.

### 2.3 Sonuçlar: tüm satırlar (3 tohum ortalaması ± örneklem standart sapması, puan)

Kaynak: `reports/hafta11/smote_deneme_ozet.csv`. Tohum başına ham değerler `smote_deneme_ham.csv`'de.

| Botnet SMOTE | Eşik | Botnet F1 | Botnet recall | Botnet precision | FP Benign→Botnet | FN Botnet→Benign | Macro F1 | Uygun |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| yok (900) | 0,3 | 73,12 ± 0,35 | 78,84 ± 0,91 | 68,18 ± 0,73 | 84,7 ± 3,5 | 48,7 ± 2,1 | 93,51 ± 0,15 | hayır (recall, diğer sınıf F1) |
| yok (900) | 0,5 | 68,82 ± 0,89 | 55,36 ± 1,09 | 90,95 ± 0,40 | 12,7 ± 0,6 | 102,7 ± 2,5 | 92,79 ± 0,26 | hayır (recall, diğer sınıf F1) |
| yok (900) | 0,7 | 65,89 ± 0,19 | 49,28 ± 0,25 | 99,42 ± 0,50 | 0,7 ± 0,6 | 116,7 ± 0,6 | 92,30 ± 0,16 | hayır (recall, diğer sınıf F1) |
| 2.500 | 0,3 | 73,53 ± 0,95 | 86,38 ± 1,65 | 64,01 ± 0,57 | 111,7 ± 1,2 | 31,3 ± 3,8 | 93,73 ± 0,22 | hayır (recall) |
| 2.500 | 0,5 | 72,20 ± 0,41 | 76,23 ± 0,66 | 68,58 ± 0,33 | 80,3 ± 1,2 | 54,7 ± 1,5 | 93,51 ± 0,01 | hayır (recall) |
| 2.500 | 0,7 | 69,80 ± 1,05 | 56,96 ± 1,15 | 90,14 ± 1,03 | 14,3 ± 1,5 | 99,0 ± 2,6 | 93,11 ± 0,16 | hayır (recall) |
| 5.000 | 0,3 | 75,92 ± 0,40 | 92,75 ± 0,91 | 64,26 ± 0,35 | 118,7 ± 2,1 | 16,7 ± 2,1 | 94,07 ± 0,14 | evet |
| 5.000 | 0,5 | 72,36 ± 0,04 | 81,01 ± 0,50 | 65,38 ± 0,39 | 98,7 ± 2,3 | 43,7 ± 1,2 | 93,48 ± 0,07 | hayır (recall) |
| 5.000 | 0,7 | 73,17 ± 0,67 | 72,32 ± 0,66 | 74,06 ± 1,57 | 58,3 ± 5,0 | 63,7 ± 1,5 | 93,61 ± 0,09 | hayır (recall) |
| **10.000 (R)** | **0,3** | **75,72 ± 0,18** | **94,93 ± 0,25** | **62,98 ± 0,15** | **128,3 ± 0,6** | **11,7 ± 0,6** | **94,03 ± 0,07** | **evet** |
| 10.000 | 0,5 | 73,30 ± 0,31 | 84,93 ± 0,66 | 64,47 ± 0,12 | 107,7 ± 0,6 | 34,7 ± 1,5 | 93,62 ± 0,09 | hayır (recall) |
| 10.000 | 0,7 | 72,28 ± 0,22 | 77,83 ± 0,00 | 67,46 ± 0,39 | 86,3 ± 1,5 | 51,0 ± 0,0 | 93,45 ± 0,02 | hayır (recall) |

Botnet dışı sınıfların F1'i (ortalama ± std, puan). Eşik yalnızca Botnet kararını değiştirdiği
için aynı SMOTE hedefinde üç eşik aynı değeri verir.

| Botnet SMOTE | Eşik | Benign | DoS/DDoS | PortScan | Brute Force | Web Attack |
| --- | --- | --- | --- | --- | --- | --- |
| yok (900) | 0,3 | 99,92 ± 0,00 | 99,74 ± 0,00 | 95,05 ± 0,02 | 98,61 ± 0,07 | 94,59 ± 0,90 |
| yok (900) | 0,5 | 99,92 ± 0,00 | 99,74 ± 0,00 | 95,05 ± 0,02 | 98,61 ± 0,07 | 94,59 ± 0,90 |
| yok (900) | 0,7 | 99,92 ± 0,00 | 99,74 ± 0,00 | 95,05 ± 0,02 | 98,61 ± 0,07 | 94,59 ± 0,90 |
| 2.500 | 0,3 | 99,92 ± 0,00 | 99,74 ± 0,00 | 95,15 ± 0,09 | 98,68 ± 0,25 | 95,34 ± 0,32 |
| 2.500 | 0,5 | 99,92 ± 0,00 | 99,74 ± 0,00 | 95,15 ± 0,09 | 98,68 ± 0,25 | 95,34 ± 0,32 |
| 2.500 | 0,7 | 99,92 ± 0,00 | 99,74 ± 0,00 | 95,15 ± 0,09 | 98,68 ± 0,25 | 95,34 ± 0,32 |
| 5.000 | 0,3 | 99,92 ± 0,00 | 99,74 ± 0,00 | 95,05 ± 0,27 | 98,67 ± 0,17 | 95,13 ± 0,16 |
| 5.000 | 0,5 | 99,92 ± 0,00 | 99,74 ± 0,00 | 95,05 ± 0,27 | 98,67 ± 0,17 | 95,13 ± 0,16 |
| 5.000 | 0,7 | 99,92 ± 0,00 | 99,74 ± 0,00 | 95,05 ± 0,27 | 98,67 ± 0,17 | 95,13 ± 0,16 |
| 10.000 (R) | 0,3 | 99,92 ± 0,00 | 99,74 ± 0,00 | 95,05 ± 0,26 | 98,60 ± 0,09 | 95,13 ± 0,41 |
| 10.000 | 0,5 | 99,92 ± 0,00 | 99,74 ± 0,00 | 95,05 ± 0,26 | 98,60 ± 0,09 | 95,13 ± 0,41 |
| 10.000 | 0,7 | 99,92 ± 0,00 | 99,74 ± 0,00 | 95,05 ± 0,26 | 98,60 ± 0,09 | 95,13 ± 0,41 |

### 2.4 Karar

- Uygun adaylar yalnızca (5.000; 0,30) ve (10.000; 0,30). En yüksek ortalama Botnet F1
  **(5.000; 0,30): %75,92 ± 0,40**. R: %75,72 ± 0,18.
- Kazanç Δ = **0,20 puan**. Gerekli: ≥ 1 puan ve > max(0,40; 0,18) = 0,40 puan. İki koşul da
  sağlanmadı, bu yüzden **mevcut ayar (SMOTE 10.000, eşik 0,30) kaldı.**
- **Test kümesi kullanılmadı.** Uygulama, alarm oranları, N2/N3 ve 9. hafta test sonuçları değişmedi.
- **Yorum:** Botnet'i daha az çoğaltmak FP'yi azaltıyor (128,3 → 84,7) ama recall'u daha hızlı
  düşürüyor (%94,93 → %78,84). Bu, 1.5'teki açıklamayla tutarlı: şablon içindeki iki sınıf akış
  düzeyinde ayrışmadığı için örnek ağırlığıyla ancak FP ↔ FN takası yapılabiliyor.

---

## 3. Arayüz değişiklikleri

Kart renkleri, SQLite şeması ve `security.log` biçimi değişmedi.

| Madde | Durum | Açıklama |
| --- | --- | --- |
| Model Hakkında sayfası | yapıldı | Test kümesi sınıf bazında sonuçlar ve hata matrisi (`reports/metrics.json`). Doğrulama kümesi öznitelik önemi (`reports/hafta11/onem_tablosu.csv`) ve bilinen sınırlar. Her tablo ve grafiğin üstünde küme (test / doğrulama) yazıyor; önem grafiğinde yöntem seçilebiliyor ve eksen başlığında yöntem ile küme yazıyor. Sayılar dosyadan okunuyor; dosya yoksa bilgi mesajı çıkıyor. Raporlar başka model sürümüne aitse uyarı veriyor. |
| Eşik / "incelenmeli" açıklaması | yapıldı | "Alarm seviyeleri nasıl belirlenir?" açılır kutusu: formül `eşik = max(9, ⌈oran × n⌉)`, kart renklerinin anlamı ve bu dosyanın tablosu (sınıf, oran, tespit edilen akış, eşik, sonuç). |
| Alarm özetini indir (CSV) | yapıldı | Alarm varsa düğme görünür. Sütunlar: dosya, analiz no, sınıf, akış, seviye, kart, eşik, eşik altı, ortalama güven (`src/alarm.py::alarm_summary`). Alarm filtresi istenen biçimde yapılmadı (ikisinden biri seçildi). |
| Boş durum rehberi | yapıldı | Dosya yüklenmeden önce 3 adımlı kullanım açıklaması ve demo dosyaları tablosu. Tablodaki içerik `demo/demo_icerik.json`'dan okunuyor. Botnet eşiği "0,30" olarak yazılıyor. |
| Tarih biçimi + saat dilimi | yapıldı | Eski kayıtlar `2026-11-26T17:38:12`, yeniler `2026-11-26 18:04:29` biçimindeydi. 13 analiz ve tüm alarm zamanları `security.log` satırlarıyla karşılaştırıldı; ikisi de birebir aynı yerel saat. Saat dilimi düzeltmesi gerekmedi. Biçim değişikliği aynı commit içinde yapılmıştı (`67c40f8`). Yalnızca gösterim `26.11.2026 17:38:12` biçimine çevrildi; veritabanı değişmedi. |
| Hata matrisi ısı haritası | yapıldı | Renk satıra göre normalize (gerçek sınıfın yüzde kaçı o tahmine gitti; köşegen = recall), hücrede ham sayı (Türkçe binlik ayırıcı). Analiz sonucunda ve Model Hakkında'da kullanılıyor. Ekran görüntüleri alınırken bazı x ekseni etiketlerinin gizlendiği görüldü; `labelOverlap=False` ile ayrı bir commit'te düzeltildi. |
| N_min'i Gelişmiş ayarlar'a taşı | yapıldı | Kenar çubuğunda "Gelişmiş ayarlar" açılır kutusu. Varsayılandan farklı N_min seçilirse sonuçta not gösteriliyor. |

Yeni AppTest testleri: eşik açıklama tablosu, ısı haritası, Model Hakkında (dosya var / yok),
tarih biçimi, alarm özeti düğmesi (alarm var / yok), boş durum rehberi, N_min notu.

**Düzeltilen test hatası:** `test_app_alarm_summary_download_only_with_alarms` ilk yazıldığında
başarısızdı. Hata testteydi, kodda değil. `make_flows` satırları karıştırdığı için
`Label.iloc[0]` BENIGN değil rastgele bir sınıftı. Test aslında tek bir saldırı sınıfından oluşan
bir dosya yüklüyordu ve orada alarm düğmesinin görünmesi doğru davranıştı. Filtre açıkça
`BENIGN` yapıldı. Beklenti gevşetilmedi; ayrıca "saldırı tespit edilmedi" kartı da kontrol ediliyor.

---

## 4. Ekran görüntüleri (`docs/img/`, 1440 piksel genişlik)

Uygulama headless Chrome ile çalıştırılarak alındı.

| Dosya | İçerik | Rapor |
| --- | --- | --- |
| `01_ana_sayfa_bos_durum.png` | Ana sayfa, boş durum rehberi ve demo dosyaları | 9 / 11 |
| `02_demo_karma_kritik_kartlar.png` | `demo_karma.csv`: 4 kırmızı KRİTİK kart + turuncu PortScan kartı | 9 |
| `03_demo_karma_hata_matrisi.png` | `demo_karma.csv`: gerçek etiketlerle karşılaştırma ve ısı haritası | 9 / 11 |
| `04_demo_portscan_uyari_karti.png` | `demo_portscan.csv`: turuncu UYARI kartı, incelenmeli kartları, eşik tablosu | 9 / 10 |
| `05_100bin_satir_esik_tablosu.png` | 100.000 satırlık dosya: oranlı eşikler, Botnet 100 akış / eşik 101 → incelenmeli | 10 |
| `06_tum_test_kumesi_botnet_incelenmeli.png` | Tüm test kümesi: Botnet "incelenmeli" kartı ve eşik tablosu | 10 |
| `07_csv_olmayan_dosya_uyarisi.png` | Uzantısı `.csv` olan zip dosyası: Türkçe uyarı, çökme yok | 10 |
| `08_gecmis_analizler.png` | Geçmiş Analizler (tek tarih biçimi) | 9 |
| `09_model_hakkinda_basarim.png` | Model Hakkında: test kümesi sonuçları ve hata matrisi | 11 |
| `10_model_hakkinda_oznitelik_onemi.png` | Model Hakkında: öznitelik önemi (doğrulama) ve bilinen sınırlar | 11 |

Görüntüler için yapılan 5 analiz (#18–#22) gerçek veritabanına ve `security.log`'a yazıldı.
Görüntülerden sonra 10. haftadaki gibi temizlendi:
- **Yedek:** görüntülerden önce `data/yedek_hafta11/` klasörüne alınan yedek geri yüklendi.
- **Kontrol:** önce yalnızca yeni satır eklendiği doğrulandı (5 analiz, 28 sınıf özeti, 23 alarm,
  23 log satırı; eski satırlar değişmemiş).
- **Görüntü sonrası hal:** `data/yedek_hafta11/ekran_sonrasi_*` olarak saklandı. Klasör gitignore'da.

Geçmişte yine yalnızca 13 demo analizi var.

Görüntülerdeki alarm sayıları önceki haftalarla tutarlı:
- `demo_karma.csv`: DoS/DDoS 799, Brute Force 385, Web Attack 184, Botnet 181, PortScan 195.
  9. hafta `security.log` kayıtlarıyla aynı.
- Tüm test kümesi: Botnet 419 tespit / eşik 445. 10. hafta ile aynı.

---

## 5. Testler

`python -m pytest -q`: **97 test, hepsi geçti**. İki çalıştırmada 33,48 sn ve 33,74 sn sürdü;
10. haftada 80 test 27,84–28,59 sn sürüyordu.

Yeni 17 test:
- `tests/test_botnet_importance.py` (+4): grup ayırma, birebir eşleşme oranı, çeyrekler, şablon karşılaştırması.
- `tests/test_experiments.py` (+4): `oversample` varsayılan parametrelerle eski mantığın birebir
  kopyasıyla aynı (4 hedef değeri). Ayrıca mevcut SMOTE testi sınıf bazında hedef ve tohum için genişletildi.
- `tests/test_alarm.py` (+1): alarm özeti tablosu.
- `tests/test_e2e.py` (+8, AppTest): eşik tablosu, ısı haritası, Model Hakkında (dosya yok / var),
  tarih biçimi, alarm özeti düğmesi, boş durum rehberi, N_min notu.

Mevcut 80 testin hiçbiri değiştirilmedi. Tek değişiklik `app_env` fikstürünün `REPORTS_DIR` ve
`DEMO_DIR`'i geçici klasöre çevirmesi; arayüz testleri gerçek rapor dosyalarına bağlı kalmasın diye.

---

## 6. Diğer işler

- **README.md baştan düzenlendi:** amaç, veri seti, sızıntısız pipeline, 7. ve 9. hafta test
  sonuçları, 10. hafta N2/N3, alarm kuralı, Windows kurulumu, testler, bilinen sınırlar ve ekran görüntüleri.
- **Canlı demo planı** (`docs/canli_demo_plani.md`, yalnızca plan, kurulum yapılmadı):
  VirtualBox host-only ağ, nmap taramaları, CICFlowMeter, uygulamaya yükleme. 45 öznitelik için
  CICFlowMeter Java 4.0 ve Python `cicflowmeter` sütun adı karşılıkları tablosu var, **doğrulanmadı**
  diye işaretli. Birim, akış zaman aşımı ve bayrak sayaçları için kontrol listesi de içeriyor.
- **`oversample` değişikliği:** sınıf bazında hedef (`class_targets`) ve tohum (`random_state`)
  parametreleri eklendi. Varsayılan parametrelerle eski mantığın birebir kopyasıyla aynı çıktıyı
  verdiği 4 hedef değeriyle test edildi (`tests/test_experiments.py`).

## 7. Kalan sınırlar

- **Botnet:** test F1 %74,22 (9. hafta). N1'in kritik sınıflarda F1 ≥ %90 koşulu karşılanmıyor.
  Bu hafta denenen SMOTE ayarı anlamlı kazanç sağlamadı. Akış düzeyinde ayırt edici bilgi yok
  gibi görünüyor (1.5). Bağlantı tekrarı veya hedef adres gibi akışlar arası öznitelikler
  bu projenin kapsamı dışında kaldı.
- **PortScan eşiği:** 100.000 satırda testte yanlış UYARI %13,6 (10. hafta); değişmedi.
- **Büyük dosyada eşik:** tüm test kümesinde doğal orandaki Botnet KRİTİK almıyor.
  `max(N_min, oran × n)` biçiminin yerine Poisson üst sınırı gibi bir kural hâlâ aday.
- **Aynı veri setinden test:** canlı demo yapılmadı. CICFlowMeter sütun eşlemesi doğrulanmadı.
- **Doğrulama modeli farkı:** analizler alt-eğitim modeliyle yapıldı; uygulamadaki model tüm
  eğitimle eğitildi. Önem sıraları benzer olmalı ama birebir aynı olmayabilir.
