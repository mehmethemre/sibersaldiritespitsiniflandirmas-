"""Oran tabanlı alarm eşiği seçimi (10. hafta).

Kural:  esik(sinif, n) = max(N_min, ceil(oran_sinif × n))   (src/alarm.py::alarm_threshold)
Seçim ölçütü deneyden ÖNCE yazıldı: reports/hafta10/esik_secim_olcutu.md (commit 2e299b8).

İki kip:
  python experiments/ratio_threshold.py           # DOĞRULAMA: N_min ve oranları seçer
  python experiments/ratio_threshold.py --test    # TEST: seçilen kuralı bir kez ölçer

Doğrulama kipinde model 9. hafta ayarlarıyla yalnızca alt-eğitimde eğitilir
(experiments/alarm_threshold.py::validation_predictions); test kipinde uygulamadaki model
(artifacts/) test kümesinde kullanılır. Test kipi kuralı doğrulama çıktısından okur; test
sonucuna göre kural değiştirilmez.

Parçalar: her (senaryo, boyut, sınıf, k) hücresi için 2.000 rastgele "dosya", tohum 42 (her
hücrede yeniden). Bir parçadaki (gerçek sınıf, tahmin) sayıları, (gerçek × tahmin) karışıklık
tablosundan çok değişkenli hipergeometrik dağılımla örneklenir: yerine koymadan satır çekmekle
aynı dağılım, ama 250.000 satırlık 2.000 parça saniyeler içinde üretilir.
  S0 yalnızca Benign · S1 Benign + bir saldırı sınıfından k ∈ {10, 50, 200} akış ·
  S2 aynı yapı, k = %0,1 / %1 × n (yalnızca rapor) · S3 doğal dağılım (yalnızca rapor)
k, sınıfın havuzundan büyükse hücre ölçülmez ("yetersiz örnek"; tekrarlı örnekleme yok).

Çıktılar: reports/hafta10/esik_{dogrulama|test}_*.csv, .json, .md
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from run_pipeline import setup_logger, tr_int, tr_pct  # noqa: E402
from src import config  # noqa: E402
from src.alarm import alarm_threshold  # noqa: E402

SIZES = [1_000, 3_000, 10_000, 30_000, 100_000, 250_000]
KS = [10, 50, 200]
RATES = [0.001, 0.01]
N_CHUNKS = 2_000
SEED = config.RANDOM_STATE
MAX_FALSE = 0.05
PER_CLASS_FALSE = MAX_FALSE / 4
MIN_GAIN = 0.05                               # sınıf bazında oran için en az 5 puan iyileşme
N_MIN_GRID = range(1, 51)
RATE_GRID = [round(i * 1e-5, 5) for i in range(0, 201)]     # 0 … 0,002
OLD_RULE = {"N_min": config.ALARM_MIN_FLOWS, "oranlar": {}}  # 9. hafta: sabit N = 9
OUT = config.REPORTS_DIR / "hafta10"


# ------------------------------------------------------------------ örnekleme
def contingency(y_true, y_pred, k):
    """(gerçek, tahmin) sayı tablosu: C[t, p]."""
    return np.bincount(np.asarray(y_true) * k + np.asarray(y_pred),
                       minlength=k * k).reshape(k, k)


def _draw(rng, colors, m):
    """colors havuzundan yerine koymadan m satır: N_CHUNKS × len(colors) sayı matrisi."""
    if m == 0:
        return np.zeros((N_CHUNKS, len(colors)), dtype=np.int64)
    return rng.multivariate_hypergeometric(np.asarray(colors, dtype=np.int64), m,
                                           size=N_CHUNKS)


def simulate(C, cn, sizes=SIZES):
    """Tüm senaryoların parçalarını üretir. Ölçülemeyen hücre: None."""
    b = cn.index("Benign")
    attacks = [i for i in range(len(cn)) if i != b]
    benign_pool, total = int(C[b].sum()), int(C.sum())
    s0, s1, s2, s3 = {}, {}, {}, {}
    for n in sizes:
        s0[n] = _draw(np.random.default_rng(SEED), C[b], n) if n <= benign_pool else None
        cells = [("S1", c, k, None) for c in attacks for k in KS] + \
                [("S2", c, max(1, round(r * n)), r) for c in attacks for r in RATES]
        for sc, c, k, r in cells:
            ok = k <= C[c].sum() and n - k <= benign_pool
            if ok:
                rng = np.random.default_rng(SEED)
                det = _draw(rng, C[b], n - k)[:, c] + _draw(rng, C[c], k)[:, c]
            (s1 if sc == "S1" else s2)[(n, cn[c], k if sc == "S1" else r)] = \
                (det if ok else None, k)
        if n <= total:
            joint = _draw(np.random.default_rng(SEED), C.ravel(), n).reshape(N_CHUNKS, *C.shape)
            s3[n] = (joint.sum(axis=2), joint.sum(axis=1))     # gerçek, tahmin sayıları
        else:
            s3[n] = None
    return s0, s1, s2, s3


# ------------------------------------------------------------------ değerlendirme
def thresholds(rule, cn, n):
    return np.array([alarm_threshold(c, n, rule["N_min"], rule["oranlar"]) for c in cn])


def false_rate(pred, thr, cols):
    """Parçaların kaçında cols sınıflarından en az biri için tespit ≥ eşik (yalnızca Benign)."""
    return float((pred[:, cols] >= thr[cols]).any(axis=1).mean())


def evaluate(rule, sims, cn):
    """Bir kuralın tüm senaryolardaki sonuçları (tablolar)."""
    s0, s1, s2, s3 = sims
    crit = [cn.index(c) for c in cn if config.ALARM_LEVELS.get(c) == "CRITICAL"]
    ps = [cn.index("PortScan")]
    rows0, rows1, rows2, rows3 = [], [], [], []
    for n in s0:
        thr = thresholds(rule, cn, n)
        if s0[n] is not None:
            rows0.append({"n": n, "esik_kritik": int(thr[crit].max()),
                          "esik_portscan": int(thr[ps[0]]),
                          "yanlis_kritik": false_rate(s0[n], thr, crit),
                          "yanlis_uyari_portscan": false_rate(s0[n], thr, ps)})
        if s3[n] is not None:
            t, p = s3[n]
            tc, pc = t[:, crit], p[:, crit]
            present = tc > 0
            rows3.append({"n": n,
                          "yanlis_kritik": float(((tc == 0) & (pc >= thr[crit])).any(axis=1).mean()),
                          "dusurulen_gercek": float((present & (pc < thr[crit])).sum()
                                                    / max(present.sum(), 1))})
    for table, out, key in ((s1, rows1, "k"), (s2, rows2, "oran")):
        for (n, c, v), (det, k) in table.items():
            thr = alarm_threshold(c, n, rule["N_min"], rule["oranlar"])
            out.append({"n": n, "sinif": c, key: v, "k": k, "esik": thr,   # S1'de key = "k"
                        "kacirma": None if det is None else float((det < thr).mean())})
    return tuple(pd.DataFrame(r) for r in (rows0, rows1, rows2, rows3))


def objective(s1, cls, thr_of):
    """S1 ortalama kaçırma oranı: verilen sınıflar × k × boyutlar, eşit ağırlık."""
    return float(np.mean([float((det < thr_of(c, n)).mean())
                          for (n, c, _), (det, _) in s1.items()
                          if c in cls and det is not None]))


# ------------------------------------------------------------------ seçim
def _curves(s0, s1, cols, cn, tmax):
    """Hız için: her boyutta eşik T'ye göre yanlış alarm ve kaçırma oranı eğrileri."""
    T = np.arange(tmax + 1)
    fp = {n: (np.clip(s0[n][:, cols].max(axis=1), 0, tmax + 1)[:, None] >= T).mean(axis=0)
          for n in s0 if s0[n] is not None}
    names = {cn[c] for c in cols}
    miss = {key: (np.clip(det, 0, tmax + 1)[:, None] < T).mean(axis=0)
            for key, (det, _) in s1.items() if key[1] in names and det is not None}
    return fp, miss


