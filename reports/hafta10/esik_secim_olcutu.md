# Oran tabanlı alarm eşiği — seçim ölçütü (sonuçlar görülmeden önce sabitlendi)

Bu dosya eşik deneyi çalıştırılmadan önce yazıldı ve commit edildi; deney sonuçları bu
ölçüte göre değerlendirilir, ölçüt sonradan değiştirilmez.

## Kural

    esik(sinif, n) = max(N_min, ceil(oran_sinif * n))      n = analiz edilen akış sayısı

* KRİTİK sınıflar (DoS/DDoS, Botnet, Web Attack, Brute Force): ortak `oran_K` (sınıf bazında
  oran yalnızca aşağıdaki koşulla seçilir).
* PortScan (WARNING): ayrı `oran_PS`, aynı ölçütle. `N_min` ortaktır (kenar çubuğunda tek değer).
* Bir sınıftan `esik`'ten az akış -> WARNING + "incelenmeli" (9. haftadaki gibi; tahmin değişmez).

## Veri ve model

* Yalnızca DOĞRULAMA kümesi (351.833 satır). Model: 9. hafta ayarlarıyla yalnızca alt-eğitimde
  eğitilen Random Forest (`experiments/alarm_threshold.py::validation_predictions`).
* Doğrulamadaki sınıf sayıları: Benign 298.004, DoS/DDoS 51.479, Brute Force 1.464,
  Web Attack 343, PortScan 313, Botnet 230.
* Test kümesi yalnızca seçilen kural için bir kez kullanılır (uygulamadaki modelle).

## Parçalar (rastgele "dosyalar")

Parça boyutları n: 1.000 · 3.000 · 10.000 · 30.000 · 100.000 · 250.000 satır.
Her (senaryo, boyut, sınıf, k) hücresi için **2.000 parça**, tohum **42**
(`numpy.random.default_rng(42)`, her hücre için yeniden oluşturulur; sonuç çalıştırma
sırasından bağımsızdır). Parçalar yerine konmadan çekilir; bir parçadaki sınıf/tahmin
sayıları çok değişkenli hipergeometrik dağılımdan doğrudan örneklenir (satır satır çekmekle
aynı dağılım, daha hızlı).

* **S0 — yalnızca Benign:** n Benign satır.
* **S1 — düşük saldırı, mutlak sayı:** (n − k) Benign + bir saldırı sınıfından k gerçek akış,
  k ∈ {10, 50, 200}; her saldırı sınıfı için ayrı.
* **S2 — düşük saldırı, oran:** k = %0,1 × n ve %1 × n (S1 ile aynı yapı). Yalnızca raporlanır.
* **S3 — doğal dağılım:** doğrulamadaki sınıf oranlarıyla. Yalnızca raporlanır (9. haftayla
  karşılaştırma için).

## Ölçülenler

* **Yanlış KRİTİK (S0):** parçaların kaçında herhangi bir KRİTİK sınıf için tespit ≥ esik.
* **Yanlış UYARI (S0):** parçaların kaçında PortScan tespiti ≥ esik_PS (turuncu kart).
* **Kaçırılan saldırı (S1/S2):** eklenen sınıfın tespit sayısı (Benign'den gelen yanlış
  tespitler dahil) < esik -> alarm normal seviyesinde verilmedi, "incelenmeli"ye düştü
  ya da hiç görünmedi.

## Seçim ölçütü

1. **Kısıt:** her boyutta (1.000 … 250.000) S0'da yanlış KRİTİK oranı ≤ %5.
   (9. haftadaki politikanın — 10.000 satırda ≤ %5 — tüm boyutlara genişletilmesi.)
2. **Amaç:** kısıtı sağlayan (N_min, oran_K) adayları arasından, S1'de KRİTİK sınıflar ×
   k ∈ {10, 50, 200} × tüm boyutlar üzerinden **ortalama kaçırma oranı en düşük** olan.
