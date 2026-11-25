"""Proje genelindeki ayarlar: klasör yolları, sınıf eşlemesi ve hiperparametreler."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "raw"
ARTIFACTS_DIR = ROOT / "artifacts"
REPORTS_DIR = ROOT / "reports"

RANDOM_STATE = 42
TEST_SIZE = 0.20
VAL_SIZE = 0.20                # 8. hafta: eğitim kümesinin bu oranı doğrulama kümesi olur

# Öznitelik seçimi
CORR_THRESHOLD = 0.95          # bu değerin üzerindeki korelasyonlu çiftlerden biri elenir
IMPORTANCE_CUMSUM = 0.90       # kümülatif önem bu orana ulaşana kadar öznitelik seçilir
FS_SAMPLE_SIZE = 300_000       # öznitelik seçimi eğitim kümesinden alınan bu boyutta örneklemle yapılır

# SMOTE: bu sayının altındaki sınıflar bu sayıya tamamlanır (yalnızca eğitim kümesinde)
SMOTE_TARGET = 100_000
SMOTE_K = 5

# Modelin ezberlememesi için çıkarılan meta sütunlar (hangisi varsa)
DROP_COLUMNS = [
    "Destination Port", "Flow ID", "Source IP", "Destination IP",
    "Source Port", "Timestamp",
]

PORT_COLUMN = "Destination Port"

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
    if s == "bot":
        return "Botnet"
    return None
