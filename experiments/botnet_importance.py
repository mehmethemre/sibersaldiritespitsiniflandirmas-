"""Botnet – Benign karışıklığı için öznitelik önem analizi (11. hafta) — yalnızca DOĞRULAMA.

Model 9. hafta ayarlarıyla yalnızca ALT-EĞİTİMDE eğitilir (experiments/alarm_threshold.py::
validation_model), tahmin doğrulama kümesinde Botnet eşiği 0,30 ile yapılır
(src/evaluate.py::predict_classes). Test kümesi kullanılmaz.

Adımlar
1) Dört grup: TP (doğru Botnet), FP (Botnet'e kaçan Benign), FN (Benign'e kaçan Botnet),
   TN (doğru Benign). Botnet'in başka saldırı sınıflarına kaçan satırları ayrıca sayılır.
2) Genel önem: RF impurity önemi (eğitimden) ve doğrulamada permutation importance
   (puan: Macro F1 ve Botnet F1, ikisi de eşik kuralıyla; n_repeats=5).
3) Botnet F1'e göre permutation sıralamasındaki ilk 10 öznitelikte dört grubun medyan ve
   çeyrekleri + kutu grafiği.
4) FP akışların ortak özellikleri: her grubun alt-eğitimdeki (Benign + Botnet) en yakın 10
   komşusunda Botnet oranı; FP vektörlerinin alt-eğitimde birebir Botnet olarak, FN
   vektörlerinin birebir Benign olarak geçme oranı.

SHAP kurulu değil ve 100 ağaçlı derin RF'de yavaş; bu yüzden permutation + dağılım
karşılaştırması kullanıldı.

Kullanım:
    python experiments/botnet_importance.py --sample-frac 0.05   # hızlı deneme
    python experiments/botnet_importance.py                      # tam veri
Çıktılar: reports/hafta11/onem_*.csv, gruplar_*.csv, *.png, botnet_analiz.md, botnet_analiz_ozet.json
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

from experiments.alarm_threshold import validation_model  # noqa: E402
from run_pipeline import setup_logger, tr_int, tr_pct  # noqa: E402
from src import config  # noqa: E402
from src.evaluate import predict_classes  # noqa: E402

GROUPS = ["TP", "FP", "FN", "TN"]
GROUP_NAMES = {"TP": "Doğru Botnet", "FP": "Botnet'e kaçan Benign",
               "FN": "Benign'e kaçan Botnet", "TN": "Doğru Benign"}
TOP_K = 10
N_REPEATS = 5
TN_SAMPLE = 50_000           # grafik için TN örneklemi (TN çok büyük)
TN_QUERY = 5_000             # komşuluk sorgusu için TN örneklemi
N_NEIGHBORS = 10
# FP şablonunu tanımlayan sütunlar: dört grup tablosunda FP'lerin çeyrek aralığı sıfır olan,
# akışın boyutunu ve TCP penceresini veren sütunlar
TEMPLATE_COLS = ["Init_Win_bytes_forward", "Init_Win_bytes_backward",
                 "Total Length of Fwd Packets", "Total Length of Bwd Packets", "Max Packet Length"]
EXTRA_DESC = ["Flow Duration", "Fwd Header Length", "ACK Flag Count", "PSH Flag Count",
              "FIN Flag Count"]


def groups(y_true, y_pred, b, k):
    """Dört grubun satır maskeleri. b: Benign kodu, k: Botnet kodu."""
    return {"TP": (y_true == k) & (y_pred == k), "FP": (y_true == b) & (y_pred == k),
            "FN": (y_true == k) & (y_pred == b), "TN": (y_true == b) & (y_pred == b)}


def make_scorer(class_names, k):
    """permutation_importance için çok ölçütlü puanlayıcı (eşik kuralı dahil)."""
    from sklearn.metrics import f1_score

    def score(est, X, y):
        pred, _ = predict_classes(est, X, class_names, config.BOTNET_THRESHOLD)
        return {"macro_f1": f1_score(y, pred, average="macro"),
                "botnet_f1": f1_score(y, pred, labels=[k], average="macro")}
    return score


def group_quartiles(X_raw, masks, feats):
    rows = []
    for f in feats:
        for g in GROUPS:
            v = X_raw.loc[masks[g], f]
            if len(v) == 0:
                continue
            q1, med, q3 = np.percentile(v, [25, 50, 75])
            rows.append({"oznitelik": f, "grup": g, "n": int(len(v)), "q1": q1, "medyan": med,
                         "q3": q3, "sifir_orani": float((v == 0).mean())})
    return pd.DataFrame(rows)


def exact_match_rate(rows, ref):
    """rows'taki vektörlerin kaçı ref içinde birebir geçiyor (oran)."""
    if len(rows) == 0:
        return float("nan")
    ref_set = {r.tobytes() for r in np.ascontiguousarray(ref, dtype=np.float32)}
    hits = sum(r.tobytes() in ref_set for r in np.ascontiguousarray(rows, dtype=np.float32))
    return hits / len(rows)