3. **Eşitlik:** daha küçük oran, sonra daha küçük N_min.
4. Arama ızgarası: N_min ∈ {1, …, 50}; oran ∈ {0; 0,00001; …; 0,00200}.
5. **PortScan:** N_min yukarıda seçilen değerde sabit; oran_PS aynı ölçütle (S0'da yanlış UYARI
   ≤ %5, S1'de PortScan kaçırma ortalaması en düşük, eşitlikte küçük oran).
6. **Sınıf bazında oran:** N_min sabit; her KRİTİK sınıf için kendi yanlış alarm oranı
   ≤ %1,25 (= %5 / 4, dört sınıfın toplamı %5'i aşmasın diye) olan en küçük oran_c. Yalnızca
   (a) S0'da toplam yanlış KRİTİK ≤ %5 her boyutta sağlanıyor ve (b) S1 ortalama kaçırma oranı
   tek orana göre **en az 5 puan** düşükse seçilir; aksi halde tek oran kalır.

**Gerekçe:** önce yanlış alarm yükü sınırlanır (sürekli yanlış KRİTİK veren bir sistem
görmezden gelinir; 9. haftadaki %5 politikası korunur), sonra bu sınır içinde gerçek
saldırıların alarm alma oranı en yükseğe çıkarılır. Amaç S1 (mutlak sayılar) üzerinden
tanımlanır, çünkü küçük dosyalarda oran tek başına anlamlı değildir (1.000 satırda %0,1 = 1 akış).

## Raporlanacaklar

* Her boyut için "alarm için gereken en az saldırı akışı" (= eşik): eski N=9 ve yeni kural.
* Her boyut × k için kaçırma oranı: eski ve yeni kural (büyük dosyalarda az sayıda saldırıyı
  kaçırma bedeli açıkça).
* Test kümesinde aynı tablolar (bir kez), eski ve yeni kural yan yana.
* Demo dosyalarında alarmların 9. haftayla aynı kalıp kalmadığı.

## Doğrulamada yetersiz örnek durumu

Karar: **senaryo sınırlanır, tekrarlı örnekleme yapılmaz.** Eklenecek saldırı akışı sayısı k,
o sınıfın doğrulamadaki (test ölçümünde testteki) akış sayısından büyükse hücre ölçülmez ve
tabloda "ölçülmedi: yetersiz örnek" yazılır. Bu yalnızca S2'yi (oran senaryosu) etkiler:
%0,1 × 250.000 = 250 (Botnet); %1 × 30.000 = 300 (Botnet); %1 × 100.000 = 1.000 (Botnet,
PortScan, Web Attack); %1 × 250.000 = 2.500 (Botnet, PortScan, Web Attack, Brute Force).
S1'de k ≤ 200 ≤ en küçük havuz (Botnet 230) olduğu için tüm hücreler ölçülür; seçim S1 ile
yapıldığından seçilen kural bu sınırlamadan etkilenmez. Not: Botnet k = 200'de 230 akışın
200'ü çekildiği için parçalar birbirine çok benzer; bu hücrenin değişkenliği düşük çıkar.

## Notlar

1. **Plandan sapma — amaç fonksiyonu:** planda "kaçırma oranının en kötü boyuttaki değeri"
   yazıyordu; ölçütte bunun yerine **S1 ortalama kaçırma oranı** kullanıldı. Neden: büyük
   boyutlarda (ör. 100.000 satır) k = 10 akış, %5 yanlış alarm kısıtını sağlayan her adayda
   eşiğin altında kalır ve kaçırılır; en kötü durum bütün adaylar için aynı (≈ %100) olduğundan
   adayları ayırt etmez. Ortalama, KRİTİK sınıflar (4) × k (3) × boyut (6) = 72 hücre üzerinden
   **eşit ağırlıkla** alınır (her hücre 2.000 parçanın kaçırma oranı). PortScan için 3 × 6 = 18
   hücre, yine eşit ağırlık.
2. **Büyük parçaların örtüşmesi:** 100.000 ve 250.000 satırlık S0 parçaları 298.004 satırlık
   Benign havuzundan çekildiği için birbiriyle büyük ölçüde örtüşür (250.000'lik iki parça
   ortalama ≈ %84 ortak satır içerir). Bu boyutlardaki S0 oranları 2.000 bağımsız ölçüm
   sayılmaz; aynı havuzun farklı alt kümeleridir ve gerçekte bağımsız dosyalardaki oranı
   olduğundan kesin gösterebilir.
