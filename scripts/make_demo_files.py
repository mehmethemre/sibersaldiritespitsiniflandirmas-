"""Demo CSV dosyalarını TEST kümesinden üretir (model bu satırları eğitimde hiç görmedi).

Neden test kümesi? Eğitim satırlarıyla demo yapılırsa model onları ezberlemiş olabilir ve
doğruluk yanıltıcı derecede yüksek görünür. Test kümesi run_pipeline.py ile birebir aynı
şekilde (aynı temizlik, aynı random_state) yeniden üretilir.

Label sütunu proje sınıf adlarıyla korunur (Benign, DoS/DDoS, ...); uygulama bu sütunu görünce
tahminleri gerçek etiketlerle karşılaştırır.

Üretilen dosyalar (demo/):
  demo_normal.csv        yalnızca Benign
  demo_ddos.csv          çoğunluk DoS/DDoS, biraz Benign
  demo_portscan.csv      testteki tüm PortScan akışları + Benign
  demo_karma.csv         altı sınıfın hepsi
  demo_10000_satir.csv   testten rastgele 10.000 satır (süre ölçümü için)
  demo_bozuk.csv         karmadan; bilerek bozulmuş hücreler (metin, Inf, boş)
  demo_eksik_sutun.csv   karmadan; modelin ihtiyaç duyduğu 3 sütun silinmiş

Kullanım:  python scripts/make_demo_files.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.data_loader import load_raw  # noqa: E402
from src.preprocess import clean, split  # noqa: E402

SEED = config.RANDOM_STATE
# Her dosyada sınıf başına satır sayısı ("all" = testteki tüm satırlar)
RECIPES = {
    "demo_normal.csv": {"Benign": 3000},
    "demo_ddos.csv": {"DoS/DDoS": 2400, "Benign": 600},
    "demo_portscan.csv": {"PortScan": "all", "Benign": 1600},
    "demo_karma.csv": {"Benign": 2000, "DoS/DDoS": 800, "PortScan": 200,
                       "Brute Force": 400, "Web Attack": 200, "Botnet": 200},
}


def build(test: pd.DataFrame, recipe: dict, seed=SEED) -> pd.DataFrame:
    """Tarife göre sınıflardan örnek alır ve karıştırır."""
    parts = []
    for cls, n in recipe.items():
        pool = test[test["Label"] == cls]
        n = len(pool) if n == "all" else min(n, len(pool))
        parts.append(pool.sample(n=n, random_state=seed))
    return pd.concat(parts).sample(frac=1, random_state=seed).reset_index(drop=True)


def corrupt(df: pd.DataFrame, features, seed=SEED) -> tuple[pd.DataFrame, dict]:
    """Bilinen sayıda satırı bozar: 20 metin, 15 Inf, 10 boş hücre (45 farklı satır)."""
    rng = np.random.default_rng(seed)
    df = df.copy()
    rows = rng.choice(len(df), 45, replace=False)
    cols = [features[i % len(features)] for i in range(45)]
    df[list(set(cols))] = df[list(set(cols))].astype(object)
    for k, (r, c) in enumerate(zip(rows, cols)):
        df.at[r, c] = "abc" if k < 20 else (np.inf if k < 35 else np.nan)
    return df, {"metin": 20, "inf": 15, "bos": 10}


def main():
    if hasattr(sys.stdout, "reconfigure"):   # Windows konsolunda Türkçe karakterler bozulmasın
        sys.stdout.reconfigure(encoding="utf-8")
    out = config.DEMO_DIR
    out.mkdir(parents=True, exist_ok=True)
    print("Veri yükleniyor ve test kümesi yeniden üretiliyor...")
    raw = load_raw(config.DATA_DIR, log=lambda *_: None)
    df, _ = clean(raw, log=lambda *_: None)
    del raw
    _, X_te, _, y_te = split(df)              # run_pipeline.py ile aynı bölme
    test = X_te.assign(Label=y_te.to_numpy())
    print(f"Test kümesi: {len(test):,} satır")

    info = {}
    for name, recipe in RECIPES.items():
        d = build(test, recipe)
        d.to_csv(out / name, index=False)
        info[name] = d["Label"].value_counts().to_dict()

    big = test.sample(n=10_000, random_state=SEED).reset_index(drop=True)
    big.to_csv(out / "demo_10000_satir.csv", index=False)
    info["demo_10000_satir.csv"] = big["Label"].value_counts().to_dict()

    features = json.loads((config.ARTIFACTS_DIR / "features.json").read_text(encoding="utf-8"))
    base = build(test, RECIPES["demo_karma.csv"], seed=SEED + 1).head(500)
    bad, counts = corrupt(base, features)
    bad.to_csv(out / "demo_bozuk.csv", index=False)
    info["demo_bozuk.csv"] = {"satir": len(bad), "bozulan_satir": counts}
    base.drop(columns=features[:3]).to_csv(out / "demo_eksik_sutun.csv", index=False)
    info["demo_eksik_sutun.csv"] = {"satir": len(base), "silinen_sutunlar": features[:3]}

    (out / "demo_icerik.json").write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    for name, v in info.items():
        size = (out / name).stat().st_size / 1024**2
        print(f"  {name:24s} {size:5.1f} MB  {v}")


if __name__ == "__main__":
    main()
