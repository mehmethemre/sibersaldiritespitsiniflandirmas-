# Botnet SMOTE hedefi denemesi — seçim ölçütü (11. hafta)

Bu dosya deney çalıştırılmadan ÖNCE yazıldı ve commit edildi. Deney sonuçlarına göre
değiştirilmez. Deney betiği: `experiments/botnet_smote.py`.

## Neden

Doğrulama kümesinde Botnet'e kaçan Benign akışların (FP) %86,7'si (111 / 128) aynı akış
şablonuna uyuyor (`reports/hafta11/botnet_analiz.md`). Alt-eğitimde bu şablonu taşıyan satırların
1.077'si Benign, 315'i Botnet (Botnet payı yaklaşık %23). Şablondaki Benign ve Botnet satırları
45 öznitelikte birebir aynı değil (ortak vektör 0; `reports/hafta11/sablon_kontrol.md`). Yalnızca
zamanlama sütunlarında ayrışıyorlar ve aralıklar örtüşüyor. SMOTE Botnet'i 900 satırdan 10.000'e
(~11 kat) çoğaltıyor. Bu yüzden modelin şablonu Botnet saydığı düşünülüyor (FP'lerin medyan
Botnet olasılığı 0,795). Deney, Botnet'in daha az çoğaltılmasının yanlış pozitifleri azaltıp
azaltmadığını sınar.

## Mevcut ayarın doğrulamadaki değerleri (ölçüt yazılmadan önce bilinen)

SMOTE 10.000, Botnet eşiği 0,30, tohum 42 (`experiments/botnet_importance.py` çalıştırması):

| Ölçüt | Değer |
| --- | --- |
| Doğrulamadaki Botnet satırı | 230 |
| TP / FN / FP | 218 / 12 / 128 |
| Botnet recall | %94,78 (218 / 230) |
| Botnet precision | %63,01 (218 / 346) |
| Botnet F1 | %75,69 |

Mevcut ayarın recall değeri %90 sınırını sağladığı için sınır mutlak kalır (aşağıda 2. madde).

## Deney düzeni

- Bölme, öznitelikler ve model 9. hafta ayarlarıyla aynıdır: `experiments/alarm_threshold.py::validation_model`.
  Model yalnızca alt-eğitimde eğitilir, doğrulamada ölçülür. **Test kümesi kullanılmaz.**
- Botnet SMOTE hedefi T: {SMOTE yok (alt-eğitimdeki 900 satır olduğu gibi), 2.500, 5.000, 10.000 (mevcut)}.
  Diğer küçük sınıflar (PortScan, Brute Force, Web Attack) her zaman 10.000'e tamamlanır.
  Benign ve DoS/DDoS çoğaltılmaz.
- Botnet karar eşiği t: {0,30 (mevcut), 0,50, 0,70}. Eşik kuralı `src/evaluate.py::predict_classes`.
  Aynı modelin olasılıklarından hesaplanır, eşik için yeniden eğitim yapılmaz.
- Tohum s: {42, 43, 44}. Hem SMOTE'un hem RF'nin `random_state` değeri s'dir. Bölme tohumu 42 sabit.
- Toplam 4 × 3 = 12 eğitim, 4 × 3 × 3 = 36 (T, t, s) ölçümü.
- Her (T, t) için 3 tohumun ortalaması ve örneklem standart sapması (ddof = 1) raporlanır:
  Botnet F1, recall ve precision, Benign↔Botnet FP/FN sayıları, diğer her sınıfın F1'i, Macro F1.
- Referans R = (T = 10.000, t = 0,30). R de aynı 3 tohumla ölçülür. Karşılaştırmalar R'nin 3 tohum
  ortalamasına göre yapılır.

## Seçim kuralı

1. **Uygunluk.** Bir (T, t) ancak şu iki koşulu sağlarsa aday olur:
   - Botnet recall ortalaması ≥ %90. Eğer R'nin 3 tohum recall ortalaması %90'ın altında çıkarsa
     sınır göreli olur: ortalama recall ≥ R'nin ortalama recall'u − 2 puan.
   - Botnet dışındaki her sınıfta ortalama F1 ≥ R'nin o sınıftaki ortalama F1'i − 0,5 puan.
2. **Seçim.** Uygun adaylar içinden ortalama Botnet F1'i en yüksek olan seçilir. Fark 0,1 puandan
   küçükse mevcut ayara yakın olan seçilir: önce T = 10.000, sonra büyük T; aynı T'de t = 0,30,
   sonra küçük t.
3. **Benimseme.** Seçilenin R'ye göre kazancı Δ = ortalama Botnet F1 (seçilen) − ortalama Botnet F1 (R).
   Yeni ayar ancak şu iki koşul birlikte sağlanırsa benimsenir:
   - Δ ≥ 1 puan,
   - Δ > max(std(seçilen), std(R)), yani kazanç tohumlar arası sapmadan büyük.

   Biri bile sağlanmazsa **mevcut ayar (10.000, 0,30) kalır**.

## Sonrası

- **Mevcut ayar kalırsa:** test kümesi yeniden kullanılmaz. Uygulama, alarm oranları ve 9. hafta
  test sonuçları değişmez. Deney sonucu (kazanç yok) raporlanır.
- **Yeni ayar benimsenirse:**
  1. Son model tüm eğitim kümesiyle (alt-eğitim + doğrulama), seçilen T ve t ile, tohum 42 ile eğitilir.
  2. Alarm oranları ve N_min doğrulamada 10. haftanın yöntemi ve ölçütüyle yeniden hesaplanır
     (`experiments/ratio_threshold.py`, `reports/hafta10/esik_secim_olcutu.md`). Bunun için
     alt-eğitim modeli yeni ayarla eğitilir.
  3. N2 (tek kayıt gecikmesi, 10.000 satır) ve N3 (tepe bellek) yeniden ölçülür. Uygulama ve
     testler güncellenir.
  4. Test kümesinde **yalnızca seçilen ayar, bir kez** ölçülür. Raporda bunun test kümesinin
     ikinci kullanımı olduğu yazılır. 9. hafta test sonuçları yanında, değiştirilmeden gösterilir.
