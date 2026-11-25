"""Tekrar silme analizi (model eğitmez).

1) Tekrar silmede her sınıftan kaç satır gittiğini `Destination Port` dahil / hariç ölçer.
2) Port hariç tutulduğunda öznitelikleri birebir aynı olup farklı sınıf etiketi taşıyan
   satır gruplarını (etiket çakışmaları) sayar ve sınıf çiftlerine göre özetler.

Temizlik sırası `src/preprocess.py::clean` ile aynıdır: kapsam dışı sınıflar -> Inf/NaN ->
drop_duplicates. Veri klasörü `src/config.py::DATA_DIR`'dan alınır.

Kullanım (proje klasöründe):
    python analysis/dedup_by_class.py                      # tam veri
    python analysis/dedup_by_class.py --sample-frac 0.05   # hızlı deneme

Çıktılar:
    reports/dedup_by_class.csv           sınıf bazında silinen/kalan satırlar
    reports/dedup_label_conflicts.csv    sınıf çiftlerine göre etiket çakışmaları
"""
import argparse
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:   # `python analysis/dedup_by_class.py` ile de çalışsın
    sys.path.insert(0, str(ROOT))

from src import config, data_loader  # noqa: E402

PORT = "Destination Port"


def load_with_port(sample_frac=None) -> pd.DataFrame:
    """Ham veriyi `Destination Port` silinmeden yükler; kapsam dışı ve Inf/NaN satırları atar.

    Dönen tablo tekrar silme ÖNCESİ hâlidir; `Label` yerine `Class` sütunu vardır.
    """
    original = data_loader.DROP_COLUMNS
    data_loader.DROP_COLUMNS = [c for c in original if c != PORT]
    try:
        df = data_loader.load_raw(config.DATA_DIR, sample_frac, log=lambda *_: None)
    finally:
        data_loader.DROP_COLUMNS = original
    df["Class"] = df["Label"].map(config.map_label)
    df = df[df["Class"].notna()].drop(columns=["Label"])
    return df.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)


def _order(classes):
    return ([c for c in config.CLASS_ORDER if c in set(classes)]
            + sorted(set(classes) - set(config.CLASS_ORDER)))


def dedup_by_class(df: pd.DataFrame) -> pd.DataFrame:
    """Sınıf bazında tekrar silme etkisi: port dahil ve port hariç."""
    before = df["Class"].value_counts()
    order = _order(before.index)
    with_port = df.drop_duplicates()["Class"].value_counts().reindex(order, fill_value=0)
    without_port = (df.drop(columns=[PORT], errors="ignore").drop_duplicates()["Class"]
                    .value_counts().reindex(order, fill_value=0))
    before = before.reindex(order)
    out = pd.DataFrame({
        "once": before,
        "silinen_port_dahil": before - with_port,
        "silinen_port_haric": before - without_port,
        "kalan_port_dahil": with_port,
        "kalan_port_haric": without_port,
    })
    out.loc["TOPLAM"] = out.sum()
    out.index.name = "sinif"
    return out


def _conflict_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Port hariç öznitelikleri aynı olup birden fazla sınıf içeren grupları bulur.

    Dönen tablo: satır = çakışan grup, sütun = sınıf, değer = o gruptaki ham satır sayısı.
    """
    feats = [c for c in df.columns if c not in ("Class", PORT)]
    # Her satırın öznitelik vektörü 64 bitlik özete çevrilir (gruplamayı hızlandırır)
    key = pd.util.hash_pandas_object(df[feats], index=False).to_numpy()
    g = pd.DataFrame({"key": key, "Class": df["Class"].to_numpy()})
    n_cls = g.groupby("key")["Class"].nunique()
    conflict_keys = n_cls.index[n_cls > 1]
    g = g[g["key"].isin(conflict_keys)]
    counts = g.groupby(["key", "Class"]).size().unstack(fill_value=0)
    return counts.reindex(columns=_order(counts.columns), fill_value=0)


def label_conflicts(df: pd.DataFrame):
    """Etiket çakışmalarını sınıf çiftlerine göre özetler.

    Her sınıf çifti (A, B) için:
      grup_sayisi          A ve B'yi birlikte içeren öznitelik grubu sayısı
      satir_tekrar_sonrasi tekrar silme sonrası bu gruplarda kalan A+B satırı (her grupta 1 A + 1 B)
      satir_tekrar_oncesi  aynı grupların ham verideki A+B satır sayısı
      satir_A / satir_B    ham satırların sınıflara dağılımı
    Üç sınıflı bir grup üç ayrı çifte sayılır; bu yüzden çiftlerin toplamı genel toplamı aşabilir.
    """
    counts = _conflict_counts(df)
    rows = []
    for a, b in combinations(counts.columns, 2):
        mask = (counts[a] > 0) & (counts[b] > 0)
        n = int(mask.sum())
        if n == 0:
            continue
        ra, rb = int(counts.loc[mask, a].sum()), int(counts.loc[mask, b].sum())
        rows.append({"sinif_A": a, "sinif_B": b, "grup_sayisi": n,
                     "satir_tekrar_sonrasi": 2 * n, "satir_tekrar_oncesi": ra + rb,
                     "satir_A": ra, "satir_B": rb})
    pairs = pd.DataFrame(rows, columns=["sinif_A", "sinif_B", "grup_sayisi",
                                        "satir_tekrar_sonrasi", "satir_tekrar_oncesi",
                                        "satir_A", "satir_B"])
    pairs = pairs.sort_values("grup_sayisi", ascending=False, ignore_index=True)
    summary = {
        "cakisan_grup": int(len(counts)),
        "satir_tekrar_sonrasi": int((counts > 0).to_numpy().sum()),
        "satir_tekrar_oncesi": int(counts.to_numpy().sum()),
        "grup_sinif_sayisi_dagilimi": {int(k): int(v) for k, v in
                                       (counts > 0).sum(axis=1).value_counts().sort_index().items()},
    }
    return pairs, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-frac", type=float, default=None,
                    help="Hızlı deneme için her CSV'den alınacak oran (ör. 0.05)")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    df = load_with_port(args.sample_frac)
    print(f"Örneklem oranı: {args.sample_frac or 'tam veri'} · tekrar silme öncesi {len(df):,} satır\n")

    dedup = dedup_by_class(df)
    print("Sınıf bazında tekrar silme")
    print(dedup.to_string(), "\n")

    pairs, summary = label_conflicts(df)
    print("Etiket çakışmaları (port hariç, öznitelikler birebir aynı, sınıf farklı)")
    print(f"Çakışan grup: {summary['cakisan_grup']:,} · "
          f"satır (tekrar silme sonrası): {summary['satir_tekrar_sonrasi']:,} · "
          f"satır (tekrar silme öncesi): {summary['satir_tekrar_oncesi']:,}")
    print(f"Gruptaki sınıf sayısına göre grup dağılımı: {summary['grup_sinif_sayisi_dagilimi']}")
    print(pairs.to_string(index=False))

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    dedup.to_csv(config.REPORTS_DIR / "dedup_by_class.csv", encoding="utf-8")
    pairs.to_csv(config.REPORTS_DIR / "dedup_label_conflicts.csv", index=False, encoding="utf-8")
    print(f"\nYazıldı: {config.REPORTS_DIR / 'dedup_by_class.csv'}, "
          f"{config.REPORTS_DIR / 'dedup_label_conflicts.csv'}")


if __name__ == "__main__":
    main()
