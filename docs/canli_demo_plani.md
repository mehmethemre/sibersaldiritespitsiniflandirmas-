# Canlı Demo Planı — nmap + CICFlowMeter (VirtualBox, isteğe bağlı)

> Durum: **yalnızca plan** (11. hafta). Hiçbir kurulum yapılmadı, hiçbir adım denenmedi.
> Aşağıdaki CICFlowMeter sütun adları geliştiricinin bilgisine dayanır ve **gerçek bir çıktıyla
> doğrulanmadı**; ilk denemede ilk iş, üretilen CSV'nin başlık satırını bu tabloyla karşılaştırmaktır.

## 1. Amaç ve beklenti

Kendi kurduğumuz izole bir ağda nmap ile port taraması yapıp trafiği kaydetmek, CICFlowMeter ile
akışlara çevirmek ve CSV'yi Streamlit uygulamasına yükleyerek **PortScan** tahmini ve turuncu
UYARI kartını canlı göstermek.

Gerçekçi beklenti: model CICIDS2017'nin kayıt ortamında (2017, belirli işletim sistemleri ve
ağ) eğitildi. Farklı ortamda, farklı CICFlowMeter sürümüyle çıkarılan akışlarda başarı düşebilir.
Demo bir başarı ölçümü değil, uçtan uca akışın gösterimidir; sonuç ne çıkarsa olduğu gibi
raporlanır.

## 2. Gereken araçlar

| Araç | Nerede | Not |
| --- | --- | --- |
| VirtualBox 7.x | Windows ana makine | Sanallaştırma BIOS'ta açık olmalı |
| Kali Linux VM (saldırgan) | VirtualBox | nmap, tcpdump hazır gelir |
| Hedef VM | VirtualBox | Ör. Ubuntu Server veya Metasploitable 2 (açık portları çok, yalnızca izole ağda!) |
| tcpdump / Wireshark | Kali veya hedef | Trafiği `.pcap` olarak kaydetmek için |
| CICFlowMeter | Kali (veya ana makine) | İki seçenek: Java sürümü (CICFlowMeter-4.0, UNB/ahlashkari) veya Python paketi (`pip install cicflowmeter`). Sütun adları ikisinde farklı (bkz. §5) |
| Bu proje | Windows ana makine | `streamlit run app.py` |

## 3. Ağ ayarı (host-only)

1. VirtualBox → Dosya → Araçlar → Ağ Yöneticisi → **Host-only ağ** oluştur
   (ör. `192.168.56.0/24`, DHCP açık).
2. Kali ve hedef VM'lerin ağ bağdaştırıcısı: **Host-only Adapter**, aynı ağ.
   NAT/köprü bağdaştırıcısı **eklenmez**: tarama trafiği okul/ev ağına çıkmamalı.
3. Kontrol: Kali'den `ping 192.168.56.x` (hedef), hedeften Kali'ye ping.
4. Güvenlik: tarama yalnızca kendi kurduğumuz hedef VM'e yapılır. Metasploitable kullanılırsa
   hiçbir zaman host-only dışındaki bir ağa bağlanmaz.

## 4. Adımlar

1. **Kaydı başlat** (Kali): `sudo tcpdump -i eth0 -w tarama.pcap host 192.168.56.x`
2. **Normal trafik üret** (birkaç dakika): hedefteki web sunucusuna `curl`, `ssh` bağlantısı vb.
   Hem Benign hem PortScan akışı olsun ki dağılım grafiği anlamlı olsun.
3. **Port taraması** (Kali), CICIDS2017'deki nmap çeşitlerine benzer birkaç tarama:
   - `nmap -sS 192.168.56.x` (SYN taraması)
   - `nmap -sT 192.168.56.x` (TCP connect)
   - `nmap -sV -p 1-1000 192.168.56.x` (servis sürümü)
4. **Kaydı durdur** (Ctrl+C) ve `.pcap`'i paylaşılan klasörle ana makineye al.
5. **Akış çıkarımı**:
   - Java: CICFlowMeter GUI → Offline → pcap seç → çıktı klasörü → CSV.
   - Python: `cicflowmeter -f tarama.pcap -c tarama_akislar.csv`
