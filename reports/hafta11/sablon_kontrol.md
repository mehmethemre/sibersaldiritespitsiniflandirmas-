# FP şablonu: Benign ve Botnet satırları birebir aynı mı?

Şablon: Init_Win_bytes_forward = 8192, Init_Win_bytes_backward = 0, Total Length of Fwd Packets = 0, Total Length of Bwd Packets = 18, Max Packet Length = 6. Karşılaştırma 45 öznitelik üzerinden.

| Küme | Benign satır | Botnet satır | Benign farklı vektör | Botnet farklı vektör | İki etikette ortak vektör | Ortak vektördeki Botnet satırı | Ortak vektördeki Benign satırı |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Alt-eğitim (çakışma silmeden önce) | 1.077 | 315 | 1.077 | 315 | 0 | 0 | 0 |
| Alt-eğitim (çakışma silindikten sonra; modelin gördüğü) | 1.077 | 315 | 1.077 | 315 | 0 | 0 | 0 |
| Doğrulama | 243 | 80 | 243 | 80 | 0 | 0 | 0 |
| Alt-eğitim (sonra) + doğrulama birlikte | 1.320 | 395 | 1.320 | 395 | 0 | 0 | 0 |

## Şablon içinde değer alan öznitelikler (alt-eğitim, çakışma sonrası)

| Öznitelik | Benign medyan [Q1–Q3] | Botnet medyan [Q1–Q3] |
| --- | --- | --- |
| Flow Duration | 1.04515e+06 [1.00257e+06–1.2695e+06] | 1.00943e+06 [998025–1.02753e+06] |
| Bwd IAT Total | 1.03081e+06 [1.00192e+06–1.18363e+06] | 1.00868e+06 [997358–1.02702e+06] |
| Fwd IAT Max | 515961 [501681–594016] | 509194 [500030–515615] |
| Bwd IAT Max | 515963 [501374–594033] | 509019 [500080–515385] |
| Fwd IAT Std | 1329.36 [501.339–3527.76] | 1636.95 [1240.62–4789.59] |
| Fwd IAT Mean | 515394 [501014–591697] | 504402 [498652–513548] |
| Bwd IAT Mean | 515406 [500958–591815] | 504338 [498679–513511] |
| Fwd IAT Min | 514795 [500036–589667] | 500447 [497457–509945] |
| Bwd IAT Min | 514927 [500101–589667] | 500365 [497490–509996] |
| Flow IAT Std | 270947 [226861–273863] | 275608 [272625–280667] |
| Flow Bytes/s | 17.2224 [14.1788–17.9538] | 17.8319 [17.5177–18.0356] |
| Bwd IAT Std | 1480.68 [490.025–3552.5] | 1856.16 [1199.25–4739.03] |
| Flow IAT Mean | 209030 [200514–253900] | 201886 [199605–205507] |
| Flow IAT Min | 728 [470–86584] | 454 [403.5–512] |
| Flow Packets/s | 5.7408 [4.72627–5.98461] | 5.94396 [5.83923–6.01187] |
| Bwd Packets/s | 2.8704 [2.36314–2.99231] | 2.97198 [2.91961–3.00594] |
