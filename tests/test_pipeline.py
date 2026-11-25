"""Boru hattının doğruluğunu ve sızıntı olmadığını sahte veriyle doğrular.

Çalıştırma: python -m pytest -q
"""
import numpy as np
import pandas as pd
import pytest

from src.config import map_label
from src.data_loader import load_raw
from src.preprocess import clean, fit_scaler, oversample, select_features, split
from tests.make_synthetic import make


@pytest.fixture(scope="module")
def cleaned(tmp_path_factory):
    d = make(tmp_path_factory.mktemp("veri"))
    raw = load_raw(d, log=lambda *_: None)
    df, stats = clean(raw, log=lambda *_: None)
    return raw, df, stats


def test_label_mapping():
    assert map_label(" BENIGN") == "Benign"
    assert map_label("DoS Hulk") == "DoS/DDoS"
    assert map_label("DDoS") == "DoS/DDoS"
    assert map_label("SSH-Patator") == "Brute Force"
    assert map_label("Web Attack \x96 XSS") == "Web Attack"
    assert map_label("Bot") == "Botnet"
    assert map_label("Infiltration") is None
    assert map_label("Heartbleed") is None


def test_columns_stripped_and_port_dropped(cleaned):
    raw, _, _ = cleaned
    assert "Label" in raw.columns
    assert "Destination Port" not in raw.columns
    assert all(c == c.strip() for c in raw.columns)


def test_clean_removes_bad_rows(cleaned):
    _, df, stats = cleaned
    feats = df.drop(columns="Class")
    assert not feats.isna().any().any()
    assert np.isfinite(feats.to_numpy()).all()
    assert not df.duplicated().any()
    assert stats["kapsam_disi_silinen"] > 0 and stats["tekrar_silinen"] > 0
    assert "Bwd PSH Flags" in stats["sabit_sutunlar"]
    assert set(df["Class"]) <= {"Benign", "DoS/DDoS", "PortScan", "Brute Force", "Web Attack", "Botnet"}


def test_no_leakage(cleaned):
    _, df, _ = cleaned
    X_tr, X_te, y_tr, y_te = split(df)
    # aynı satır hem eğitimde hem testte olmamalı
    joined = pd.concat([X_tr.assign(_s="tr"), X_te.assign(_s="te")])
    dup = joined.drop(columns="_s").duplicated(keep=False)
    assert joined.loc[dup, "_s"].nunique() <= 1

    # öznitelik seçimi yalnızca eğitimle; yüksek korelasyonlu çiftten biri elenmeli
    feats, info = select_features(X_tr, y_tr, log=lambda *_: None)
    assert not ({"Flow Duration", "Fwd IAT Total"} <= set(feats))

    # ölçekleyici yalnızca eğitime fit: eğitim ortalaması ~0
    sc = fit_scaler(X_tr[feats].to_numpy(np.float32))
    assert np.allclose(sc.transform(X_tr[feats].to_numpy(np.float32)).mean(0), 0, atol=1e-3)

    # SMOTE yalnızca eğitimi büyütür, test dağılımı değişmez
    y_tr_i = pd.factorize(y_tr)[0]
    n_test_before = len(X_te)
    Xr, yr, _ = oversample(X_tr[feats].to_numpy(np.float32), y_tr_i, log=lambda *_: None)
    assert len(Xr) > len(X_tr)
    assert len(X_te) == n_test_before
