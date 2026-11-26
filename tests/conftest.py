"""Testler için ortak yardımcılar: küçük sahte model ve onun artefakt klasörü.

Gerçek model GitHub'da yok (artifacts/*.pkl yüklenmez) ve eğitimi dakikalar sürer; çıkarım
testleri bu yüzden birkaç saniyede eğitilen küçük bir Random Forest ile çalışır.
"""
import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from src.config import CLASS_ORDER

FEATURES = ["Flow Duration", "Total Fwd Packets", "Bwd Packet Length Max",
            "Flow IAT Mean", "Init_Win_bytes_forward"]
RAW_LABELS = {"Benign": "BENIGN", "DoS/DDoS": "DDoS", "PortScan": "PortScan",
              "Brute Force": "SSH-Patator", "Web Attack": "Web Attack \x96 XSS", "Botnet": "Bot"}


def make_flows(n_per_class=60, seed=0):
    """Her sınıf için ayrık merkezli sahte akışlar + ham CICIDS etiketleri."""
    rng = np.random.default_rng(seed)
    rows = []
    for i, cls in enumerate(CLASS_ORDER):
        X = rng.normal(i * 4.0, 0.5, (n_per_class, len(FEATURES)))
        df = pd.DataFrame(X, columns=FEATURES)
        df["Label"] = RAW_LABELS[cls]
        rows.append(df)
    return pd.concat(rows, ignore_index=True).sample(frac=1, random_state=seed)


@pytest.fixture(scope="session")
def artifacts_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("artifacts")
    df = make_flows()
    y = df["Label"].map({v: CLASS_ORDER.index(k) for k, v in RAW_LABELS.items()}).to_numpy()
    X = df[FEATURES].to_numpy(np.float32)
    scaler = StandardScaler().fit(X)
    model = RandomForestClassifier(n_estimators=20, random_state=0).fit(scaler.transform(X), y)
    joblib.dump(model, d / "random_forest_model.pkl")
    joblib.dump(scaler, d / "scaler.pkl")
    (d / "features.json").write_text(json.dumps(FEATURES), encoding="utf-8")
    (d / "model_config.json").write_text(json.dumps({
        "model_surumu": "test-1", "model_dosyasi": "random_forest_model.pkl",
        "olcekleyici_dosyasi": "scaler.pkl", "siniflar": CLASS_ORDER, "botnet_esigi": 0.30,
    }), encoding="utf-8")
    return d