6. **Sütun eşleme** (gerekirse, §5): `tarama_akislar.csv` → `tarama_cicids.csv`.
7. **Uygulamaya yükle**: Analiz sayfası → dosya → "Analiz et". Beklenen: PortScan akışları,
   eşiği geçerse turuncu UYARI kartı. Sonucu ekran görüntüsüyle kaydet.
8. **Etiket (isteğe bağlı)**: Kali'nin IP'sinden hedefe giden ve tarama zaman aralığına düşen
   akışlara `Label = PortScan`, diğerlerine `BENIGN` yazılırsa uygulama "Gerçek etiketlerle
   karşılaştırma" bölümünü de gösterir. Bu etiketleme yaklaşıktır; raporda öyle belirtilir.

## 5. Sütun uyumu: modelin beklediği 45 öznitelik

Model `artifacts/features.json`'daki 45 sütunu **bu adlarla** bekler (CICIDS2017
`MachineLearningCSV` adları; baştaki boşluklar uygulamada zaten kırpılır, büyük/küçük harf farkı
`src/inference.py::_match_columns` ile eşlenir). Fazla sütunlar (IP, port, zaman damgası, Label
dışındakiler) yok sayılır; eksik bir sütun varsa uygulama eksikleri listeleyip analiz yapmaz.

CICFlowMeter'ın yeni sürümleri (CSE-CIC-IDS2018 ile kullanılan Java 4.0 sürümü) kısaltılmış adlar,
Python paketi ise küçük harf + alt çizgi kullanır. Aşağıdaki karşılıklar **doğrulanmadı**:

| # | Model (CICIDS2017) | Java CICFlowMeter-4.0 (tahmini) | Python `cicflowmeter` (tahmini) |
| --- | --- | --- | --- |
| 1 | Flow Duration | Flow Duration | flow_duration |
| 2 | Bwd IAT Total | Bwd IAT Tot | bwd_iat_tot |
| 3 | Fwd IAT Max | Fwd IAT Max | fwd_iat_max |
| 4 | Idle Min | Idle Min | idle_min |
| 5 | Bwd IAT Max | Bwd IAT Max | bwd_iat_max |
| 6 | Fwd IAT Mean | Fwd IAT Mean | fwd_iat_mean |
| 7 | Fwd IAT Std | Fwd IAT Std | fwd_iat_std |
| 8 | Bwd IAT Mean | Bwd IAT Mean | bwd_iat_mean |
| 9 | Fwd IAT Min | Fwd IAT Min | fwd_iat_min |
| 10 | Bwd IAT Min | Bwd IAT Min | bwd_iat_min |
| 11 | Flow IAT Std | Flow IAT Std | flow_iat_std |
| 12 | Bwd IAT Std | Bwd IAT Std | bwd_iat_std |
| 13 | Flow Bytes/s | Flow Byts/s | flow_byts_s |
| 14 | Idle Std | Idle Std | idle_std |
| 15 | Flow IAT Mean | Flow IAT Mean | flow_iat_mean |
| 16 | Flow IAT Min | Flow IAT Min | flow_iat_min |
| 17 | Total Length of Bwd Packets | TotLen Bwd Pkts | totlen_bwd_pkts |
| 18 | Packet Length Variance | Pkt Len Var | pkt_len_var |
| 19 | Active Max | Active Max | active_max |
| 20 | Active Mean | Active Mean | active_mean |
| 21 | Active Min | Active Min | active_min |
| 22 | Fwd Header Length | Fwd Header Len | fwd_header_len |
| 23 | Active Std | Active Std | active_std |
| 24 | Flow Packets/s | Flow Pkts/s | flow_pkts_s |
| 25 | Bwd Packets/s | Bwd Pkts/s | bwd_pkts_s |
| 26 | Init_Win_bytes_forward | Init Fwd Win Byts | init_fwd_win_byts |
| 27 | Init_Win_bytes_backward | Init Bwd Win Byts | init_bwd_win_byts |
| 28 | Total Length of Fwd Packets | TotLen Fwd Pkts | totlen_fwd_pkts |
| 29 | Max Packet Length | Pkt Len Max | pkt_len_max |
| 30 | Bwd Packet Length Max | Bwd Pkt Len Max | bwd_pkt_len_max |
| 31 | Fwd Packet Length Max | Fwd Pkt Len Max | fwd_pkt_len_max |
| 32 | act_data_pkt_fwd | Fwd Act Data Pkts | fwd_act_data_pkts |
| 33 | Average Packet Size | Pkt Size Avg | pkt_size_avg |
| 34 | Avg Fwd Segment Size | Fwd Seg Size Avg | fwd_seg_size_avg |
| 35 | Bwd Packet Length Min | Bwd Pkt Len Min | bwd_pkt_len_min |
| 36 | Fwd Packet Length Min | Fwd Pkt Len Min | fwd_pkt_len_min |
| 37 | Min Packet Length | Pkt Len Min | pkt_len_min |
| 38 | Down/Up Ratio | Down/Up Ratio | down_up_ratio |
| 39 | PSH Flag Count | PSH Flag Cnt | psh_flag_cnt |
| 40 | ACK Flag Count | ACK Flag Cnt | ack_flag_cnt |
| 41 | URG Flag Count | URG Flag Cnt | urg_flag_cnt |
| 42 | Fwd PSH Flags | Fwd PSH Flags | fwd_psh_flags |
| 43 | FIN Flag Count | FIN Flag Cnt | fin_flag_cnt |
| 44 | ECE Flag Count | ECE Flag Cnt | ece_flag_cnt |
| 45 | Fwd URG Flags | Fwd URG Flags | fwd_urg_flags |