def neighbour_botnet_share(X_val, masks, X_fit, y_fit, b, k, rng, n_neighbors=N_NEIGHBORS,
                           tn_sample=TN_QUERY):
    """Her gruptaki akışın, alt-eğitimin Benign + Botnet satırları arasındaki (ölçekli uzay)
    en yakın `n_neighbors` komşusunda Botnet oranı. Aynı referans kümesi tüm gruplar için
    kullanılır; böylece gruplar birbiriyle karşılaştırılabilir. TN çok büyük olduğundan
    rastgele `tn_sample` satır sorgulanır."""
    from sklearn.neighbors import NearestNeighbors
    ref = (y_fit == b) | (y_fit == k)
    lab = y_fit[ref] == k
    nn = NearestNeighbors(n_neighbors=n_neighbors, n_jobs=-1).fit(X_fit[ref])
    out = {}
    for g in GROUPS:
        idx = np.flatnonzero(masks[g])
        if g == "TN":
            idx = rng.choice(idx, min(tn_sample, len(idx)), replace=False)
        if len(idx) == 0:
            continue
        dist, j = nn.kneighbors(X_val[idx])
        share = lab[j].mean(axis=1)
        out[g] = {"n": int(len(idx)), "botnet_orani_ort": float(share.mean()),
                  "cogunlugu_botnet": float((share > 0.5).mean()),
                  "en_yakin_botnet": float(lab[j[:, 0]].mean()),
                  "en_yakin_uzaklik_medyan": float(np.median(dist[:, 0]))}
    return out


def fp_template(X_raw, masks, X_fit_df, y_fit, b, k, cols=TEMPLATE_COLS):
    """FP akışlarda `cols` üzerindeki en sık değer birleşimi (şablon) ve bu şablonun her
    grupta ve alt-eğitimin Benign / Botnet satırlarında görülme oranı."""
    fp = X_raw.loc[masks["FP"], cols]
    if fp.empty:
        return None
    mode = fp.value_counts().index[0]
    key = dict(zip(cols, (float(v) for v in mode)))
    match = lambda df: np.all(np.column_stack([df[c].to_numpy() == key[c] for c in cols]), axis=1)
    m_val = match(X_raw)
    m_fit = match(X_fit_df)
    out = {"sablon": key,
           "gruplar": {g: {"n": int(masks[g].sum()), "eslesen": int((m_val & masks[g]).sum())}
                       for g in GROUPS},
           "alt_egitim": {"Benign": {"n": int((y_fit == b).sum()),
                                     "eslesen": int((m_fit & (y_fit == b)).sum())},
                          "Botnet": {"n": int((y_fit == k).sum()),
                                     "eslesen": int((m_fit & (y_fit == k)).sum())}}}
    return out


def threshold_sensitivity(proba_bot, y, b, k, thresholds=(0.3, 0.5, 0.7)):
    """Yalnızca betimleyici: farklı Botnet eşiklerinde TP / FP / FN (Benign↔Botnet).
    Eşik 8. haftada seçildi; bu tablo seçim için kullanılmaz."""
    rows = []
    for t in thresholds:
        pb = proba_bot >= t
        rows.append({"esik": t, "TP": int((pb & (y == k)).sum()),
                     "FP": int((pb & (y == b)).sum()), "FN_botnet_kacan": int((~pb & (y == k)).sum())})
    return rows


