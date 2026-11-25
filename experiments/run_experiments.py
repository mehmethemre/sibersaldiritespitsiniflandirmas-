"""8. hafta deneyleri: SMOTE düzeyi, etiket çakışmaları, port bilgisi, hiperparametre araması,
model karşılaştırması ve tek seferlik final test değerlendirmesi.

GENEL DÜZEN (neden böyle?)
    Ham veri -> temizlik -> katmanlı %80 eğitim / %20 TEST  (7. haftayla aynı, test kümesi aynı)
                              |
                              +-> eğitim: katmanlı %80 ALT-EĞİTİM / %20 DOĞRULAMA
    * Bütün ayar/model karşılaştırmaları DOĞRULAMA kümesinde yapılır. Test kümesine bakarak
      ayar seçersek test sonucu iyimser olur (teste "uyum" sağlamış oluruz).
    * Öznitelik seçimi, ölçekleyici, SMOTE ve çakışma işlemleri her seferinde yalnızca
      model eğitilen tarafa (alt-eğitim, finalde tüm eğitim) uygulanır -> sızıntı yok.
    * Test kümesi yalnızca en sonda, seçilen TEK yapılandırma için BİR kez kullanılır.

Kullanım (proje klasöründe):
    python experiments/run_experiments.py --sample-frac 0.05   # hızlı deneme
    python experiments/run_experiments.py                      # tam veri

Çıktılar: reports/hafta8/ (örneklemli çalıştırmada reports/hafta8/deneme_frac<oran>/)
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:   # `python experiments/run_experiments.py` ile de çalışsın
    sys.path.insert(0, str(ROOT))

from run_pipeline import setup_logger, tr_int, tr_num, tr_pct  # noqa: E402
from src import config  # noqa: E402
from src.data_loader import load_raw  # noqa: E402
from src.evaluate import plot_confusion  # noqa: E402
from src.preprocess import (SmoteTarget, _stratified_sample, clean, fit_scaler,  # noqa: E402
                            oversample, port_category, resolve_label_conflicts,
                            select_features, split, split_train_val)

PORT = config.PORT_COLUMN
PORT_CAT = "Port Kategorisi"
COUNT = "_kopya_sayisi"          # temizlikte eklenen ham kopya sayısı (öznitelik değil)

# 7. hafta sonuçları (reports/metrics.json, tam veri, test kümesi) — karşılaştırma için
WEEK7 = {"accuracy": 0.9985, "macro_f1": 0.9304, "f1_Botnet": 0.6819,
         "f1_PortScan": 0.9413, "benign_to_botnet": 233}

# Deney 1'de denenen dengesizlik ayarları
IMBALANCE_SETTINGS = [
    {"ad": "SMOTE 100.000", "smote": 100_000, "class_weight": None},
    {"ad": "SMOTE 25.000", "smote": 25_000, "class_weight": None},
    {"ad": "SMOTE 10.000", "smote": 10_000, "class_weight": None},
    {"ad": "SMOTE yok + class_weight=balanced", "smote": None, "class_weight": "balanced"},
    {"ad": "SMOTE yok", "smote": None, "class_weight": None},
]
CONFLICT_MODES = {"birak": "Olduğu gibi bırak", "sil": "Çakışan grupları sil",
                  "cogunluk": "Çoğunluk etiketine ata"}
PORT_MODES = {"yok": "A) Port yok (mevcut)", "ham": "B) Ham Destination Port",
              "kategori": "C) Port kategorisi (0-1023 / 1024-49151 / 49152+)"}

# Deney 4: RandomizedSearchCV'nin rastgele seçim yapacağı ızgara
PARAM_GRID = {
    "rf__n_estimators": [100, 200, 300],
    "rf__max_depth": [10, 20, 30, None],
    "rf__min_samples_split": [2, 5, 10],
    "rf__min_samples_leaf": [1, 2, 4],
    "rf__max_features": ["sqrt", "log2", 0.5],
}
LGBM_PARAMS = dict(n_estimators=500, learning_rate=0.05, num_leaves=63,
                   random_state=config.RANDOM_STATE, n_jobs=-1, verbose=-1)


# =============================================================== metrik yardımcıları
def metric_row(y_true, y_pred, class_names):
    """Bir tahmin kümesinden rapora girecek metrikleri tek satırlık sözlük olarak üretir.

    Sınıf bazında değerler sklearn `classification_report` çıktısından alınır (CLAUDE.md).
    """
    labels = list(range(len(class_names)))
    rep = classification_report(y_true, y_pred, labels=labels, target_names=class_names,
                                output_dict=True, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    row = {"accuracy": accuracy_score(y_true, y_pred),
           "macro_f1": rep["macro avg"]["f1-score"]}
    for c in class_names:
        row[f"f1_{c}"] = rep[c]["f1-score"]
    for c in ("Botnet", "PortScan"):
        if c in class_names:
            row[f"{c.lower()}_precision"] = rep[c]["precision"]
            row[f"{c.lower()}_recall"] = rep[c]["recall"]
    if {"Benign", "Botnet"} <= set(class_names):
        row["benign_to_botnet"] = int(cm[class_names.index("Benign"),
                                         class_names.index("Botnet")])
    return row, cm


def best_of(rows, key="macro_f1"):
    """Doğrulama sonuçları arasından seçim ölçütüne (varsayılan Macro F1) göre en iyisi."""
    return max(rows, key=lambda r: r[key])


# =============================================================== veri hazırlama
def build_variant(raw, port_mode, class_names, log):
    """Ham veriden bir port varyantı için test / alt-eğitim / doğrulama kümelerini üretir.

    Port tekrar silmeden ÖNCE eklenir/çıkarılır; bu yüzden her varyantta silinen tekrarlar,
    dolayısıyla bölme ve doğrulama kümesi farklıdır (Deney 3 notu).
    """
    df = raw
    if port_mode == "yok":
        df = raw.drop(columns=[PORT])
    elif port_mode == "kategori":
        df = raw.drop(columns=[PORT]).assign(**{PORT_CAT: port_category(raw[PORT])})
    df, stats = clean(df, log, count_col=COUNT)

    X_tr, X_te, y_tr, y_te = split(df)                  # test kümesi burada ayrılır
    del df
    X_sub, X_val, y_sub, y_val = split_train_val(X_tr, y_tr)
    code = {c: i for i, c in enumerate(class_names)}
    enc = lambda s: s.map(code).to_numpy(np.int64)
    # Kopya sayısı öznitelik değildir: X'ten ayrı bir diziye alınır
    v = {"port_mode": port_mode, "clean_stats": stats,
         "n_train": X_tr[COUNT].to_numpy(), "n_sub": X_sub[COUNT].to_numpy(),
         "X_train": X_tr.drop(columns=COUNT), "y_train": enc(y_tr),
         "X_test": X_te.drop(columns=COUNT), "y_test": enc(y_te),
         "X_sub": X_sub.drop(columns=COUNT), "y_sub": enc(y_sub),
         "X_val": X_val.drop(columns=COUNT), "y_val": enc(y_val)}
    log(f"[{PORT_MODES[port_mode]}] eğitim {len(X_tr):,} -> alt-eğitim {len(X_sub):,} / "
        f"doğrulama {len(X_val):,} · test {len(X_te):,}")
    return v


def prepare(X_fit, y_fit, n_fit, X_eval, conflict_mode, log, force_cols=(), features=None):
    """Model eğitilecek taraf (X_fit) üzerinde sızıntısız hazırlık; X_eval yalnızca dönüştürülür.

    1) etiket çakışmaları (yalnızca X_fit)
    2) öznitelik seçimi (yalnızca X_fit) — `features` verilmişse seçim yapılmaz, o küme kullanılır
    3) StandardScaler X_fit'e fit -> ikisine de transform.
    force_cols: seçimden bağımsız olarak modele mutlaka verilen sütunlar (port deneyi).
    Seçim bu sütunları atsaydı deney anlamsız olurdu; bu yüzden zorla eklenirler.

    Neden sabit `features`? İlk tam veri denemesinde, Deney 2'de yalnızca 254 satır silindiği
    halde yeniden yapılan seçim `Fwd IAT Min`i düşürdü ve Web Attack F1 %93'ten %38'e indi.
    Yani sonuç çakışma işleminden değil seçimin kararsızlığından geliyordu. Bir deneyde yalnızca
    incelenen faktörün değişmesi için öznitelik kümesi Deney 1'de bir kez seçilip sabitlenir.
    """
    X_fit, y_fit, cinfo = resolve_label_conflicts(X_fit, y_fit, n_fit, conflict_mode)
    log(f"Çakışma modu '{conflict_mode}': {cinfo['cakisan_grup']:,} grup, "
        f"{cinfo['cakisan_satir']:,} satır çakışıyor, {cinfo['silinen_satir']:,} satır silindi")
    if features is None:
        features, _ = select_features(X_fit.drop(columns=list(force_cols)), y_fit, log)
    feats = list(features) + list(force_cols)
    Xf = X_fit[feats].to_numpy(np.float32)
    scaler = fit_scaler(Xf)
    return {"X_fit_raw": Xf, "X_fit": scaler.transform(Xf).astype(np.float32), "y_fit": y_fit,
            "X_eval": scaler.transform(X_eval[feats].to_numpy(np.float32)).astype(np.float32),
            "features": feats, "conflict_info": cinfo}


def fit_eval(model, X, y, X_ev, y_ev, smote_target, class_names, log):
    """(İsteğe bağlı SMOTE ->) eğit -> değerlendir. SMOTE yalnızca eğitim matrisine uygulanır."""
    t0 = time.perf_counter()
    if smote_target:
        X, y, _ = oversample(X, y, log, target=smote_target)
    smote_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    model.fit(X, y)
    train_s = time.perf_counter() - t0
    row, cm = metric_row(y_ev, model.predict(X_ev), class_names)
    row.update(smote_suresi_s=smote_s, egitim_suresi_s=train_s, egitim_satir_smote_sonrasi=len(X))
    log(f"  -> Accuracy={row['accuracy']:.4f} MacroF1={row['macro_f1']:.4f} "
        f"BotnetF1={row.get('f1_Botnet', float('nan')):.4f} "
        f"BotnetP={row.get('botnet_precision', float('nan')):.4f} "
        f"BotnetR={row.get('botnet_recall', float('nan')):.4f} "
        f"PortScanF1={row.get('f1_PortScan', float('nan')):.4f} eğitim={train_s:.1f} sn")
    return row, cm, model


def rf(class_weight=None, **over):
    return RandomForestClassifier(**{**config.RF_PARAMS, "class_weight": class_weight, **over})


# =============================================================== deneyler
def experiment1(V, class_names, log):
    """SMOTE düzeyi. Aynı alt-eğitim/doğrulama ve aynı öznitelikler; yalnızca dengesizlik
    ayarı değişir. Böylece fark yalnızca SMOTE düzeyinden kaynaklanır."""
    P = prepare(V["X_sub"], V["y_sub"], V["n_sub"], V["X_val"], "birak", log)
    log(f"Sabitlenen öznitelik kümesi ({len(P['features'])}): {P['features']}")
    rows = []
    for s in IMBALANCE_SETTINGS:
        log(f"Deney 1 · {s['ad']}")
        row, _, _ = fit_eval(rf(s["class_weight"]), P["X_fit"], P["y_fit"], P["X_eval"],
                             V["y_val"], s["smote"], class_names, log)
        rows.append({"ayar": s["ad"], "smote_hedefi": s["smote"] or 0,
                     "class_weight": s["class_weight"] or "-", **row})
    return rows, P["features"]


def experiment2(V, setting, features, class_names, log):
    """Etiket çakışmaları: yalnızca alt-eğitim satırları değişir; doğrulama kümesi ve
    öznitelik kümesi aynı kalır."""
    rows = []
    for mode, name in CONFLICT_MODES.items():
        log(f"Deney 2 · {name}")
        P = prepare(V["X_sub"], V["y_sub"], V["n_sub"], V["X_val"], mode, log,
                    features=features)
        row, _, _ = fit_eval(rf(setting["class_weight"]), P["X_fit"], P["y_fit"], P["X_eval"],
                             V["y_val"], setting["smote"], class_names, log)
        ci = P["conflict_info"]
        rows.append({"mod": mode, "yontem": name, "cakisan_grup": ci["cakisan_grup"],
                     "cakisan_satir": ci["cakisan_satir"], "silinen_satir": ci["silinen_satir"],
                     "esit_oylu_grup": ci["esit_oylu_grup"],
                     "alt_egitim_satir": len(P["y_fit"]), **row})
    return rows


def experiment3(raw, V_none, setting, conflict_mode, features, class_names, log):
    """Port bilgisi. Her varyant kendi temizlik/bölmesini yapar -> doğrulama kümeleri farklı.
    Öznitelikler: Deney 1'de sabitlenen küme + port sütunu; fark yalnızca porttan gelsin."""
    rows = []
    for mode, name in PORT_MODES.items():
        log(f"Deney 3 · {name}")
        V = V_none if mode == "yok" else build_variant(raw, mode, class_names, log)
        force = {"yok": (), "ham": (PORT,), "kategori": (PORT_CAT,)}[mode]
        # Temizlik sabit sütunları siler; port sütunu sabit çıktıysa (tek kategori) uyar
        missing = [c for c in force if c not in V["X_sub"].columns]
        if missing:
            log(f"UYARI: {missing} sabit olduğu için temizlikte silindi; varyant portsuz çalışır")
        force = tuple(c for c in force if c not in missing)
        P = prepare(V["X_sub"], V["y_sub"], V["n_sub"], V["X_val"], conflict_mode, log, force,
                    features=features)
        row, _, _ = fit_eval(rf(setting["class_weight"]), P["X_fit"], P["y_fit"], P["X_eval"],
                             V["y_val"], setting["smote"], class_names, log)
        rows.append({"varyant": name, "tekrar_silinen": V["clean_stats"]["tekrar_silinen"],
                     "temiz_satir": V["clean_stats"]["tekrar_sonrasi"],
                     "alt_egitim_satir": len(V["y_sub"]), "dogrulama_satir": len(V["y_val"]),
                     "dogrulama_botnet": int((V["y_val"] == class_names.index("Botnet")).sum())
                     if "Botnet" in class_names else 0,
                     "oznitelik_sayisi": len(P["features"]), **row})
        if V is not V_none:
            del V
    return rows