Adı değişmeden kalması beklenen sütunlar (ör. `Flow Duration`, `Fwd IAT Max`, `Active Mean`)
doğrudan eşleşir; büyük/küçük harf farkını uygulama zaten giderir. Diğerleri için ad eşlemesi gerekir.

### Eşleme nasıl yapılır (öneri, henüz kod yok)

- Küçük bir betik: `scripts/cicflowmeter_to_cicids.py girdi.csv cikti.csv`. İçinde yukarıdaki
  tablodan bir `{kaynak_ad: model_adı}` sözlüğü; `df.rename(columns=...)` ile yeniden adlandırıp
  CSV yazar. Eşlenemeyen model sütunlarını ekrana listeler (uygulama zaten eksik sütun mesajı verir).
- Tablo ilk gerçek çıktıyla doğrulanıp düzeltildikten sonra yazılır; yanlış eşleme sessizce
  yanlış tahmin üreteceği için her eşleme tek tek kontrol edilir.
- Uygulamanın kendisine eşleme eklenmez: model sözleşmesi (45 CICIDS2017 adı) değişmesin.

### Ad dışındaki olası farklar (kontrol listesi)

- **Birim:** CICIDS2017'de `Flow Duration` ve IAT sütunları mikrosaniye. Yeni sürümün aynı birimi
  kullandığı ilk çıktıda kontrol edilmeli (ör. bilinen kısa bir bağlantının süresine bakarak).
- **Başlık uzunlukları:** 2017 sürümünde `Fwd Header Length` sütunu iki kez yazılıyordu
  (`Fwd Header Length.1`, yüklemede siliniyor). Yeni sürümde tek sütun beklenir.
- **Akış zaman aşımı:** CICIDS2017'de akış zaman aşımı 120 sn idi; farklı ayar akış sayısını ve
  süre/idle değerlerini değiştirir. Mümkünse aynı değer kullanılır.
- **Bayrak sayaçları:** bazı sürümlerde `Fwd PSH Flags`, `URG Flag Count` gibi sütunlar hep 0 olabilir.
  Bu, dağılım kayması demektir; raporda not edilir.
- **Inf/NaN:** `Flow Bytes/s` sıfır süreli akışlarda Inf olabilir. Uygulama bu satırları zaten
  "atlanan satır" olarak gösterir.

## 6. Riskler

- Dağılım kayması nedeniyle PortScan yerine Benign veya DoS tahmini çıkabilir; bu, modelin aynı
  veri setinden test edilmesinin sınırını gösteren dürüst bir sonuçtur.
- CICFlowMeter Java sürümü belirli bir Java ve jnetpcap sürümü isteyebilir; kurulum zaman alabilir.
  Python paketi daha kolay kurulur ama öznitelik hesapları Java sürümünden farklı olabilir.
- Demo sırasında internet gerekmez; bütün dosyalar önceden hazırlanmalı, canlı sunumda
  önceden kaydedilmiş `.pcap` ve CSV yedek olarak tutulmalı.