def plot_importance(imp, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    top = imp.sort_values("perm_botnet_f1", ascending=False).head(15)[::-1]
    fig, axes = plt.subplots(1, 3, figsize=(15, 6), sharey=True)
    for ax, col, title in zip(axes, ["impurity", "perm_macro_f1", "perm_botnet_f1"],
                              ["RF impurity önemi", "Permutation (Macro F1 düşüşü)",
                               "Permutation (Botnet F1 düşüşü)"]):
        err = top.get(col + "_std")
        ax.barh(top["oznitelik"], top[col], xerr=err, color="#4C72B0")
        ax.set_title(title)
        ax.grid(axis="x", alpha=0.3)
    fig.suptitle("Öznitelik önemi — Botnet F1 permutation sıralamasındaki ilk 15 (doğrulama)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_groups(X_raw, masks, feats, path, rng):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"TP": "#C44E52", "FP": "#DD8452", "FN": "#8172B2", "TN": "#55A868"}
    tn = np.flatnonzero(masks["TN"])
    tn_keep = np.zeros(len(X_raw), bool)
    tn_keep[rng.choice(tn, min(TN_SAMPLE, len(tn)), replace=False)] = True
    sel = {**masks, "TN": tn_keep}
    n = len(feats)
    cols = 5
    fig, axes = plt.subplots(int(np.ceil(n / cols)), cols, figsize=(4 * cols, 3.6 * np.ceil(n / cols)))
    for ax, f in zip(axes.ravel(), feats):
        data = [np.log10(1 + np.abs(X_raw.loc[sel[g], f].to_numpy())) * np.sign(
            X_raw.loc[sel[g], f].to_numpy()) for g in GROUPS]
        bp = ax.boxplot(data, tick_labels=GROUPS, showfliers=False, patch_artist=True)
        for patch, g in zip(bp["boxes"], GROUPS):
            patch.set_facecolor(colors[g])
            patch.set_alpha(0.7)
        ax.set_title(f, fontsize=9)
        ax.set_ylabel("sign·log10(1+|x|)", fontsize=7)
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    fig.suptitle("Dört grubun dağılımı (doğrulama; TN için rastgele "
                 f"{tr_int(int(tn_keep.sum()))} satır, aykırı değerler gizli)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_proba(proba_bot, masks, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4))
    bins = np.linspace(0, 1, 41)
    for g, c in [("TP", "#C44E52"), ("FP", "#DD8452"), ("FN", "#8172B2")]:
        if masks[g].any():
            ax.hist(proba_bot[masks[g]], bins=bins, alpha=0.6, label=f"{g} ({GROUP_NAMES[g]})",
                    color=c)
    ax.axvline(config.BOTNET_THRESHOLD, color="k", ls="--", label="eşik 0,30")
    ax.set_xlabel("Botnet olasılığı")
    ax.set_ylabel("akış sayısı")
    ax.legend(fontsize=8)
    ax.set_title("Botnet olasılığının dağılımı (doğrulama)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(config.DATA_DIR))
    ap.add_argument("--sample-frac", type=float, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--n-repeats", type=int, default=N_REPEATS)
    args = ap.parse_args(argv)
    out = Path(args.out) if args.out else config.REPORTS_DIR / "hafta11"
    if args.sample_frac and not args.out:
        out = out / f"deneme_frac{args.sample_frac}"
    out.mkdir(parents=True, exist_ok=True)
    log = setup_logger(out / "botnet_analiz_log.txt")
    t0 = time.perf_counter()
    rng = np.random.default_rng(config.RANDOM_STATE)

    M = validation_model(args, log)
    cn, feats, model = M["class_names"], M["features"], M["model"]
    b, k = cn.index("Benign"), cn.index("Botnet")
    y, pred = M["y_val"], M["pred"]
    X_raw = M["X_val_raw"].reset_index(drop=True)
    masks = groups(y, pred, b, k)
    counts = {g: int(m.sum()) for g, m in masks.items()}
    bot_other = {cn[c]: int(((y == k) & (pred == c)).sum()) for c in range(len(cn))
                 if c not in (b, k) and ((y == k) & (pred == c)).any()}
    fp_other = {cn[c]: int(((y == c) & (pred == k)).sum()) for c in range(len(cn))
                if c not in (b, k) and ((y == c) & (pred == k)).any()}
    log(f"Gruplar: {counts} · Botnet->diğer saldırı: {bot_other} · diğer saldırı->Botnet: {fp_other}")

    # --- genel önem
    from sklearn.inspection import permutation_importance
    t1 = time.perf_counter()
    base = make_scorer(cn, k)(model, M["X_val"], y)
    pi = permutation_importance(model, M["X_val"], y, scoring=make_scorer(cn, k),
                                n_repeats=args.n_repeats, random_state=config.RANDOM_STATE,
                                n_jobs=1)
    perm_min = (time.perf_counter() - t1) / 60
    imp = pd.DataFrame({"oznitelik": feats, "impurity": model.feature_importances_,
                        "perm_macro_f1": pi["macro_f1"]["importances_mean"],
                        "perm_macro_f1_std": pi["macro_f1"]["importances_std"],
                        "perm_botnet_f1": pi["botnet_f1"]["importances_mean"],
                        "perm_botnet_f1_std": pi["botnet_f1"]["importances_std"]})
    for col in ["impurity", "perm_macro_f1", "perm_botnet_f1"]:
        imp["sira_" + col] = imp[col].rank(ascending=False, method="min").astype(int)
    imp = imp.sort_values("perm_botnet_f1", ascending=False).reset_index(drop=True)
    imp.to_csv(out / "onem_tablosu.csv", index=False, encoding="utf-8")
    log(f"Permutation ({args.n_repeats} tekrar, {len(y):,} satır): {perm_min:.1f} dk · "
        f"temel puan {base}")

    # Korelasyon: impurity'de üstte ama permutation'da sıfıra yakın olanların ikizleri
    corr = X_raw[feats].corr().abs()
    top_imp = imp.sort_values("impurity", ascending=False).head(TOP_K)["oznitelik"]
    twins = []
    for f in top_imp:
        c = corr[f].drop(f)
        twins.append({"oznitelik": f, "en_ilintili": c.idxmax(), "abs_r": float(c.max())})
    twins = pd.DataFrame(twins)

    # --- dört grup
    top = list(imp["oznitelik"].head(TOP_K))
    extra = [f for f in EXTRA_DESC if f in feats and f not in top]
    qt = group_quartiles(X_raw, masks, top + extra)
    qt.to_csv(out / "gruplar_ceyrekler.csv", index=False, encoding="utf-8")
    proba_bot = M["proba"][:, list(model.classes_).index(k)]
    pstats = {g: {"n": counts[g], "medyan": float(np.median(proba_bot[masks[g]])),
                  "q1": float(np.percentile(proba_bot[masks[g]], 25)),
                  "q3": float(np.percentile(proba_bot[masks[g]], 75))}
              for g in GROUPS if counts[g]}

    # --- FP / FN ortak özellikleri
    nb = neighbour_botnet_share(M["X_val"], masks, M["X_fit"], M["y_fit"], b, k, rng)
    # Tekrar silme bölmeden önce tüm veride yapıldığı için aynı vektör + aynı etiket iki
    # kümede birden olamaz; yalnızca ZIT etiketli birebir eşleşme anlamlıdır.
    Xv = X_raw[feats].to_numpy(np.float32)
    Xf, yf = M["X_fit_raw"], M["y_fit"]
    exact = {"FP_altegitimde_botnet": exact_match_rate(Xv[masks["FP"]], Xf[yf == k]),
             "FN_altegitimde_benign": exact_match_rate(Xv[masks["FN"]], Xf[yf == b])}
    log(f"En yakın komşu: {nb} · Birebir eşleşme: {exact}")
    tpl = fp_template(X_raw, masks, pd.DataFrame(Xf, columns=feats), yf, b, k,
                      cols=[c for c in TEMPLATE_COLS if c in feats])  # örneklemde seçim farklı olabilir
    sens = threshold_sensitivity(proba_bot, y, b, k)
    log(f"FP şablonu: {tpl} · Eşik duyarlılığı: {sens}")

    plot_importance(imp, out / "onem_karsilastirma.png")
    plot_groups(X_raw, masks, top, out / "dort_grup_dagilim.png", rng)
    plot_proba(proba_bot, masks, out / "botnet_olasilik.png")

    summary = {"ornekleme_orani": args.sample_frac, "dogrulama_satir": int(len(y)),
               "alt_egitim_satir": int(M["n_sub"]), "oznitelik_sayisi": len(feats),
               "gruplar": counts, "botnet_diger_saldiri": bot_other,
               "diger_saldiri_botnet": fp_other, "temel_puan": base,
               "permutation_tekrar": args.n_repeats, "permutation_dk": perm_min,
               "ilk10_botnet_perm": top, "botnet_olasilik": pstats,
               "en_yakin_komsu": nb, "birebir_eslesme": exact,
               "ek_betimleyici": extra, "fp_sablonu": tpl, "esik_duyarliligi": sens,
               "impurity_ikizleri": twins.to_dict("records"),
               "sure_dk": (time.perf_counter() - t0) / 60}
    (out / "botnet_analiz_ozet.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    write_report(out / "botnet_analiz.md", summary, imp, qt, twins)
    log(f"Bitti: {summary['sure_dk']:.1f} dk · Çıktılar: {out}")
    return summary, imp, qt


def fmt(x):
    if abs(x) >= 1000:
        return tr_int(int(round(x)))
    return f"{x:.3g}".replace(".", ",")


def write_report(path, s, imp, qt, twins):
    L = ["# Botnet – Benign öznitelik önem analizi (doğrulama kümesi)\n"]
    if s["ornekleme_orani"]:
        L.append("> **Uyarı:** örneklem çalıştırması; sayılar rapora yazılmaz.\n")
    g = s["gruplar"]
    L.append(f"Alt-eğitim {tr_int(s['alt_egitim_satir'])} satır, doğrulama "
             f"{tr_int(s['dogrulama_satir'])} satır, {s['oznitelik_sayisi']} öznitelik, "
             "Botnet eşiği 0,30.\n")
    L.append("| Grup | Akış |\n| --- | --- |")
    for k in GROUPS:
        L.append(f"| {k} — {GROUP_NAMES[k]} | {tr_int(g[k])} |")
    L.append(f"\nBotnet → diğer saldırı: {s['botnet_diger_saldiri'] or 'yok'} · "
             f"diğer saldırı → Botnet: {s['diger_saldiri_botnet'] or 'yok'}\n")
    L.append(f"Temel puan: Macro F1 {fmt(s['temel_puan']['macro_f1'])}, Botnet F1 "
             f"{fmt(s['temel_puan']['botnet_f1'])}. Permutation: {s['permutation_tekrar']} tekrar, "
             f"{s['permutation_dk']:.1f} dk.\n")
    L.append("## Öznitelik önemi (Botnet F1 permutation sırasına göre ilk 15)\n")
    L.append("| # | Öznitelik | Impurity (sıra) | Perm. Macro F1 (sıra) | Perm. Botnet F1 (sıra) |")
    L.append("| --- | --- | --- | --- | --- |")
    for i, r in imp.head(15).iterrows():
        L.append(f"| {i + 1} | {r.oznitelik} | {fmt(r.impurity)} ({r.sira_impurity}) | "
                 f"{fmt(r.perm_macro_f1)} ({r.sira_perm_macro_f1}) | "
                 f"{fmt(r.perm_botnet_f1)} ± {fmt(r.perm_botnet_f1_std)} ({r.sira_perm_botnet_f1}) |")
    L.append("\n## Impurity'de ilk 10 ve en ilintili ikizleri (doğrulama, |r|)\n")
    L.append("| Öznitelik | Impurity sırası | Perm. Botnet sırası | En ilintili | abs r |")
    L.append("| --- | --- | --- | --- | --- |")
    by = imp.set_index("oznitelik")
    for r in twins.itertuples():
        L.append(f"| {r.oznitelik} | {by.loc[r.oznitelik, 'sira_impurity']} | "
                 f"{by.loc[r.oznitelik, 'sira_perm_botnet_f1']} | {r.en_ilintili} | {fmt(r.abs_r)} |")
    L.append("\n## Dört grubun dağılımı (medyan [Q1–Q3]; sıfır oranı)\n")
    L.append("| Öznitelik | " + " | ".join(GROUPS) + " |")
    L.append("| --- |" + " --- |" * len(GROUPS))
    for f in s["ilk10_botnet_perm"] + s["ek_betimleyici"]:
        cells = []
        for k in GROUPS:
            r = qt[(qt.oznitelik == f) & (qt.grup == k)]
            cells.append("—" if r.empty else f"{fmt(r.medyan.iloc[0])} [{fmt(r.q1.iloc[0])}–"
                         f"{fmt(r.q3.iloc[0])}]; {tr_pct(r.sifir_orani.iloc[0], 0)}")
        L.append(f"| {f} | " + " | ".join(cells) + " |")
    L.append("\n## Botnet olasılığı (medyan [Q1–Q3])\n")
    for k, v in s["botnet_olasilik"].items():
        L.append(f"- {k}: {fmt(v['medyan'])} [{fmt(v['q1'])}–{fmt(v['q3'])}], n={tr_int(v['n'])}")
    L.append("\n## Yanlış sınıflanan akışlar neye benziyor?\n")
    L.append(f"Alt-eğitimin Benign + Botnet satırları arasında (ölçekli uzay) en yakın "
             f"{N_NEIGHBORS} komşu. TN için rastgele {tr_int(TN_QUERY)} satır sorgulandı.\n")
    L.append("| Grup | n | Komşularda Botnet oranı (ort.) | Komşularının çoğu Botnet | "
             "En yakın komşu Botnet | En yakın uzaklık (medyan) |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for k, v in s["en_yakin_komsu"].items():
        L.append(f"| {k} | {tr_int(v['n'])} | {tr_pct(v['botnet_orani_ort'], 1)} | "
                 f"{tr_pct(v['cogunlugu_botnet'], 1)} | {tr_pct(v['en_yakin_botnet'], 1)} | "
                 f"{fmt(v['en_yakin_uzaklik_medyan'])} |")
    e = s["birebir_eslesme"]
    L.append("\nZıt etiketli birebir eşleşme (tekrar silme tüm veride yapıldığı için aynı etiketli "
             "eşleşme tanım gereği olamaz):\n")
    L.append(f"- FP vektörlerinin alt-eğitimde birebir **Botnet** olarak geçme oranı "
             f"{tr_pct(e['FP_altegitimde_botnet'], 1)}")
    L.append(f"- FN vektörlerinin alt-eğitimde birebir **Benign** olarak geçme oranı "
             f"{tr_pct(e['FN_altegitimde_benign'], 1)}")
    L.append("\n(İlk 10'dan sonraki satırlar önem sırasından değil, betimleme için eklendi: "
             + ", ".join(s["ek_betimleyici"]) + ".)\n")
    t = s["fp_sablonu"]
    if t:
        L.append("## FP şablonu\n")
        L.append("FP akışlarda en sık görülen değer birleşimi: "
                 + ", ".join(f"{c} = {fmt(v)}" for c, v in t["sablon"].items()) + ".\n")
        L.append("| Küme | Satır | Şablona uyan | Oran |\n| --- | --- | --- | --- |")
        for g, v in t["gruplar"].items():
            L.append(f"| Doğrulama {g} | {tr_int(v['n'])} | {tr_int(v['eslesen'])} | "
                     f"{tr_pct(v['eslesen'] / v['n'], 1) if v['n'] else '—'} |")
        for c, v in t["alt_egitim"].items():
            L.append(f"| Alt-eğitim {c} | {tr_int(v['n'])} | {tr_int(v['eslesen'])} | "
                     f"{tr_pct(v['eslesen'] / v['n'], 2)} |")
    L.append("\n## Eşik duyarlılığı (yalnızca betimleyici; eşik 8. haftada seçildi)\n")
    L.append("| Botnet eşiği | TP | FP (Benign→Botnet) | Kaçan Botnet |\n| --- | --- | --- | --- |")
    for r in s["esik_duyarliligi"]:
        L.append(f"| {fmt(r['esik'])} | {tr_int(r['TP'])} | {tr_int(r['FP'])} | "
                 f"{tr_int(r['FN_botnet_kacan'])} |")
    L.append(f"\nSüre: {s['sure_dk']:.1f} dk. Grafikler: onem_karsilastirma.png, "
             "dort_grup_dagilim.png, botnet_olasilik.png\n")
    path.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
