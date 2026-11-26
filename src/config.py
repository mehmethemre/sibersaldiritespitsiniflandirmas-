"""Proje genelindeki ayarlar: klasör yolları, sınıf eşlemesi ve hiperparametreler."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "raw"
ARTIFACTS_DIR = ROOT / "artifacts"
REPORTS_DIR = ROOT / "reports"
LOG_DIR = ROOT / "logs"                     # 9. hafta: security.log burada
DB_PATH = ROOT / "data" / "analizler.db"    # 9. hafta: analiz geçmişi (SQLite)
DEMO_DIR = ROOT / "demo"                    # 9. hafta: demo CSV dosyaları

RANDOM_STATE = 42
TEST_SIZE = 0.20
VAL_SIZE = 0.20                # 8. hafta: eğitim kümesinin bu oranı doğrulama kümesi olur

# Öznitelik seçimi
CORR_THRESHOLD = 0.95          # bu değerin üzerindeki korelasyonlu çiftlerden biri elenir
IMPORTANCE_CUMSUM = 0.90       # kümülatif önem bu orana ulaşana kadar öznitelik seçilir
# 9. hafta: ExtraTrees adımı kapalı -> korelasyon elemesinden sonra kalan TÜM öznitelikler
# (8. hafta Ek 1: doğrulamada daha iyi ve daha kararlı)
USE_EXTRATREES = False
FS_SAMPLE_SIZE = 300_000       # öznitelik seçimi eğitim kümesinden alınan bu boyutta örneklemle yapılır

# SMOTE: bu sayının altındaki sınıflar bu sayıya tamamlanır (yalnızca eğitim kümesinde)
# 7. hafta 100.000 idi; 8. hafta Deney 1'de 10.000 en iyi doğrulama Macro F1'ini verdi
SMOTE_TARGET = 10_000
SMOTE_K = 5

# Modelin ezberlememesi için çıkarılan meta sütunlar (hangisi varsa)
DROP_COLUMNS = [
    "Destination Port", "Flow ID", "Source IP", "Destination IP",
    "Source Port", "Timestamp",
]

PORT_COLUMN = "Destination Port"

# Öznitelikleri birebir aynı ama etiketi farklı satır grupları (yalnızca eğitimde):
# "sil" = bu grupların tamamı eğitimden çıkarılır (8. hafta Deney 2)
CONFLICT_MODE = "sil"

# Botnet karar eşiği: Botnet olasılığı >= eşik ise "Botnet", değilse kalan en olası sınıf
# (8. hafta Ek 2, doğrulama kümesinde seçildi). Yalnızca Random Forest'a uygulanır.
BOTNET_THRESHOLD = 0.30

MODEL_VERSION = "hafta9-rf-1"

# Alarm seviyeleri (F11): bu sınıflar CRITICAL, PortScan WARNING, Benign alarm üretmez
ALARM_LEVELS = {"DoS/DDoS": "CRITICAL", "Botnet": "CRITICAL", "Web Attack": "CRITICAL",
                "Brute Force": "CRITICAL", "PortScan": "WARNING"}

# CSV'lerde "Fwd Header Length" iki kez bulunur; pandas ikincisini ".1" ekiyle okur.
# İki sütun birebir aynı olduğu için kopya yüklemede silinir.
DUPLICATE_COLUMNS = ["Fwd Header Length.1"]

DT_PARAMS = dict(criterion="gini", max_depth=15, min_samples_split=10,
                 random_state=RANDOM_STATE)
RF_PARAMS = dict(n_estimators=100, max_depth=20, min_samples_split=5,
                 n_jobs=-1, random_state=RANDOM_STATE)

CLASS_ORDER = ["Benign", "DoS/DDoS", "PortScan", "Brute Force", "Web Attack", "Botnet"]

# Tek kayıt gecikme ölçümünde tekrar sayısı
LATENCY_REPEATS = 1000


def map_label(raw) -> "str | None":
    """CICIDS2017'nin 15 orijinal etiketini proje sınıflarına eşler.

    Infiltration ve Heartbleed (toplam 47 örnek) için None döner -> kapsam dışı.
    Proje sınıf adlarını da kabul eder ("Brute Force", "Botnet" ...): demo dosyalarındaki
    Label sütunu bu adlarla yazılır.
    """
    s = str(raw).strip().lower()
    if s == "benign":
        return "Benign"
    if s.startswith("dos") or s.startswith("ddos"):
        return "DoS/DDoS"
    if s == "portscan":
        return "PortScan"
    if "patator" in s:
        return "Brute Force"
    if s.startswith("web attack"):   # dosyalarda tire karakteri bozuk kodlanmış olabilir
        return "Web Attack"
    if s in ("bot", "botnet"):
        return "Botnet"
    if s == "brute force":           # "Web Attack - Brute Force" yukarıda yakalanır
        return "Brute Force"
    return None
