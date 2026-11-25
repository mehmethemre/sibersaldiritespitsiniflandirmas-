"""CICIDS2017 MachineLearningCSV biçiminde küçük SAHTE veri üretir (yalnızca kod testi için).

Gerçek veriyle karıştırmayın: bu dosyaların ürettiği sonuçlar rapora yazılmaz.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

LABELS = {  # etiket: (satır sayısı, sınıf merkezi kayması)
    "BENIGN": (6000, 0.0), "DoS Hulk": (900, 3.0), "DDoS": (500, 3.5),
    "PortScan": (700, -3.0), "FTP-Patator": (250, 5.0), "SSH-Patator": (200, 5.5),
    "Bot": (120, -5.0), "Web Attack \x96 Brute Force": (90, 7.0),
    "Web Attack \x96 XSS": (50, 7.5), "Infiltration": (5, 0.0), "Heartbleed": (3, 0.0),
}
BASE = ["Destination Port", "Flow Duration", "Total Fwd Packets", "Total Backward Packets",
        "Fwd Packet Length Mean", "Bwd Packet Length Mean", "Flow Bytes/s", "Flow Packets/s",
        "Flow IAT Mean", "Fwd IAT Total", "Bwd IAT Total", "Packet Length Variance",
        "SYN Flag Count", "ACK Flag Count", "Init_Win_bytes_forward", "Average Packet Size"]


def make(out_dir, n_files=2, seed=0):
    rng = np.random.default_rng(seed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for lab, (n, shift) in LABELS.items():
        X = rng.normal(shift, 1.0, (n, len(BASE)))
        X[:, 1:] += rng.normal(0, 1.0, (n, len(BASE) - 1)) * (np.arange(1, len(BASE)) % 3)
        df = pd.DataFrame(X, columns=BASE)
        df["Fwd IAT Total"] = df["Flow Duration"] * 0.98 + rng.normal(0, 0.01, n)  # yüksek korelasyon
        df["Bwd PSH Flags"] = 0.0                                                    # sabit sütun
        df["Label"] = lab
        rows.append(df)
    df = pd.concat(rows, ignore_index=True)
    df.loc[rng.choice(len(df), 30, replace=False), "Flow Bytes/s"] = np.inf
    df.loc[rng.choice(len(df), 20, replace=False), "Flow Packets/s"] = np.nan
    df = pd.concat([df, df.sample(400, random_state=seed)], ignore_index=True)       # tekrarlar
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    df.columns = [" " + c for c in df.columns]   # gerçek dosyalardaki baştaki boşluk
    for i, idx in enumerate(np.array_split(np.arange(len(df)), n_files)):
        df.iloc[idx].to_csv(out_dir / f"synthetic_part{i}.csv", index=False, encoding="latin-1")
    return out_dir


if __name__ == "__main__":
    print(make(sys.argv[1] if len(sys.argv) > 1 else "data/synthetic"))
