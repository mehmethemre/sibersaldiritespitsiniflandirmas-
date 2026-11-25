"""CICIDS2017 MachineLearningCSV dosyalarını okuyup tek tabloda birleştirir."""
from pathlib import Path

import pandas as pd

from .config import DROP_COLUMNS, DUPLICATE_COLUMNS, PORT_COLUMN, RANDOM_STATE


def load_raw(data_dir, sample_frac=None, log=print, keep_port=False) -> pd.DataFrame:
    """keep_port=True: `Destination Port` silinmez (8. hafta port deneyi için)."""
    drop_cols = [c for c in DROP_COLUMNS if not (keep_port and c == PORT_COLUMN)]
    drop_cols += DUPLICATE_COLUMNS   # birebir kopya sütun (Fwd Header Length.1)
    files = sorted(Path(data_dir).glob("*.csv"))
    if not files:
        raise FileNotFoundError(
            f"'{data_dir}' klasöründe CSV bulunamadı. MachineLearningCSV.zip içindeki "
            "8 CSV dosyasını bu klasöre kopyalayın."
        )

    frames = []
    for f in files:
        # latin-1: bazı dosyalarda 'Web Attack – ...' etiketindeki tire bozuk kodlanmıştır
        df = pd.read_csv(f, encoding="latin-1", low_memory=False)
        df.columns = df.columns.str.strip()
        if "Label" not in df.columns:
            raise ValueError(f"{f.name} dosyasında 'Label' sütunu yok.")
        if sample_frac:
            df = df.sample(frac=sample_frac, random_state=RANDOM_STATE)

        df = df.drop(columns=[c for c in drop_cols if c in df.columns])
        feat_cols = [c for c in df.columns if c != "Label"]
        # Sayısal olmayan bozuk hücreler NaN olur; bellek için float32
        df[feat_cols] = df[feat_cols].apply(pd.to_numeric, errors="coerce").astype("float32")
        log(f"  {f.name}: {len(df):,} satır")
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    log(f"Birleşik ham veri: {len(df):,} satır, {df.shape[1] - 1} öznitelik")
    return df
