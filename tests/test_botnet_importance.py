"""11. hafta Botnet öznitelik önem analizinin yardımcı fonksiyonları."""
import numpy as np
import pandas as pd

from experiments.botnet_importance import exact_match_rate, group_quartiles, groups


def test_groups_split_four_ways():
    b, k = 0, 5
    y = np.array([5, 0, 5, 0, 5, 2])
    p = np.array([5, 5, 0, 0, 2, 5])
    m = groups(y, p, b, k)
    assert [int(m[g].sum()) for g in ["TP", "FP", "FN", "TN"]] == [1, 1, 1, 1]
    # Botnet -> başka saldırı ve başka saldırı -> Botnet dört gruba girmez
    assert not any(m[g][4] or m[g][5] for g in m)


def test_exact_match_rate():
    ref = np.array([[1, 2], [3, 4]], dtype=np.float32)
    rows = np.array([[1, 2], [9, 9], [3, 4], [3, 5]], dtype=np.float64)
    assert exact_match_rate(rows, ref) == 0.5
    assert np.isnan(exact_match_rate(rows[:0], ref))


def test_group_quartiles_skips_empty_group():
    X = pd.DataFrame({"a": [0.0, 1.0, 2.0, 3.0]})
    masks = {"TP": np.array([1, 1, 0, 0], bool), "FP": np.zeros(4, bool),
             "FN": np.array([0, 0, 1, 0], bool), "TN": np.array([0, 0, 0, 1], bool)}
    q = group_quartiles(X, masks, ["a"])
    assert set(q["grup"]) == {"TP", "FN", "TN"}
    tp = q[q.grup == "TP"].iloc[0]
    assert tp.medyan == 0.5 and tp.sifir_orani == 0.5


def test_template_compare_counts_shared_vectors():
    from experiments.botnet_template_check import TEMPLATE, compare
    base = {**TEMPLATE, "Flow Duration": 1.0}
    rows = [dict(base), dict(base), {**base, "Flow Duration": 2.0}, {**base, "Max Packet Length": 7}]
    X = pd.DataFrame(rows)
    y = np.array([0, 5, 5, 0])                       # 0: Benign, 5: Botnet
    feats = list(X.columns)
    r = compare(X, y, feats, 0, 5)
    # 4. satır şablona uymaz; 1. ve 2. satır aynı vektör, iki etikette
    assert (r["benign_satir"], r["botnet_satir"]) == (1, 2)
    assert r["iki_etikette_ortak_vektor"] == 1
    assert r["botnet_satiri_ortak_vektorde"] == 1 and r["benign_satiri_ortak_vektorde"] == 1
    assert [d["oznitelik"] for d in r["degisen_oznitelikler"]] == ["Flow Duration"]