def experiment4(P, setting, n_sub_total, cv_sample, n_iter, log, out):
    """Hiperparametre araması: alt-eğitimden katmanlı örneklem + 3 katlı CV.

    Neden imblearn Pipeline? SMOTE CV'den ÖNCE uygulansaydı sentetik Botnet örnekleri,
    kendilerini üreten gerçek örneklerle farklı katlara düşer ve skor şişerdi.
    Pipeline içinde SMOTE her katta yalnızca o katın eğitim kısmına uygulanır.
    Ölçekleyici de pipeline içinde: SMOTE komşuları ölçeklenmiş uzayda bulunur ve
    ölçekleyici her katta yalnızca eğitim kısmına fit edilir.
    """
    from imblearn.over_sampling import SMOTE
    from imblearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    Xs, ys = _stratified_sample(P["X_fit_raw"], P["y_fit"], cv_sample)
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=config.RANDOM_STATE)
    if setting["smote"]:
        # SMOTE hedefi örneklem büyüklüğüne oranlanır: tam alt-eğitimdeki oranı korumak için
        fold_train = len(ys) * (cv.n_splits - 1) / cv.n_splits
        target = max(1, round(setting["smote"] * fold_train / n_sub_total))
        smote_step = SMOTE(sampling_strategy=SmoteTarget(target), k_neighbors=config.SMOTE_K,
                           random_state=config.RANDOM_STATE)
    else:
        target, smote_step = None, "passthrough"
    pipe = Pipeline([("olcek", StandardScaler()), ("smote", smote_step),
                     ("rf", rf(setting["class_weight"]))])
    search = RandomizedSearchCV(pipe, PARAM_GRID, n_iter=n_iter, scoring="f1_macro", cv=cv,
                                random_state=config.RANDOM_STATE, n_jobs=1, refit=False,
                                verbose=1, error_score="raise")
    log(f"Deney 4: {len(ys):,} satırlık örneklem, {n_iter} deneme x 3 kat, "
        f"katta SMOTE hedefi: {target}")
    t0 = time.perf_counter()
    search.fit(Xs, ys)
    search_s = time.perf_counter() - t0

    res = pd.DataFrame(search.cv_results_)
    keep = [c for c in res.columns if c.startswith("param_")] + [
        "mean_test_score", "std_test_score", "mean_fit_time", "rank_test_score"]
    res = res[keep].sort_values("rank_test_score")
    res.columns = [c.replace("param_rf__", "") for c in res.columns]
    res.to_csv(out / "deney4_arama_sonuclari.csv", index=False, encoding="utf-8")
    best = {k.replace("rf__", ""): v for k, v in search.best_params_.items()}
    info = {"izgara": {k.replace("rf__", ""): v for k, v in PARAM_GRID.items()},
            "deneme_sayisi": n_iter, "kat_sayisi": 3, "skor": "f1_macro",
            "orneklem_satir": int(len(ys)), "kat_smote_hedefi": target,
            "class_weight": setting["class_weight"], "en_iyi_parametreler": best,
            "en_iyi_cv_macro_f1": float(search.best_score_), "arama_suresi_s": search_s}
    (out / "deney4_en_iyi.json").write_text(json.dumps(info, ensure_ascii=False, indent=2,
                                                       default=str), encoding="utf-8")
    log(f"Deney 4 en iyi: {best} · CV Macro F1={search.best_score_:.4f} · {search_s/60:.1f} dk")
    return info