def choose(sims, cn, cls, n_min_grid, rate_grid, max_false=MAX_FALSE):
    """Ölçüt: her boyutta yanlış alarm ≤ max_false; S1 ortalama kaçırma en düşük;
    eşitlikte küçük oran, sonra küçük N_min. Dönüş: (N_min, oran, amaç, uygun aday sayısı)."""
    s0, s1 = sims[0], sims[1]
    cols = [cn.index(c) for c in cls]
    tmax = max(max(n_min_grid), int(np.ceil(max(rate_grid) * max(SIZES))) + 1)
    fp, miss = _curves(s0, s1, cols, cn, tmax)
    best, feasible = None, 0
    for n_min in n_min_grid:
        for r in rate_grid:
            thr = {n: alarm_threshold("x", n, n_min, {"x": r}) for n in SIZES}
            if any(fp[n][thr[n]] > max_false for n in fp):
                continue
            feasible += 1
            obj = round(float(np.mean([m[thr[key[0]]] for key, m in miss.items()])), 12)
            cand = (obj, r, n_min)
            best = cand if best is None or cand < best else best
    if best is None:
        return None, None, None, 0
    return best[2], best[1], best[0], feasible


def choose_per_class(sims, cn, crit, n_min, rate_grid):
    """Her KRİTİK sınıf için kendi yanlış alarm oranı ≤ %1,25 olan en küçük oran."""
    s0 = sims[0]
    rates = {}
    for c in crit:
        i = cn.index(c)
        for r in rate_grid:
            if all(float((s0[n][:, i] >= alarm_threshold(c, n, n_min, {c: r})).mean())
                   <= PER_CLASS_FALSE for n in s0 if s0[n] is not None):
                rates[c] = r
                break
        else:
            return None
    return rates


