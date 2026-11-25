"""8. hafta ek deneyleri: öznitelik seçimi kontrolü, Botnet karar eşiği ve yeni final.

KURAL: Bütün seçimler DOĞRULAMA kümesinde yapılır; test kümesi yalnızca en sonda, kazanan tek
yapılandırma için bir kez kullanılır. Bölmeler run_experiments.py ile birebir aynıdır (aynı
temizlik, aynı random_state), bu yüzden alt-eğitim / doğrulama / test kümeleri değişmez.

Sabit ayarlar: port yok, 7. hafta RF parametreleri, çakışma modu "sil" (önceki 8. hafta
seçimi; Deney 2'de etkisi gürültü düzeyindeydi).

Ek 1 — Öznitelik seçimi kontrolü (SMOTE 10.000):
    a) sabit 26 öznitelik (korelasyon elemesi + ExtraTrees %90)
    b) seçim yok: yalnızca korelasyon elemesinden sonra kalan bütün öznitelikler
    Neden? Deney 2'de küçük bir veri değişikliği seçilen kümeyi değiştirdi. ExtraTrees adımı
    gerçekten yararlı mı, yoksa yalnızca kararsızlık mı getiriyor, bunu ölçmek istiyoruz.

Ek 2 — Botnet karar eşiği (Ek 1 kazananı ile; SMOTE 10.000 ve SMOTE yok):
    Kural: Botnet olasılığı >= t ise "Botnet", değilse kalan sınıflar arasında en olası sınıf.
    "Varsayılan" = eşik yok, düz predict() (en olası sınıf).
    Neden? Botnet'in sorunu Benign'ın Botnet sanılması (precision düşük) ya da SMOTE yokken
    Botnet'in kaçırılması (recall düşük). Eşik, precision/recall dengesini model yeniden
    eğitilmeden kaydırır. SMOTE düzeyi de aynı dengeyi kaydırdığı için ikisi birlikte denenir.
    4 aday (2 SMOTE x varsayılan/ayarlı eşik) arasından doğrulama Macro F1'i en yüksek seçilir.

Final: kazanan tüm eğitim kümesinde yeniden eğitilir, eşik doğrulamada bulunan değerde
SABİT tutulur (testte yeniden ayarlanmaz) ve test kümesinde bir kez değerlendirilir.

Kullanım:
    python experiments/run_followup.py --sample-frac 0.05   # hızlı deneme
    python experiments/run_followup.py                      # tam veri
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_experiments import (WEEK7, build_variant, metric_row, prepare,  # noqa: E402
                                         rf, save_csv)
from run_pipeline import setup_logger, tr_int, tr_num, tr_pct  # noqa: E402
from src import config  # noqa: E402
from src.data_loader import load_raw  # noqa: E402
from src.evaluate import plot_confusion  # noqa: E402
from src.preprocess import oversample, select_features  # noqa: E402

CONFLICT_MODE = "sil"
SMOTE_SETTINGS = {"SMOTE 10.000": 10_000, "SMOTE yok": None}
THRESHOLDS = np.round(np.arange(0.05, 0.951, 0.01), 2)
# 7. hafta Botnet precision/recall (reports/rapor_tablolari.md, test kümesi)
WEEK7_BOTNET = {"botnet_precision": 0.5359, "botnet_recall": 0.9373}
MARKER = "<!-- EK DENEYLER -->"


# =============================================================== eşik yardımcıları
def predict_with_threshold(proba, botnet_col, t):
    """Botnet olasılığı >= t ise Botnet; değilse Botnet dışındaki en olası sütun.

    t=None -> düz argmax (varsayılan karar). Dönen değerler SÜTUN indeksidir.
    """
    if t is None:
        return proba.argmax(axis=1)
    rest = proba.copy()
    rest[:, botnet_col] = -np.inf          # Botnet'i dışarıda bırakıp en olası sınıfı bul
    return np.where(proba[:, botnet_col] >= t, botnet_col, rest.argmax(axis=1))


def sweep_threshold(y_true, proba, classes, botnet_label, class_names, grid=THRESHOLDS):
    """Her eşik için doğrulama metriklerini hesaplar; Botnet F1'i en yüksek eşiği döndürür.

    En iyi F1'i birden çok eşik paylaşıyorsa (düz bölge) ortadaki seçilir: bölgenin kenarındaki
    bir eşik yeni veride kolayca bölgenin dışına düşebilir, ortası daha sağlamdır.
    """
    col = list(classes).index(botnet_label)
    rows = []
    for t in grid:
        pred = np.asarray(classes)[predict_with_threshold(proba, col, t)]
        r, _ = metric_row(y_true, pred, class_names)
        rows.append({"esik": float(t), **r})
    curve = pd.DataFrame(rows)
    best_f1 = curve["f1_Botnet"].max()
    ties = curve.loc[np.isclose(curve["f1_Botnet"], best_f1), "esik"].to_numpy()
    return float(ties[len(ties) // 2]), curve


# =============================================================== eğitim
def train(X, y, smote_target, log):
    model = rf(None)
    if smote_target:
        X, y, _ = oversample(X, y, log, target=smote_target)
    t0 = time.perf_counter()
    model.fit(X, y)
    return model, time.perf_counter() - t0


def evaluate(model, X_ev, y_ev, t, class_names):
    classes = model.classes_
    b = class_names.index("Botnet")
    proba = model.predict_proba(X_ev)
    pred = classes[predict_with_threshold(proba, list(classes).index(b), t)]
    row, cm = metric_row(y_ev, pred, class_names)
    return row, cm, proba


def _log_row(log, name, r):
    log(f"  [{name}] MacroF1={r['macro_f1']:.4f} BotnetF1={r['f1_Botnet']:.4f} "
        f"P={r['botnet_precision']:.4f} R={r['botnet_recall']:.4f} "
        f"Benign->Botnet={r['benign_to_botnet']}")


# =============================================================== rapor
def report_section(R):
    cn = R["sinif_adlari"]
    L = [MARKER, "", "# Ek Deneyler (öznitelik seçimi kontrolü, Botnet karar eşiği, yeni final)\n",
         f"Çalıştırma zamanı: {R['zaman']} · Örneklem oranı: {R['ornekleme_orani'] or 'tam veri'}"
         f" · Süre: {tr_num(R['toplam_sure_dk'], 1)} dk\n",
         "Ortak ayarlar: port yok, 7. hafta RF parametreleri, çakışma modu \"sil\", aynı "
         "alt-eğitim / doğrulama / test bölmesi. Tüm seçimler doğrulama kümesinde yapıldı.\n"]

    L.append("## Ek 1 — Öznitelik Seçimi Kontrolü (SMOTE 10.000, doğrulama kümesi)\n")
    L.append("| Öznitelik kümesi | Sayı | Accuracy | Macro F1 | "
             + " | ".join(f"F1 {c}" for c in cn) + " | Eğitim (sn) |")
    L.append("| --- |" + " --- |" * (len(cn) + 4))
    for r in R["ek1"]:
        L.append(f"| {r['kume']} | {r['oznitelik_sayisi']} | {tr_pct(r['accuracy'])} | "
                 f"{tr_pct(r['macro_f1'])} | " + " | ".join(tr_pct(r[f'f1_{c}']) for c in cn)
                 + f" | {tr_num(r['egitim_suresi_s'], 1)} |")
    extra = [f for f in R["tum_oznitelikler"] if f not in R["sabit_oznitelikler"]]
    L.append(f"\nKazanan (doğrulama Macro F1): **{R['ek1_kazanan']}**. (b) kümesinde olup "
             f"(a)'da olmayan {len(extra)} öznitelik: {', '.join(extra)}.\n")

    L.append("## Ek 2 — Botnet Karar Eşiği (doğrulama kümesi)\n")
    L.append("Kural: Botnet olasılığı ≥ eşik ise Botnet, değilse kalan sınıflardan en olası olan. "
             "\"Varsayılan\" = eşik yok (en olası sınıf). Eşik 0,05–0,95 aralığında 0,01 adımla "
             "tarandı; Botnet F1'i en yüksek eşik seçildi (eşit olanlardan ortadaki).\n")
    L.append("| Aday | Eşik | Macro F1 | Botnet F1 | Botnet Precision | Botnet Recall | "
             "Benign→Botnet | PortScan F1 |\n| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in R["ek2"]:
        L.append(f"| {r['aday']} | {tr_num(r['esik'], 2) if r['esik'] is not None else 'varsayılan'}"
                 f" | {tr_pct(r['macro_f1'])} | {tr_pct(r['f1_Botnet'])} | "
                 f"{tr_pct(r['botnet_precision'])} | {tr_pct(r['botnet_recall'])} | "
                 f"{tr_int(r['benign_to_botnet'])} | {tr_pct(r['f1_PortScan'])} |")
    L.append(f"\nSeçilen aday (doğrulama Macro F1): **{R['secim']['aday']}**.\n")
    L.append("> **Not:** Ayarlı eşik, seçimin yapıldığı doğrulama kümesinde bulundu; bu adayların "
             "doğrulama skoru bu yüzden hafif iyimserdir. Tarafsız ölçüm aşağıdaki test "
             "sonucudur. Eşik eğrileri: `ek2_esik_tarama.csv`.\n")

    f, p = R["final"], R["onceki_final"]
    L.append("## Yeni Final — Test Kümesi (tek değerlendirme)\n")
    L.append(f"Yapılandırma: {R['ek1_kazanan']}, {R['secim']['smote_ad']}, eşik: "
             f"{tr_num(R['secim']['esik'], 2) if R['secim']['esik'] is not None else 'varsayılan'}"
             f". Tüm eğitim kümesinde yeniden eğitildi; eşik doğrulamadaki değerinde sabit tutuldu.\n")
    L.append("| Metrik | 7. Hafta | 8. Hafta (önceki final) | 8. Hafta (yeni final) | "
             "Fark (yeni − önceki) |\n| --- | --- | --- | --- | --- |")
    w7 = {**WEEK7, **WEEK7_BOTNET}
    for key, name in [("accuracy", "Accuracy"), ("macro_f1", "Macro F1"),
                      ("f1_Botnet", "Botnet F1"), ("botnet_precision", "Botnet Precision"),
                      ("botnet_recall", "Botnet Recall"), ("f1_PortScan", "PortScan F1")]:
        L.append(f"| {name} | {tr_pct(w7[key])} | {tr_pct(p[key])} | {tr_pct(f[key])} | "
                 f"{tr_num((f[key] - p[key]) * 100, 2)} puan |")
    L.append(f"| Benign→Botnet hatası | {tr_int(w7['benign_to_botnet'])} | "
             f"{tr_int(p['benign_to_botnet'])} | {tr_int(f['benign_to_botnet'])} | "
             f"{int(f['benign_to_botnet']) - int(p['benign_to_botnet']):+d} |")
    if R["ornekleme_orani"]:
        L.append("\n> Örneklem çalıştırması: 7. hafta sütunu tam veri testidir, karşılaştırma "
                 "geçersizdir.")
    L.append("\n| Sınıf | F1 (test, yeni final) |\n| --- | --- |")
    for c in cn:
        L.append(f"| {c} | {tr_pct(f[f'f1_{c}'])} |")
    L.append("\nHata matrisi: `hata_matrisi_ek_final.png`.\n")
    return "\n".join(L)


def append_report(md_path, section):
    """Ek bölümü rapora ekler; daha önce eklenmişse eski ek bölümün yerine yazar."""
    text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    if MARKER in text:
        text = text[:text.index(MARKER)].rstrip()
    md_path.write_text(text + "\n\n" + section, encoding="utf-8")


# =============================================================== ana akış
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(config.DATA_DIR))
    ap.add_argument("--sample-frac", type=float, default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    out = Path(args.out) if args.out else config.REPORTS_DIR / "hafta8"
    if args.sample_frac and not args.out:
        out = out / f"deneme_frac{args.sample_frac}"
    out.mkdir(parents=True, exist_ok=True)
    log = setup_logger(out / "ek_run_log.txt")
    t_start = time.perf_counter()

    raw = load_raw(args.data, args.sample_frac, log, keep_port=True)
    classes = set(raw["Label"].map(config.map_label).dropna())
    cn = [c for c in config.CLASS_ORDER if c in classes]
    V = build_variant(raw, "yok", cn, log)
    del raw

    # Deney 1'deki seçim aynen tekrarlanır (alt-eğitim, çakışma işlemi yok, aynı random_state):
    # sabit 26 öznitelik + korelasyon elemesinden sonra kalan tüm öznitelikler
    fixed, info = select_features(V["X_sub"], V["y_sub"], log)
    all_after_corr = list(info["onem_skorlari"])     # korelasyon sonrası kalanların hepsi
    log(f"Sabit küme {len(fixed)} öznitelik, korelasyon sonrası küme {len(all_after_corr)}")

    # ---------------- Ek 1
    log("=" * 20 + " EK 1: öznitelik seçimi kontrolü " + "=" * 20)
    sets = {f"a) Sabit {len(fixed)} öznitelik (seçim var)": fixed,
            f"b) Seçim yok, korelasyon sonrası {len(all_after_corr)} öznitelik": all_after_corr}
    ek1, cache = [], {}
    for name, feats in sets.items():
        P = prepare(V["X_sub"], V["y_sub"], V["n_sub"], V["X_val"], CONFLICT_MODE, log,
                    features=feats)
        model, train_s = train(P["X_fit"], P["y_fit"], 10_000, log)
        row, _, proba = evaluate(model, P["X_eval"], V["y_val"], None, cn)
        _log_row(log, name, row)
        ek1.append({"kume": name, "oznitelik_sayisi": len(feats), **row,
                    "egitim_suresi_s": train_s})
        cache[name] = (P, model, proba)
    save_csv(ek1, out / "ek1_oznitelik.csv")
    win1 = max(ek1, key=lambda r: r["macro_f1"])["kume"]
    feats = sets[win1]
    log(f"EK 1 TAMAM · kazanan: {win1}")

    # ---------------- Ek 2
    log("=" * 20 + " EK 2: Botnet karar eşiği " + "=" * 20)
    P = cache[win1][0]
    b = cn.index("Botnet")
    ek2, curves = [], []
    for smote_name, target in SMOTE_SETTINGS.items():
        if target == 10_000:                       # Ek 1'de zaten eğitildi: yeniden kullan
            model, proba = cache[win1][1], cache[win1][2]
        else:
            model, _ = train(P["X_fit"], P["y_fit"], target, log)
            proba = model.predict_proba(P["X_eval"])
        t_best, curve = sweep_threshold(V["y_val"], proba, model.classes_, b, cn)
        curves.append(curve.assign(smote=smote_name))
        for t in (None, t_best):
            pred = model.classes_[predict_with_threshold(
                proba, list(model.classes_).index(b), t)]
            row, _ = metric_row(V["y_val"], pred, cn)
            name = f"{smote_name} + {'varsayılan karar' if t is None else f'eşik {t:.2f}'}"
            _log_row(log, name, row)
            ek2.append({"aday": name, "smote_ad": smote_name, "smote_hedefi": target or 0,
                        "esik": t, **row})
    save_csv(ek2, out / "ek2_adaylar.csv")
    pd.concat(curves).to_csv(out / "ek2_esik_tarama.csv", index=False, encoding="utf-8")
    best = max(ek2, key=lambda r: r["macro_f1"])
    log(f"EK 2 TAMAM · seçilen: {best['aday']}")

    # ---------------- Final (test kümesi bir kez)
    log("=" * 20 + f" FİNAL: {best['aday']} " + "=" * 20)
    PF = prepare(V["X_train"], V["y_train"], V["n_train"], V["X_test"], CONFLICT_MODE, log,
                 features=feats)
    model, train_s = train(PF["X_fit"], PF["y_fit"], SMOTE_SETTINGS[best["smote_ad"]], log)
    row, cm, _ = evaluate(model, PF["X_eval"], V["y_test"], best["esik"], cn)
    row["egitim_suresi_s"] = train_s
    _log_row(log, "TEST", row)
    plot_confusion(cm, cn, "8. hafta yeni final — Hata Matrisi (test kümesi)",
                   out / "hata_matrisi_ek_final.png")
    np.savetxt(out / "hata_matrisi_ek_final.csv", cm, fmt="%d", delimiter=",",
               header=",".join(cn), comments="")
    prev = pd.read_csv(out / "final_test.csv").iloc[0].to_dict()

    R = {"zaman": datetime.now().strftime("%Y-%m-%d %H:%M"), "ornekleme_orani": args.sample_frac,
         "sinif_adlari": cn, "sabit_oznitelikler": fixed, "tum_oznitelikler": all_after_corr,
         "ek1": ek1, "ek1_kazanan": win1, "ek2": ek2,
         "secim": {"aday": best["aday"], "smote_ad": best["smote_ad"], "esik": best["esik"],
                   "oznitelikler": feats, "cakisma": CONFLICT_MODE},
         "final": row, "onceki_final": prev,
         "toplam_sure_dk": (time.perf_counter() - t_start) / 60}
    save_csv([{"aday": best["aday"], **row}], out / "ek_final_test.csv")
    w7 = {**WEEK7, **WEEK7_BOTNET}
    save_csv([{"metrik": k, "hafta7": w7[k], "hafta8_onceki": prev[k], "hafta8_yeni": row[k]}
              for k in ["accuracy", "macro_f1", "f1_Botnet", "botnet_precision",
                        "botnet_recall", "f1_PortScan", "benign_to_botnet"]],
             out / "ek_final_karsilastirma.csv")
    (out / "ek_sonuclar.json").write_text(json.dumps(R, ensure_ascii=False, indent=2,
                                                     default=str), encoding="utf-8")
    append_report(out / "rapor_tablolari_hafta8.md", report_section(R))
    log(f"FİNAL TAMAM · {R['toplam_sure_dk']:.1f} dk · Çıktılar: {out}")
    return R


if __name__ == "__main__":
    main()