def lgbm(class_weight=None):
    from lightgbm import LGBMClassifier
    return LGBMClassifier(**LGBM_PARAMS, class_weight=class_weight)


def experiment5(P, setting, best_params, y_val, class_names, log):
    """Ayarlanmış RF ile LightGBM aynı alt-eğitim ve aynı doğrulama kümesinde."""
    models = {"Random Forest (ayarlanmış)": rf(setting["class_weight"], **best_params),
              "LightGBM": lgbm(setting["class_weight"])}
    rows = []
    for name, model in models.items():
        log(f"Deney 5 · {name}")
        row, _, _ = fit_eval(model, P["X_fit"], P["y_fit"], P["X_eval"], y_val,
                             setting["smote"], class_names, log)
        rows.append({"model": name, **row})
    return rows, models


def final_test(V, setting, conflict_mode, features, model, class_names, log, out):
    """Seçilen yapılandırma TÜM eğitim kümesiyle yeniden kurulur ve test kümesinde BİR kez
    değerlendirilir. Doğrulamada sınanan öznitelik kümesi aynen kullanılır (alt-eğitim, eğitimin
    parçası olduğu için sızıntı yoktur); ölçekleyici ve SMOTE tüm eğitim kümesinde yeniden yapılır."""
    P = prepare(V["X_train"], V["y_train"], V["n_train"], V["X_test"], conflict_mode, log,
                features=features)
    row, cm, _ = fit_eval(clone(model), P["X_fit"], P["y_fit"], P["X_eval"], V["y_test"],
                          setting["smote"], class_names, log)
    plot_confusion(cm, class_names, "8. hafta final modeli — Hata Matrisi (test kümesi)",
                   out / "hata_matrisi_final.png")
    np.savetxt(out / "hata_matrisi_final.csv", cm, fmt="%d", delimiter=",",
               header=",".join(class_names), comments="")
    return row, P["features"]


