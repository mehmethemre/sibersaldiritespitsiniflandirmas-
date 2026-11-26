"""experiments/alarm_threshold.py hesap fonksiyonları (elle kurulmuş küçük örneklerle)."""
import numpy as np
import pandas as pd

from experiments.alarm_threshold import alarm_stats, choose_n, chunk_counts, critical_classes
from src.config import CLASS_ORDER


def test_critical_classes_exclude_benign_and_portscan():
    assert [CLASS_ORDER[i] for i in critical_classes(CLASS_ORDER)] == \
        ["DoS/DDoS", "Brute Force", "Web Attack", "Botnet"]


def test_alarm_stats_false_critical_and_downgraded():
    # 3 parça x 2 KRİTİK sınıf (sütun 0, 1)
    t = np.array([[0, 0], [0, 5], [0, 1]])      # gerçek sayılar
    p = np.array([[2, 0], [0, 5], [3, 1]])      # tahmin sayıları
    s = alarm_stats(t, p, [0, 1], n_values=[1, 3, 6]).set_index("N")
    # N=1: parça 1 (sınıf 0 yokken 2) ve parça 3 (yokken 3) yanlış KRİTİK -> 2/3
    assert s.loc[1, "yanlis_kritik_parca"] == 2 / 3
    assert s.loc[3, "yanlis_kritik_parca"] == 1 / 3      # yalnızca 3 >= 3
    assert s.loc[6, "yanlis_kritik_parca"] == 0
    # gerçek saldırı çiftleri: (parça2,s1)=5 tespit, (parça3,s1)=1 tespit
    assert s.loc[1, "dusurulen_gercek"] == 0
    assert s.loc[3, "dusurulen_gercek"] == 0.5           # 1 < 3
    assert s.loc[6, "dusurulen_gercek"] == 1.0
    assert s.loc[1, "gercek_saldiri_cifti"] == 2


def test_chunk_counts_shapes_and_pool():
    y_true = np.array([0] * 50 + [1] * 50)
    y_pred = y_true.copy()
    t, p = chunk_counts(y_true, y_pred, 3, 10, 7, np.random.default_rng(0),
                        pool=np.arange(50))
    assert t.shape == (7, 3) and (t[:, 0] == 10).all() and (p == t).all()


def test_choose_n_smallest_meeting_rule():
    tbl = pd.DataFrame({"N": [1, 2, 3, 4], "parca_boyutu": 10_000,
                        "yanlis_kritik_parca": [0.9, 0.2, 0.04, 0.0]})
    assert choose_n(tbl, size=10_000, max_rate=0.05) == 3
    assert choose_n(tbl, size=10_000, max_rate=0.0) == 4
