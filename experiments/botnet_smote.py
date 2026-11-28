"""Botnet SMOTE hedefi × Botnet eşiği × tohum denemesi (11. hafta) — yalnızca DOĞRULAMA.

Seçim ölçütü deneyden ÖNCE yazıldı ve commit edildi: reports/hafta11/botnet_secim_olcutu.md
(commit f7c5d54). Bu betik ölçütü olduğu gibi uygular; test kümesine dokunmaz.

Izgara: Botnet SMOTE hedefi T ∈ {yok, 2.500, 5.000, 10.000} × eşik t ∈ {0,30; 0,50; 0,70}
× tohum s ∈ {42, 43, 44}. Diğer küçük sınıflar 10.000'e tamamlanır. Tohum hem SMOTE'un hem RF'nin
random_state'idir; bölme tohumu 42 sabit. Eşik aynı modelin olasılıklarından hesaplanır.

Kullanım:
    python experiments/botnet_smote.py --sample-frac 0.05   # hızlı deneme
    python experiments/botnet_smote.py                      # tam veri (~12 RF eğitimi)
Çıktılar: reports/hafta11/smote_deneme_{ham,ozet}.csv, smote_deneme.md, smote_deneme_karar.json
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

from experiments.alarm_threshold import validation_data  # noqa: E402
from run_pipeline import setup_logger, tr_int  # noqa: E402
from src import config  # noqa: E402
from src.evaluate import predict_with_threshold  # noqa: E402
from src.preprocess import oversample  # noqa: E402

TARGETS = [None, 2_500, 5_000, 10_000]       # None = Botnet çoğaltılmaz
THRESHOLDS = [0.30, 0.50, 0.70]
SEEDS = [42, 43, 44]
REF = (10_000, 0.30)
RECALL_MIN = 0.90
RECALL_REL = 0.02            # R'nin recall'u %90'ın altındaysa: R − 2 puan
OTHER_F1_DROP = 0.005        # Botnet dışı sınıflarda en fazla 0,5 puan düşüş
MIN_GAIN = 0.01              # en az 1 puan Botnet F1 kazancı
TIE = 0.001                  # 0,1 puandan küçük fark = eşit


def metrics(y, pred, cn):
    """Sınıf bazında F1 + Botnet recall/precision + Benign↔Botnet hata sayıları."""
    from sklearn.metrics import f1_score, precision_score, recall_score
    labels = list(range(len(cn)))
    f1 = f1_score(y, pred, labels=labels, average=None, zero_division=0)
    b, k = cn.index("Benign"), cn.index("Botnet")
    row = {f"f1_{c}": float(v) for c, v in zip(cn, f1)}
    row.update({"macro_f1": float(f1.mean()),
                "botnet_recall": float(recall_score(y, pred, labels=[k], average="macro",
                                                    zero_division=0)),
                "botnet_precision": float(precision_score(y, pred, labels=[k], average="macro",
                                                          zero_division=0)),
                "fp_benign_botnet": int(((y == b) & (pred == k)).sum()),
                "fn_botnet_benign": int(((y == k) & (pred == b)).sum())})
    row["botnet_f1"] = row["f1_Botnet"]
    return row


def summarize(raw, cn):
    """(T, t) başına tohum ortalaması ve örneklem standart sapması (ddof=1)."""
    cols = [c for c in raw.columns if c not in ("T", "t", "tohum", "egitim_sn")]
    g = raw.groupby(["T", "t"], sort=False)[cols]
    mean, std = g.mean(), g.std(ddof=1)
    out = mean.add_suffix("_ort").join(std.add_suffix("_std")).reset_index()
    out["tohum_sayisi"] = g.size().to_numpy()
    return out


def decide(summary, cn):
    """Önceden yazılmış ölçütü uygular. T sütununda 'yok' = Botnet çoğaltılmaz."""
    key = lambda T, t: (summary["T"] == T) & (np.isclose(summary["t"], t))
    ref = summary[key(*REF)].iloc[0]
    ref_recall = float(ref["botnet_recall_ort"])
    recall_floor = RECALL_MIN if ref_recall >= RECALL_MIN else ref_recall - RECALL_REL
    others = [c for c in cn if c != "Botnet"]
    s = summary.copy()
    s["recall_uygun"] = s["botnet_recall_ort"] >= recall_floor - 1e-12
    s["diger_uygun"] = np.all(np.column_stack(
        [s[f"f1_{c}_ort"] >= ref[f"f1_{c}_ort"] - OTHER_F1_DROP - 1e-12 for c in others]), axis=1)
    s["uygun"] = s["recall_uygun"] & s["diger_uygun"]
    ok = s[s["uygun"]]
    if ok.empty:
        return s, {"secilen": None, "benimsendi": False, "neden": "uygun aday yok",
                   "recall_siniri": recall_floor}
    best = ok["botnet_f1_ort"].max()
    near = ok[ok["botnet_f1_ort"] >= best - TIE].copy()
    # Eşitlikte mevcut ayara yakın olan: önce T = 10.000, sonra büyük T; aynı T'de küçük t
    order_T = {10_000: 0, 5_000: 1, 2_500: 2, "yok": 3}
    near["_o"] = near["T"].map(order_T)
    ch = near.sort_values(["_o", "t"]).iloc[0]
    gain = float(ch["botnet_f1_ort"] - ref["botnet_f1_ort"])
    spread = float(max(ch["botnet_f1_std"], ref["botnet_f1_std"]))
    adopt = bool(gain >= MIN_GAIN and gain > spread)
    is_ref = ch["T"] == REF[0] and np.isclose(ch["t"], REF[1])
    if is_ref:
        why = "en iyi uygun aday mevcut ayarın kendisi"
    elif adopt:
        why = f"kazanç {gain * 100:.2f} puan ≥ 1 puan ve > tohum sapması {spread * 100:.2f} puan"
    else:
        why = (f"kazanç {gain * 100:.2f} puan; gerekli: ≥ 1 puan ve > tohum sapması "
               f"{spread * 100:.2f} puan")
    return s, {"secilen": {"T": ch["T"], "t": float(ch["t"])}, "kazanc": gain,
               "tohum_sapmasi": spread, "benimsendi": adopt and not is_ref, "neden": why,
               "recall_siniri": recall_floor,
               "referans": {"botnet_f1_ort": float(ref["botnet_f1_ort"]),
                            "botnet_f1_std": float(ref["botnet_f1_std"]),
                            "botnet_recall_ort": float(ref["botnet_recall_ort"])}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(config.DATA_DIR))
    ap.add_argument("--sample-frac", type=float, default=None)
    args = ap.parse_args(argv)
    out = config.REPORTS_DIR / "hafta11"
    if args.sample_frac:
        out = out / f"deneme_frac{args.sample_frac}"
    out.mkdir(parents=True, exist_ok=True)
    log = setup_logger(out / "smote_deneme_log.txt")
    t0 = time.perf_counter()

    cn, V, P = validation_data(args, log)
    k = cn.index("Botnet")
    y = np.asarray(V["y_val"])
    n_bot = int((np.asarray(P["y_fit"]) == k).sum())
    log(f"Alt-eğitim Botnet: {n_bot:,} · doğrulama Botnet: {int((y == k).sum()):,}")

    from sklearn.ensemble import RandomForestClassifier
    rows = []
    for T in TARGETS:
        for seed in SEEDS:
            t1 = time.perf_counter()
            Xs, ys, _ = oversample(P["X_fit"], P["y_fit"], log, target=config.SMOTE_TARGET,
                                   class_targets={k: n_bot if T is None else T},
                                   random_state=seed)
            model = RandomForestClassifier(**{**config.RF_PARAMS, "random_state": seed}).fit(Xs, ys)
            proba = model.predict_proba(P["X_eval"])
            col = list(model.classes_).index(k)
            sec = time.perf_counter() - t1
            for t in THRESHOLDS:
                pred = np.asarray(model.classes_)[predict_with_threshold(proba, col, t)]
                r = metrics(y, pred, cn)
                rows.append({"T": "yok" if T is None else T, "t": t, "tohum": seed,
                             "egitim_sn": sec, **r})
                log(f"T={rows[-1]['T']} t={t} s={seed}: Botnet F1 {r['botnet_f1']:.4f} "
                    f"recall {r['botnet_recall']:.4f} FP {r['fp_benign_botnet']} "
                    f"Macro F1 {r['macro_f1']:.4f}")
            del model, proba, Xs, ys
    raw = pd.DataFrame(rows)
    raw.to_csv(out / "smote_deneme_ham.csv", index=False, encoding="utf-8")
    summary = summarize(raw, cn)
    summary, dec = decide(summary, cn)
    summary.to_csv(out / "smote_deneme_ozet.csv", index=False, encoding="utf-8")
    dec.update({"alt_egitim_botnet": n_bot, "dogrulama_botnet": int((y == k).sum()),
                "dogrulama_satir": int(len(y)), "ornekleme_orani": args.sample_frac,
                "sure_dk": (time.perf_counter() - t0) / 60})
    (out / "smote_deneme_karar.json").write_text(
        json.dumps(dec, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_report(out / "smote_deneme.md", summary, dec, cn)
    log(f"Karar: {dec} · {dec['sure_dk']:.1f} dk")
    return summary, dec


def p(x):
    return f"%{x * 100:.2f}".replace(".", ",")


def pp(x):
    return f"{x * 100:.2f}".replace(".", ",")


def write_report(path, s, d, cn):
    L = ["# Botnet SMOTE hedefi denemesi — doğrulama sonuçları\n"]
    if d["ornekleme_orani"]:
        L.append("> **Uyarı:** örneklem çalıştırması; sayılar rapora yazılmaz.\n")
    L.append(f"Ölçüt: `reports/hafta11/botnet_secim_olcutu.md` (deneyden önce commit edildi). "
             f"Alt-eğitim Botnet {tr_int(d['alt_egitim_botnet'])}, doğrulama "
             f"{tr_int(d['dogrulama_satir'])} satır ({tr_int(d['dogrulama_botnet'])} Botnet). "
             f"Her hücre {len(SEEDS)} tohumun ortalaması ± standart sapma. Recall sınırı "
             f"{p(d['recall_siniri'])}. Süre {d['sure_dk']:.1f} dk.\n")
    L.append("| Botnet SMOTE | Eşik | Botnet F1 | Recall | Precision | FP (Benign→Botnet) | "
             "Macro F1 | Uygun |")
    L.append("| --- |" + " --- |" * 7)
    for r in s.itertuples():
        T = "yok" if r.T == "yok" else tr_int(r.T)
        L.append(f"| {T} | {str(r.t).replace('.', ',')} | {pp(r.botnet_f1_ort)} ± {pp(r.botnet_f1_std)} | "
                 f"{pp(r.botnet_recall_ort)} ± {pp(r.botnet_recall_std)} | "
                 f"{pp(r.botnet_precision_ort)} ± {pp(r.botnet_precision_std)} | "
                 f"{r.fp_benign_botnet_ort:.1f} | {pp(r.macro_f1_ort)} | "
                 f"{'evet' if r.uygun else 'hayır'} |")
    L.append("\nBotnet dışı sınıfların ortalama F1'i (puan):\n")
    others = [c for c in cn if c != "Botnet"]
    L.append("| Botnet SMOTE | Eşik | " + " | ".join(others) + " |")
    L.append("| --- | --- |" + " --- |" * len(others))
    for r in s.to_dict("records"):
        T = "yok" if r["T"] == "yok" else tr_int(r["T"])
        L.append(f"| {T} | {str(r['t']).replace('.', ',')} | "
                 + " | ".join(pp(r[f'f1_{c}_ort']) for c in others) + " |")
    L.append("\n## Karar\n")
    if d["secilen"] is None:
        L.append(f"Uygun aday yok → **mevcut ayar (10.000; 0,30) kalır**.")
    else:
        sel = d["secilen"]
        L.append(f"Uygun adaylar içinde en yüksek ortalama Botnet F1: T = {sel['T']}, "
                 f"t = {str(sel['t']).replace('.', ',')}. Referans (10.000; 0,30): "
                 f"{pp(d['referans']['botnet_f1_ort'])} ± {pp(d['referans']['botnet_f1_std'])}. "
                 f"Gerekçe: {d['neden']}.\n")
        L.append("**Yeni ayar benimsendi.**" if d["benimsendi"] else
                 "**Mevcut ayar (10.000; 0,30) kalır; test kümesi kullanılmaz.**")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