# =============================================================== rapor
def save_csv(rows, path):
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")


def _metric_cells(r, class_names):
    return (f"{tr_pct(r['accuracy'])} | {tr_pct(r['macro_f1'])} | "
            f"{tr_pct(r.get('f1_Botnet', 0))} | {tr_pct(r.get('botnet_precision', 0))} | "
            f"{tr_pct(r.get('botnet_recall', 0))} | {tr_pct(r.get('f1_PortScan', 0))} | "
            f"{tr_int(r.get('benign_to_botnet', 0))} | {tr_num(r['egitim_suresi_s'], 1)}")


METRIC_HEAD = ("Accuracy | Macro F1 | Botnet F1 | Botnet Precision | Botnet Recall | "
               "PortScan F1 | Benign→Botnet | Eğitim (sn)")


def _per_class_table(rows, label_key, class_names):
    L = [f"| {label_key} | " + " | ".join(f"F1 {c}" for c in class_names) + " |",
         "| --- |" + " --- |" * len(class_names)]
    for r in rows:
        L.append(f"| {r[label_key]} | " + " | ".join(tr_pct(r[f'f1_{c}']) for c in class_names)
                 + " |")
    return L


def write_report(R, path):
    cn = R["sinif_adlari"]
    L = ["# 8. Hafta Raporu İçin Otomatik Üretilen Tablolar\n",
         f"Çalıştırma zamanı: {R['zaman']} · Örneklem oranı: {R['ornekleme_orani'] or 'tam veri'}"
         f" · Toplam süre: {tr_num(R['toplam_sure_dk'], 1)} dk\n"]
    if R["ornekleme_orani"]:
        L.append("> **Uyarı:** Bu bir örneklem çalıştırmasıdır; sayılar rapora yazılmamalıdır.\n")
    L.append("## Deney Düzeni\n")
    s = R["kume_boyutlari"]
    L.append("| Küme | Satır |\n| --- | --- |")
    L.append(f"| Eğitim (%80) | {tr_int(s['egitim'])} |")
    L.append(f"| → Alt-eğitim (eğitimin %80'i) | {tr_int(s['alt_egitim'])} |")
    L.append(f"| → Doğrulama (eğitimin %20'si) | {tr_int(s['dogrulama'])} |")
    L.append(f"| Test (%20, 7. haftayla aynı) | {tr_int(s['test'])} |\n")
    L.append("Tüm karşılaştırmalar doğrulama kümesinde yapıldı; seçim ölçütü doğrulama Macro F1. "
             "Test kümesi yalnızca en sonda seçilen tek yapılandırma için bir kez kullanıldı. "
             "Yüklemede birebir kopya olan `Fwd Header Length.1` sütunu silindi.\n")
    L.append(f"Öznitelik kümesi Deney 1'de alt-eğitimde bir kez seçildi ve sonraki tüm deneylerde "
             f"ve finalde sabit tutuldu ({len(R['sabit_oznitelikler'])} öznitelik). Neden: ilk "
             f"denemede Deney 2'de seçim her modda yeniden yapılınca, 254 satırlık değişiklik bile "
             f"seçilen kümeyi değiştirdi (`Fwd IAT Min` düştü) ve Web Attack F1 sert düştü; etki "
             f"çakışma işleminden değil seçimin kararsızlığından geliyordu.\n")
    L.append("Sabit öznitelikler: " + ", ".join(R["sabit_oznitelikler"]) + "\n")

    e1 = R["deney1"]
    L.append("## Deney 1 — SMOTE Düzeyi (Random Forest, port yok, doğrulama kümesi)\n")
    L.append(f"| Ayar | {METRIC_HEAD} |\n| --- |" + " --- |" * 8)
    for r in e1:
        L.append(f"| {r['ayar']} | {_metric_cells(r, cn)} |")
    smote_rows = [r for r in e1 if r["smote_hedefi"]]
    trend = " → ".join(f"{tr_int(r['smote_hedefi'])}: {tr_pct(r['botnet_precision'])}"
                       for r in smote_rows)
    L.append(f"\nBotnet precision'ın SMOTE hedefine göre değişimi: {trend}. "
             f"SMOTE yok: {tr_pct(e1[-1]['botnet_precision'])}; SMOTE yok + balanced: "
             f"{tr_pct(e1[-2]['botnet_precision'])}.\n")
    L.append(f"Seçilen ayar (en yüksek doğrulama Macro F1): **{R['secim']['dengesizlik']}**\n")
    L += _per_class_table(e1, "ayar", cn) + [""]

    L.append("## Deney 2 — Etiketi Çakışan Satırlar (yalnızca alt-eğitimde)\n")
    L.append("Çakışma: `Destination Port` hariç tüm öznitelikleri birebir aynı, sınıfı farklı "
             "satır grubu. Çoğunluk oyu ham veri kopya sayısıyla verilir; oyları eşit olan "
             "grup silinir. Doğrulama kümesine dokunulmadı.\n")
    L.append("| Yöntem | Çakışan grup | Çakışan satır | Silinen satır | Eşit oylu grup | "
             f"{METRIC_HEAD} |\n| --- |" + " --- |" * 12)
    for r in R["deney2"]:
        L.append(f"| {r['yontem']} | {tr_int(r['cakisan_grup'])} | {tr_int(r['cakisan_satir'])} | "
                 f"{tr_int(r['silinen_satir'])} | {tr_int(r['esit_oylu_grup'])} | "
                 f"{_metric_cells(r, cn)} |")
    L.append(f"\nSeçilen yöntem: **{CONFLICT_MODES[R['secim']['cakisma']]}**\n")

    L.append("## Deney 3 — Port Bilgisi\n")
    L.append("> **Not:** Port tekrar silmeden önce eklendiği için her varyantta farklı satırlar "
             "silinir ve bölme değişir. Doğrulama kümeleri birebir aynı **değildir**; "
             "karşılaştırma yaklaşık yorumlanmalıdır. Tüm varyantlarda Deney 1'deki sabit "
             "öznitelik kümesi kullanıldı; port sütunu bu kümeye zorla eklendi. (Küme port yok "
             "varyantının alt-eğitiminde seçildiği için B/C doğrulama kümeleriyle küçük bir "
             "örtüşme olabilir.)\n")
    L.append("| Varyant | Tekrar silinen | Alt-eğitim | Doğrulama | Doğrulamada Botnet | "
             f"{METRIC_HEAD} |\n| --- |" + " --- |" * 12)
    for r in R["deney3"]:
        L.append(f"| {r['varyant']} | {tr_int(r['tekrar_silinen'])} | "
                 f"{tr_int(r['alt_egitim_satir'])} | {tr_int(r['dogrulama_satir'])} | "
                 f"{tr_int(r['dogrulama_botnet'])} | {_metric_cells(r, cn)} |")
    L.append("\nPort, CLAUDE.md'deki tasarım kararı gereği final seçimine dahil edilmedi "
             "(port ezberi riski); bu deney yalnızca bilgi amaçlıdır.\n")

    e4 = R["deney4"]
    L.append("## Deney 4 — Hiperparametre Araması (RandomizedSearchCV)\n")
    L.append(f"imblearn Pipeline(StandardScaler → SMOTE → RandomForest), alt-eğitimden katmanlı "
             f"{tr_int(e4['orneklem_satir'])} satırlık örneklem, 3 katlı StratifiedKFold, "
             f"scoring=f1_macro, {e4['deneme_sayisi']} deneme. Katta SMOTE hedefi: "
             f"{tr_int(e4['kat_smote_hedefi']) if e4['kat_smote_hedefi'] else 'SMOTE yok'}. "
             f"Arama süresi: {tr_num(e4['arama_suresi_s'] / 60, 1)} dk.\n")
    L.append("| Parametre | Denenen değerler | En iyi |\n| --- | --- | --- |")
    for k, vals in e4["izgara"].items():
        L.append(f"| {k} | {', '.join(str(v) for v in vals)} | {e4['en_iyi_parametreler'][k]} |")
    L.append(f"\nEn iyi CV Macro F1: {tr_pct(e4['en_iyi_cv_macro_f1'])}. Tüm denemeler: "
             "`deney4_arama_sonuclari.csv`. Not: öznitelik seçimi aramadan önce tüm alt-eğitimde "
             "yapıldığı için CV skoru hafif iyimser olabilir; asıl karşılaştırma doğrulama "
             "kümesindedir.\n")

    L.append("## Deney 5 — Model Karşılaştırması (doğrulama kümesi)\n")
    L.append(f"| Model | {METRIC_HEAD} |\n| --- |" + " --- |" * 8)
    for r in R["deney5"]:
        L.append(f"| {r['model']} | {_metric_cells(r, cn)} |")
    L.append(f"\nLightGBM parametreleri: {LGBM_PARAMS}\n")
    L += _per_class_table(R["deney5"], "model", cn) + [""]

    f = R["final"]
    L.append("## Final — Test Kümesi (tek değerlendirme)\n")
    L.append(f"Seçilen yapılandırma: **{f['model']}**, dengesizlik: {R['secim']['dengesizlik']}, "
             f"çakışma: {CONFLICT_MODES[R['secim']['cakisma']]}, port yok. "
             f"Tüm eğitim kümesinde yeniden eğitildi ({len(f['oznitelikler'])} öznitelik).\n")
    L.append("| Metrik | 7. Hafta | 8. Hafta (final) | Fark (puan) |\n| --- | --- | --- | --- |")
    for key, name in [("accuracy", "Accuracy"), ("macro_f1", "Macro F1"),
                      ("f1_Botnet", "Botnet F1"), ("f1_PortScan", "PortScan F1")]:
        L.append(f"| {name} | {tr_pct(WEEK7[key])} | {tr_pct(f['satir'][key])} | "
                 f"{tr_num((f['satir'][key] - WEEK7[key]) * 100, 2)} |")
    L.append(f"| Benign→Botnet hatası | {tr_int(WEEK7['benign_to_botnet'])} | "
             f"{tr_int(f['satir']['benign_to_botnet'])} | "
             f"{f['satir']['benign_to_botnet'] - WEEK7['benign_to_botnet']:+d} |")
    if R["ornekleme_orani"]:
        L.append("\n> Örneklem çalıştırmasında test kümesi farklı olduğu için bu karşılaştırma "
                 "geçersizdir.")
    L.append("\n7. hafta: DT/RF, SMOTE 100.000, çakışma işlemi yok; `Fwd Header Length.1` "
             "o zaman veri içindeydi.\n")
    L.append("| Sınıf | F1 (test) |\n| --- | --- |")
    for c in cn:
        L.append(f"| {c} | {tr_pct(f['satir'][f'f1_{c}'])} |")
    L.append("\nHata matrisi: `hata_matrisi_final.png`.")
    path.write_text("\n".join(L), encoding="utf-8")