# ------------------------------------------------------------------ veri
def validation_table(args, log):
    from experiments.alarm_threshold import validation_predictions
    cn, y_val, y_pred, n_sub = validation_predictions(args, log)
    return cn, contingency(y_val, y_pred, len(cn)), {"alt_egitim_satir": int(n_sub)}


def test_table(log):
    """Uygulamadaki modelle test kümesi tahminleri (make_demo_files.py ile aynı yeniden üretim)."""
    from src.data_loader import load_raw
    from src.inference import Predictor
    from src.preprocess import clean, split
    raw = load_raw(config.DATA_DIR, log=lambda *_: None)
    df, _ = clean(raw, log=lambda *_: None)
    del raw
    _, X_te, _, y_te = split(df)
    del df
    predictor = Predictor()
    res = predictor.predict(X_te.assign(Label=y_te.to_numpy()))
    cn = predictor.class_names
    code = {c: i for i, c in enumerate(cn)}
    p = res.predictions.dropna(subset=["gercek"])
    log(f"Test: {len(X_te):,} satır, karşılaştırılan {len(p):,}, model {predictor.version}")
    return cn, contingency(p["gercek"].map(code), p["tahmin"].map(code), len(cn)), \
        {"model_surumu": predictor.version}


# ------------------------------------------------------------------ ana akış
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--data", default=str(config.DATA_DIR))
    ap.add_argument("--sample-frac", type=float, default=None)
    args = ap.parse_args(argv)
    mode = "test" if args.test else "dogrulama"
    out = OUT / (f"deneme_frac{args.sample_frac}" if args.sample_frac else "")
    out.mkdir(parents=True, exist_ok=True)
    log = setup_logger(out / f"esik_{mode}_log.txt")
    t0 = time.perf_counter()

    cn, C, meta = test_table(log) if args.test else validation_table(args, log)
    pd.DataFrame(C, index=cn, columns=cn).rename_axis("gercek\\tahmin").to_csv(
        out / f"esik_{mode}_karisiklik.csv", encoding="utf-8")
    pools = {c: int(C[i].sum()) for i, c in enumerate(cn)}
    log(f"Sınıf havuzları: {pools}")
    sims = simulate(C, cn)
    crit = [c for c in cn if config.ALARM_LEVELS.get(c) == "CRITICAL"]

    if args.test:
        sel = json.loads((OUT / "esik_dogrulama_ozet.json").read_text(encoding="utf-8"))
        new_rule = {"N_min": sel["secilen"]["N_min"], "oranlar": sel["secilen"]["oranlar"]}
        summary = {"kip": "test", "kural": new_rule, **meta}
    else:
        n_min, r_k, obj_k, feas = choose(sims, cn, crit, N_MIN_GRID, RATE_GRID)
        if n_min is None:
            raise SystemExit("Kısıtı sağlayan aday yok; ızgarayı genişletin.")
        _, r_ps, obj_ps, feas_ps = choose(sims, cn, ["PortScan"], [n_min], RATE_GRID)
        single = {c: r_k for c in crit} | {"PortScan": r_ps}
        pc = choose_per_class(sims, cn, crit, n_min, RATE_GRID)
        pc_info = {"oranlar": pc}
        chosen = single
        if pc is not None:
            pc_rule = {"N_min": n_min, "oranlar": pc | {"PortScan": r_ps}}
            joint_ok = all(false_rate(sims[0][n], thresholds(pc_rule, cn, n),
                                      [cn.index(c) for c in crit]) <= MAX_FALSE
                           for n in sims[0] if sims[0][n] is not None)
            obj_pc = objective(sims[1], crit,
                               lambda c, n: alarm_threshold(c, n, n_min, pc))
            gain = obj_k - obj_pc
            pc_info |= {"toplam_yanlis_kritik_uygun": joint_ok, "amac": obj_pc,
                        "iyilesme_puan": gain * 100,
                        "secildi": bool(joint_ok and gain >= MIN_GAIN)}
            if pc_info["secildi"]:
                chosen = pc_rule["oranlar"]
        new_rule = {"N_min": n_min, "oranlar": chosen}
        summary = {"kip": "dogrulama", "secilen": new_rule,
                   "tek_oran": {"N_min": n_min, "oran_kritik": r_k, "amac_kritik": obj_k,
                                "uygun_aday": feas, "oran_portscan": r_ps,
                                "amac_portscan": obj_ps, "uygun_aday_portscan": feas_ps},
                   "sinif_bazinda": pc_info,
                   "izgara": {"N_min": [min(N_MIN_GRID), max(N_MIN_GRID)],
                              "oran": [RATE_GRID[0], RATE_GRID[-1]], "adim": 1e-5},
                   **meta}
    summary |= {"parca_sayisi": N_CHUNKS, "tohum": SEED, "boyutlar": SIZES, "k": KS,
                "oran_senaryolari": RATES, "havuzlar": pools,
                "ornekleme_orani": args.sample_frac}

    tables = {}
    for name, rule in (("eski", OLD_RULE), ("yeni", new_rule)):
        tables[name] = evaluate(rule, sims, cn)
    keys = (["n"], ["n", "sinif", "k"], ["n", "sinif", "oran", "k"], ["n"])
    merged = []
    for i, (fname, key) in enumerate(zip(("s0", "s1", "s2", "s3"), keys)):
        m = tables["eski"][i].merge(tables["yeni"][i], on=key, suffixes=("_eski", "_yeni"))
        m.to_csv(out / f"esik_{mode}_{fname}.csv", index=False, encoding="utf-8")
        merged.append(m)
    summary["sure_dk"] = (time.perf_counter() - t0) / 60
    (out / f"esik_{mode}_ozet.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(out / f"esik_{mode}.md", summary, *merged)
    log(f"Kural: {new_rule} · {summary['sure_dk']:.1f} dk · Çıktılar: {out}")
    return summary, merged


def _p(x):
    return "ölçülmedi (yetersiz örnek)" if x is None or pd.isna(x) else tr_pct(x, 1)


def write_report(path, s, s0, s1, s2, s3):
    rule = s.get("secilen") or s["kural"]
    L = [f"# Oran tabanlı alarm eşiği — {'DOĞRULAMA' if s['kip'] == 'dogrulama' else 'TEST'}\n"]
    if s["ornekleme_orani"]:
        L.append("> **Uyarı:** örneklem çalıştırması; sayılar rapora yazılmaz.\n")
    L.append(f"Kural: N_min = {rule['N_min']}, oranlar = {rule['oranlar']}. Eski kural: sabit "
             f"N = {OLD_RULE['N_min']}. Hücre başına {tr_int(s['parca_sayisi'])} parça, tohum "
             f"{s['tohum']}. Sınıf havuzları: "
             + ", ".join(f"{k} {tr_int(v)}" for k, v in s["havuzlar"].items()) + ".\n")
    L.append("## Alarm için gereken en az saldırı akışı (= eşik)\n")
    cls = [c for c in config.CLASS_ORDER if c in config.ALARM_LEVELS]
    L.append("| Dosya (satır) | Eski (tüm sınıflar) | " + " | ".join(f"Yeni {c}" for c in cls)
             + " |\n| --- | --- |" + " --- |" * len(cls))
    for n in SIZES:
        L.append(f"| {tr_int(n)} | {OLD_RULE['N_min']} | " + " | ".join(
            str(alarm_threshold(c, n, rule["N_min"], rule["oranlar"])) for c in cls) + " |")
    L.append("\n## S0 — yalnızca Benign: yanlış alarm çıkan parça oranı\n")
    L.append("| Dosya | Yanlış KRİTİK eski | Yanlış KRİTİK yeni | Yanlış UYARI (PortScan) eski "
             "| Yanlış UYARI yeni |\n| --- | --- | --- | --- | --- |")
    for r in s0.itertuples():
        L.append(f"| {tr_int(r.n)} | {_p(r.yanlis_kritik_eski)} | {_p(r.yanlis_kritik_yeni)} | "
                 f"{_p(r.yanlis_uyari_portscan_eski)} | {_p(r.yanlis_uyari_portscan_yeni)} |")
    L.append("\n## S1 — k saldırı akışı eklenmiş Benign dosya: kaçırma oranı (eski / yeni)\n")
    L.append("Kaçırma: eklenen sınıfın tespit sayısı eşiğin altında kaldı (alarm normal "
             "seviyesinde verilmedi; \"incelenmeli\" olarak görünür veya hiç görünmez).\n")
    classes = list(dict.fromkeys(s1["sinif"]))
    L.append("| Dosya | k | " + " | ".join(classes) + " |")
    L.append("| --- | --- |" + " --- |" * len(classes))
    for (n, k), g in s1.groupby(["n", "k"], sort=True):
        g = g.set_index("sinif")
        L.append(f"| {tr_int(n)} | {k} | " + " | ".join(
            f"{_p(g.loc[c, 'kacirma_eski'])} / {_p(g.loc[c, 'kacirma_yeni'])}" for c in classes)
            + " |")
    L.append("\n## S2 — oran senaryosu: kaçırma oranı (eski / yeni)\n")
    L.append("| Dosya | Oran | k | " + " | ".join(classes) + " |")
    L.append("| --- | --- | --- |" + " --- |" * len(classes))
    for (n, r), g in s2.groupby(["n", "oran"], sort=True):
        g = g.set_index("sinif")
        L.append(f"| {tr_int(n)} | {tr_pct(r, 1)} | {int(g['k'].iloc[0])} | " + " | ".join(
            f"{_p(g.loc[c, 'kacirma_eski'])} / {_p(g.loc[c, 'kacirma_yeni'])}" for c in classes)
            + " |")
    L.append("\n## S3 — doğal dağılım (eski / yeni)\n")
    L.append("| Dosya | Yanlış KRİTİK | Düşürülen gerçek saldırı |\n| --- | --- | --- |")
    for r in s3.itertuples():
        L.append(f"| {tr_int(r.n)} | {_p(r.yanlis_kritik_eski)} / {_p(r.yanlis_kritik_yeni)} | "
                 f"{_p(r.dusurulen_gercek_eski)} / {_p(r.dusurulen_gercek_yeni)} |")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
