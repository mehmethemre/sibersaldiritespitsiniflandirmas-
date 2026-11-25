"""8. hafta yardımcı fonksiyonlarını ve deney betiğini doğrular (sahte veriyle).

Çalıştırma: python -m pytest -q
"""
import json

import numpy as np
import pandas as pd
import pytest

from experiments.run_experiments import best_of, main, metric_row
from src.data_loader import load_raw
from src.preprocess import (SmoteTarget, clean, oversample, port_category,
                            resolve_label_conflicts, split_train_val)
from tests.make_synthetic import make

quiet = lambda *_: None


def test_load_drops_duplicate_column_and_keep_port(tmp_path):
    # Gerçek CSV'deki gibi aynı adlı iki sütun: pandas ikincisini ".1" ekiyle okur
    (tmp_path / "a.csv").write_text(
        " Destination Port, Fwd Header Length, Fwd Header Length, Label\n"
        "80,20,20,BENIGN\n443,40,40,Bot\n", encoding="latin-1")
    df = load_raw(tmp_path, log=quiet)
    assert "Fwd Header Length" in df.columns
    assert "Fwd Header Length.1" not in df.columns
    assert "Destination Port" not in df.columns
    df_p = load_raw(tmp_path, log=quiet, keep_port=True)
    assert df_p["Destination Port"].tolist() == [80, 443]


def test_clean_count_col_counts_raw_copies():
    raw = pd.DataFrame({"f": [1, 1, 1, 2, 3, 3], "g": [0, 1, 0, 0, 5, 5],
                        "Label": ["BENIGN", "BENIGN", "BENIGN", "Bot", "Bot", "BENIGN"]}
                       ).astype({"f": "float32", "g": "float32"})
    df, stats = clean(raw, quiet, count_col="_n")
    assert stats["tekrar_silinen"] == 1
    counts = {(f, g, c): n for f, g, c, n in df[["f", "g", "Class", "_n"]].to_numpy()}
    assert counts[(1.0, 0.0, "Benign")] == 2
    assert counts[(3.0, 5.0, "Botnet")] == 1
    assert "_n" not in stats["sabit_sutunlar"]


def test_port_category():
    assert port_category([0, 80, 1023, 1024, 8080, 49151, 49152, 65535]).tolist() == \
        [0, 0, 0, 1, 1, 1, 2, 2]


def _conflict_table():
    X = pd.DataFrame({"a": [1, 1, 2, 2, 3, 3, 4], "b": [0, 0, 0, 0, 0, 0, 9]}, dtype="float32")
    y = np.array([0, 5, 0, 2, 0, 5, 1])          # 3 çakışan grup + 1 tekil satır
    n = np.array([10, 3, 4, 4, 1, 7, 1])         # ham kopya sayıları (oy)
    return X, y, n


def test_resolve_conflicts_modes():
    X, y, n = _conflict_table()
    Xb, yb, ib = resolve_label_conflicts(X, y, n, "birak")
    assert len(Xb) == 7 and ib["cakisan_grup"] == 3 and ib["cakisan_satir"] == 6

    Xs, ys, i_s = resolve_label_conflicts(X, y, n, "sil")
    assert ys.tolist() == [1] and i_s["silinen_satir"] == 6

    Xm, ym, im = resolve_label_conflicts(X, y, n, "cogunluk")
    # grup a=1: 0 kazanır (10>3); a=2: eşit (4=4) -> silinir; a=3: 5 kazanır (7>1)
    assert list(zip(Xm["a"], ym)) == [(1, 0), (3, 5), (4, 1)]
    assert im["esit_oylu_grup"] == 1 and im["silinen_satir"] == 4

    with pytest.raises(ValueError):
        resolve_label_conflicts(X, y, n, "bilinmeyen")


def test_resolve_conflicts_keeps_series_index():
    X, y, n = _conflict_table()
    X.index = y_idx = np.arange(100, 107)
    ys = pd.Series(y, index=y_idx)
    Xm, ym, _ = resolve_label_conflicts(X, ys, n, "sil")
    assert list(Xm.index) == list(ym.index) == [106]