# =============================================================== ana akış
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(config.DATA_DIR))
    ap.add_argument("--sample-frac", type=float, default=None)
    ap.add_argument("--out", default=None, help="Çıktı klasörü (varsayılan reports/hafta8)")
    ap.add_argument("--n-iter", type=int, default=20, help="Deney 4 deneme sayısı")
    ap.add_argument("--cv-sample", type=int, default=300_000, help="Deney 4 örneklem boyutu")
    args = ap.parse_args(argv)

    out = Path(args.out) if args.out else config.REPORTS_DIR / "hafta8"
    if args.sample_frac and not args.out:   # deneme çıktıları gerçek sonuçlarla karışmasın
        out = out / f"deneme_frac{args.sample_frac}"
    out.mkdir(parents=True, exist_ok=True)
    log = setup_logger(out / "run_log.txt")
    t_start = time.perf_counter()

    # Port ile birlikte bir kez yüklenir; port yok varyantı sütunu silerek elde edilir
    raw = load_raw(args.data, args.sample_frac, log, keep_port=True)
    classes = set(raw["Label"].map(config.map_label).dropna())
    class_names = [c for c in config.CLASS_ORDER if c in classes]
    V = build_variant(raw, "yok", class_names, log)
    R = {"zaman": datetime.now().strftime("%Y-%m-%d %H:%M"), "ornekleme_orani": args.sample_frac,
         "sinif_adlari": class_names,
         "kume_boyutlari": {"egitim": len(V["y_train"]), "alt_egitim": len(V["y_sub"]),
                            "dogrulama": len(V["y_val"]), "test": len(V["y_test"])}}

    log("=" * 20 + " DENEY 1: SMOTE düzeyi " + "=" * 20)
    R["deney1"], features = experiment1(V, class_names, log)
    R["sabit_oznitelikler"] = features
    save_csv(R["deney1"], out / "deney1_smote.csv")
    setting = next(s for s in IMBALANCE_SETTINGS if s["ad"] == best_of(R["deney1"])["ayar"])
    log(f"DENEY 1 TAMAM · seçilen: {setting['ad']}")

    log("=" * 20 + " DENEY 2: etiket çakışmaları " + "=" * 20)
    R["deney2"] = experiment2(V, setting, features, class_names, log)
    save_csv(R["deney2"], out / "deney2_cakisma.csv")
    conflict_mode = best_of(R["deney2"])["mod"]
    log(f"DENEY 2 TAMAM · seçilen: {conflict_mode}")

    log("=" * 20 + " DENEY 3: port bilgisi " + "=" * 20)
    R["deney3"] = experiment3(raw, V, setting, conflict_mode, features, class_names, log)
    save_csv(R["deney3"], out / "deney3_port.csv")
    del raw
    log("DENEY 3 TAMAM")

    log("=" * 20 + " DENEY 4: hiperparametre araması " + "=" * 20)
    P = prepare(V["X_sub"], V["y_sub"], V["n_sub"], V["X_val"], conflict_mode, log,
                features=features)
    R["deney4"] = experiment4(P, setting, len(P["y_fit"]), args.cv_sample, args.n_iter, log, out)
    log("DENEY 4 TAMAM")

    log("=" * 20 + " DENEY 5: model karşılaştırması " + "=" * 20)
    R["deney5"], models = experiment5(P, setting, R["deney4"]["en_iyi_parametreler"],
                                      V["y_val"], class_names, log)
    save_csv(R["deney5"], out / "deney5_model.csv")
    log("DENEY 5 TAMAM")

    # Final adayları: Deney 2'nin en iyisi (varsayılan RF) + Deney 5 modelleri
    best2 = best_of(R["deney2"])
    candidates = [("Random Forest (7. hafta parametreleri)", best2["macro_f1"],
                   rf(setting["class_weight"]))]
    candidates += [(r["model"], r["macro_f1"], models[r["model"]]) for r in R["deney5"]]
    name, val_f1, model = max(candidates, key=lambda c: c[1])
    R["secim"] = {"dengesizlik": setting["ad"], "cakisma": conflict_mode, "model": name,
                  "dogrulama_macro_f1": val_f1,
                  "adaylar": {c[0]: c[1] for c in candidates}}
    log("=" * 20 + f" FİNAL: {name} (doğrulama Macro F1={val_f1:.4f}) " + "=" * 20)
    row, feats = final_test(V, setting, conflict_mode, features, model, class_names, log, out)
    R["final"] = {"model": name, "satir": row, "oznitelikler": feats,
                  "parametreler": {k: v for k, v in model.get_params().items()
                                   if k in set(config.RF_PARAMS) | set(LGBM_PARAMS)
                                   | {"class_weight", "min_samples_leaf", "max_features",
                                      "num_leaves", "learning_rate"}}}
    save_csv([{"model": name, **row}], out / "final_test.csv")
    save_csv([{"metrik": k, "hafta7": WEEK7[k], "hafta8": row[k]} for k in WEEK7],
             out / "final_karsilastirma.csv")
    (out / "secilen_yapilandirma.json").write_text(json.dumps(
        {**R["secim"], "smote_hedefi": setting["smote"], "class_weight": setting["class_weight"],
         "parametreler": R["final"]["parametreler"], "oznitelikler": feats},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    R["toplam_sure_dk"] = (time.perf_counter() - t_start) / 60
    (out / "sonuclar.json").write_text(json.dumps(R, ensure_ascii=False, indent=2, default=str),
                                       encoding="utf-8")
    write_report(R, out / "rapor_tablolari_hafta8.md")
    log(f"FİNAL TAMAM · Toplam süre: {R['toplam_sure_dk']:.1f} dk · Çıktılar: {out}")
    return R


if __name__ == "__main__":   # Windows'ta paralel işlemler için gerekli
    main()
