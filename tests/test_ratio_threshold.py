"""Oran tabanlı alarm eşiği: eşik formülü ve seçim deneyinin yardımcıları."""
import numpy as np

from experiments import ratio_threshold as rt
from src.alarm import alarm_threshold
from src.config import CLASS_ORDER


def test_alarm_threshold_formula():
    assert alarm_threshold("Botnet", 3_000, 9, {}) == 9                  # oran yok -> sabit
    assert alarm_threshold("Botnet", 100_000, 9, {"Botnet": 0.0005}) == 50
    assert alarm_threshold("Botnet", 1_000, 9, {"Botnet": 0.0005}) == 9  # küçük dosya: N_min
    # kayan nokta: 0.00003 * 100000 = 3.0000000000000004 -> 4 olmamalı
    assert alarm_threshold("Botnet", 100_000, 1, {"Botnet": 0.00003}) == 3
    assert alarm_threshold("Botnet", 100_001, 1, {"Botnet": 0.00003}) == 4  # yukarı yuvarlama


def _table(benign=300_000, fp_botnet=150, attack=300):
    """Sahte karışıklık tablosu: Benign'in bir kısmı Botnet sanılıyor, saldırılar doğru."""
    k = len(CLASS_ORDER)
    C = np.zeros((k, k), dtype=np.int64)
    C[0, 0], C[0, CLASS_ORDER.index("Botnet")] = benign - fp_botnet, fp_botnet
    for i in range(1, k):
        C[i, i] = attack
    return C


def test_simulate_marks_insufficient_cells(monkeypatch):
    monkeypatch.setattr(rt, "N_CHUNKS", 50)
    s0, s1, s2, s3 = rt.simulate(_table(), CLASS_ORDER, sizes=[1_000, 100_000])
    assert s0[1_000].shape == (50, len(CLASS_ORDER))
    assert s0[1_000].sum(axis=1).tolist() == [1_000] * 50
    assert s1[(1_000, "Botnet", 200)][0] is not None
    assert s2[(100_000, "Botnet", 0.01)][0] is None        # k = 1.000 > 300 akışlık havuz
    assert s2[(100_000, "Botnet", 0.001)][0] is not None   # k = 100


def test_choose_respects_false_alarm_limit(monkeypatch):
    monkeypatch.setattr(rt, "N_CHUNKS", 200)
    monkeypatch.setattr(rt, "SIZES", [1_000, 100_000])
    sims = rt.simulate(_table(), CLASS_ORDER, sizes=[1_000, 100_000])
    crit = ["DoS/DDoS", "Brute Force", "Web Attack", "Botnet"]
    n_min, rate, obj, feasible = rt.choose(sims, CLASS_ORDER, crit, range(1, 21),
                                           [i * 1e-5 for i in range(0, 101)])
    assert feasible > 0
    for n in (1_000, 100_000):
        thr = rt.thresholds({"N_min": n_min, "oranlar": {c: rate for c in crit}},
                            CLASS_ORDER, n)
        assert rt.false_rate(sims[0][n], thr, [CLASS_ORDER.index(c) for c in crit]) <= 0.05
    # oran 0 olsaydı 100.000 satırda ~50 yanlış Botnet akışı her parçada alarm verirdi
    assert rate > 0
