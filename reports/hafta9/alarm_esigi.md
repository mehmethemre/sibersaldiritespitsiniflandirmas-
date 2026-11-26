# Alarm Eşiği Seçimi (doğrulama kümesi)

Alt-eğitimde (1.407.332 satır) 9. hafta ayarlarıyla eğitilen model, görmediği doğrulama kümesinde (351.833 satır) tahmin yaptı. Doğrulamadaki 298.004 Benign akışın %0,072'ü saldırı sanıldı: DoS/DDoS 69, PortScan 17, Brute Force 0, Web Attack 0, Botnet 128.

Her boyut için 2.000 rastgele parça çekildi. Seçim kuralı: 10.000 satırlık Benign parçalarda yanlış KRİTİK oranı <= %5 olan en küçük N. **Seçilen N = 9.**

## Yalnızca Benign parçalarda yanlış KRİTİK alarm çıkan parça oranı

| N | 1.000 satır | 3.000 satır | 10.000 satır | 100.000 satır |
| --- | --- | --- | --- | --- |
| 1 | %47,5 | %86,5 | %99,9 | %100,0 |
| 2 | %9,8 | %45,6 | %97,5 | %100,0 |
| 3 | %0,9 | %16,5 | %88,9 | %100,0 |
| 5 | %0,0 | %1,0 | %47,0 | %100,0 |
| 8 | %0,0 | %0,0 | %6,8 | %100,0 |
| 9 | %0,0 | %0,0 | %2,5 | %100,0 |
| 10 | %0,0 | %0,0 | %0,9 | %100,0 |
| 15 | %0,0 | %0,0 | %0,0 | %100,0 |
| 20 | %0,0 | %0,0 | %0,0 | %100,0 |
| 30 | %0,0 | %0,0 | %0,0 | %99,2 |
| 50 | %0,0 | %0,0 | %0,0 | %10,8 |

Benign parçalarda yanlış saldırı akışı sayısı (en kalabalık KRİTİK sınıf):

| Parça | Ort. yanlış saldırı akışı | Medyan | %95'lik | En çok |
| --- | --- | --- | --- | --- |
| 1.000 | 0,70 | 0,0 | 2,0 | 4 |
| 3.000 | 2,14 | 1,0 | 3,0 | 7 |
| 10.000 | 7,11 | 4,0 | 8,0 | 12 |
| 100.000 | 71,68 | 43,0 | 52,0 | 65 |

## Doğal dağılımlı parçalar (gerçek saldırılar dahil)

Yanlış KRİTİK: parçada olmayan bir sınıf için alarm. Düşürülen: parçada gerçekten bulunan bir saldırı sınıfının N'den az akışla tespit edilip sarı bilgiye düşmesi (gizlenmez).

| N | 1.000: yanlış KRİTİK / düşürülen | 3.000: yanlış KRİTİK / düşürülen | 10.000: yanlış KRİTİK / düşürülen | 100.000: yanlış KRİTİK / düşürülen |
| --- | --- | --- | --- | --- |
| 1 | %16,4 / %1,5 | %9,6 / %0,4 | %0,1 / %0,0 | %0,0 / %0,0 |
| 2 | %3,0 / %23,1 | %4,0 / %7,9 | %0,1 / %0,0 | %0,0 / %0,0 |
| 3 | %0,3 / %37,9 | %1,2 / %20,4 | %0,1 / %0,2 | %0,0 / %0,0 |
| 5 | %0,0 / %55,1 | %0,1 / %39,4 | %0,0 / %2,2 | %0,0 / %0,0 |
| 8 | %0,0 / %65,9 | %0,0 / %49,3 | %0,0 / %13,9 | %0,0 / %0,0 |
| 9 | %0,0 / %67,0 | %0,0 / %51,2 | %0,0 / %20,0 | %0,0 / %0,0 |
| 10 | %0,0 / %67,4 | %0,0 / %53,2 | %0,0 / %26,7 | %0,0 / %0,0 |
| 15 | %0,0 / %67,7 | %0,0 / %67,6 | %0,0 / %47,2 | %0,0 / %0,0 |
| 20 | %0,0 / %67,7 | %0,0 / %73,0 | %0,0 / %49,9 | %0,0 / %0,0 |
| 30 | %0,0 / %67,7 | %0,0 / %73,7 | %0,0 / %50,8 | %0,0 / %0,0 |
| 50 | %0,0 / %67,7 | %0,0 / %73,7 | %0,0 / %73,0 | %0,0 / %0,0 |