def test_smote_target_and_oversample_target():
    y = np.array([0] * 500 + [1] * 50 + [2] * 20)
    assert SmoteTarget(100)(y) == {1: 100, 2: 100}
    assert SmoteTarget(10_000)(y) == {1: 500, 2: 500}   # en büyük sınıfı aşmaz
    X = np.random.default_rng(0).normal(size=(len(y), 3)).astype(np.float32)
    Xr, yr, _ = oversample(X, y, quiet, target=100)
    assert np.bincount(yr).tolist() == [500, 100, 100]


def test_split_train_val_is_stratified_and_disjoint():
    X = pd.DataFrame({"f": np.arange(1000)})
    y = pd.Series([0] * 900 + [1] * 100)
    Xa, Xv, ya, yv = split_train_val(X, y)
    assert len(Xv) == 200 and (yv == 1).sum() == 20
    assert set(Xa.index).isdisjoint(Xv.index)


def test_metric_row_and_best_of():
    names = ["Benign", "DoS/DDoS", "PortScan", "Botnet"]
    y_true = np.array([0, 0, 0, 0, 1, 2, 3, 3])
    y_pred = np.array([0, 0, 3, 3, 1, 2, 3, 0])
    row, cm = metric_row(y_true, y_pred, names)
    assert row["benign_to_botnet"] == 2
    assert row["botnet_precision"] == pytest.approx(1 / 3)
    assert row["botnet_recall"] == pytest.approx(0.5)
    assert row["accuracy"] == pytest.approx(5 / 8)
    assert row["f1_PortScan"] == 1.0
    assert best_of([{"macro_f1": 0.5, "x": 1}, {"macro_f1": 0.7, "x": 2}])["x"] == 2


def test_prepare_uses_fixed_features_and_force_cols():
    """features verilince seçim yapılmamalı; çakışma işlemi küme dışındaki sütunları etkilemez."""
    from experiments.run_experiments import prepare
    X, y, n = _conflict_table()
    X["port"] = np.float32(80)
    P = prepare(X, y, n, X, "sil", quiet, force_cols=("port",), features=["b"])
    assert P["features"] == ["b", "port"]
    assert P["X_fit"].shape == (1, 2) and P["X_eval"].shape == (7, 2)


def test_run_experiments_smoke(tmp_path):
    """Tüm deney akışı sahte veride uçtan uca çalışmalı ve beklenen dosyaları üretmeli."""
    data = make(tmp_path / "veri")
    out = tmp_path / "cikti"
    R = main(["--data", str(data), "--out", str(out), "--n-iter", "2", "--cv-sample", "3000"])
    for f in ["deney1_smote.csv", "deney2_cakisma.csv", "deney3_port.csv",
              "deney4_arama_sonuclari.csv", "deney4_en_iyi.json", "deney5_model.csv",
              "final_test.csv", "final_karsilastirma.csv", "hata_matrisi_final.png",
              "rapor_tablolari_hafta8.md", "sonuclar.json", "secilen_yapilandirma.json"]:
        assert (out / f).exists(), f
    assert len(R["deney1"]) == 5 and len(R["deney2"]) == 3 and len(R["deney3"]) == 3
    # port varyantlarının doğrulama boyutu raporlanır
    assert all(r["dogrulama_satir"] > 0 for r in R["deney3"])
    # test kümesi port yok varyantında 7. haftayla aynı bölmeden gelir: boyut tutarlı
    assert R["kume_boyutlari"]["alt_egitim"] + R["kume_boyutlari"]["dogrulama"] == \
        R["kume_boyutlari"]["egitim"]
    best = json.loads((out / "deney4_en_iyi.json").read_text(encoding="utf-8"))
    assert set(best["en_iyi_parametreler"]) == {"n_estimators", "max_depth",
                                                "min_samples_split", "min_samples_leaf",
                                                "max_features"}
    assert "Deney 3" in (out / "rapor_tablolari_hafta8.md").read_text(encoding="utf-8")
