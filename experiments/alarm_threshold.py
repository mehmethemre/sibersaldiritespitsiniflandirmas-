"""Alarm eşiği (config.ALARM_MIN_FLOWS) seçimi — yalnızca DOĞRULAMA kümesiyle.

Soru: Bir saldırı sınıfı için KRİTİK alarm "en az N akış" görülünce verilsin. N kaç olmalı?

Neden doğrulama kümesi ve neden ayrı model?
* Test kümesi yalnızca final değerlendirme içindir; ayar seçiminde kullanılmaz.
* Uygulamadaki model TÜM eğitim kümesiyle eğitildi, yani doğrulama satırlarını da gördü; onunla
  ölçülen yanlış alarm sayısı olduğundan düşük çıkardı. Bu yüzden burada 9. hafta ayarlarıyla
  (çakışma silme, korelasyon sonrası öznitelikler, SMOTE 10.000, Botnet eşiği 0,30) yalnızca
  ALT-EĞİTİM kümesinde bir model eğitilir ve hiç görmediği doğrulama kümesinde tahmin yapılır.

Yöntem: doğrulama kümesinden rastgele "dosyalar" (parçalar) çekilir.
  a) Yalnızca Benign parçalar: her N için, kaç parçada yanlış KRİTİK alarm çıkıyor?
  b) Doğal dağılımlı parçalar (doğrulamadaki sınıf oranlarıyla): her N için
     - yanlış KRİTİK: sınıf parçada hiç yokken N veya daha fazla akışa o sınıf denmiş
     - düşürülen gerçek saldırı: sınıf parçada gerçekten var ama N'den az akış tespit edilmiş
       (alarm gizlenmez, sarı "incelenmeli" bilgisine düşer)
Satırlar rastgele örneklenir; gerçek trafik dosyaları zamana göre ardışıktır, bu bir yaklaşımdır.

Seçim kuralı (sonuçlara bakmadan önce belirlendi): yalnızca Benign içeren 10.000 satırlık
parçaların en fazla %5'inde yanlış KRİTİK alarm üreten EN KÜÇÜK N.
10.000 satır, N2 gereksinimindeki başvuru dosya boyutudur.

Kullanım:
    python experiments/alarm_threshold.py --sample-frac 0.05   # hızlı deneme
    python experiments/alarm_threshold.py                      # tam veri
Çıktılar: reports/hafta9/alarm_esigi_*.csv ve alarm_esigi.md
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

from experiments.run_experiments import build_variant, prepare  # noqa: E402
from run_pipeline import setup_logger, tr_int, tr_num, tr_pct  # noqa: E402
from src import config  # noqa: E402
from src.data_loader import load_raw  # noqa: E402
from src.evaluate import predict_classes  # noqa: E402
from src.preprocess import oversample, resolve_label_conflicts, select_features  # noqa: E402

N_VALUES = list(range(1, 51))
CHUNK_SIZES = [1_000, 3_000, 10_000, 100_000]
N_CHUNKS = 2_000
TARGET_SIZE = 10_000          # seçim kuralındaki dosya boyutu
MAX_FALSE_RATE = 0.05         # seçim kuralındaki en yüksek yanlış KRİTİK parça oranı


def critical_classes(class_names):
    return [i for i, c in enumerate(class_names) if config.ALARM_LEVELS.get(c) == "CRITICAL"]


def chunk_counts(y_true, y_pred, n_classes, chunk_size, n_chunks, rng, pool=None):
    """Rastgele parçalar çeker; her parça için gerçek ve tahmin sınıf sayılarını döndürür.

    Dönüş: (true_counts, pred_counts) — ikisi de (n_chunks, n_classes) tamsayı matrisi.
    """
    pool = np.arange(len(y_true)) if pool is None else np.asarray(pool)
    size = min(chunk_size, len(pool))
    t = np.zeros((n_chunks, n_classes), dtype=np.int64)
    p = np.zeros((n_chunks, n_classes), dtype=np.int64)
    for k in range(n_chunks):
        idx = rng.choice(pool, size, replace=False)
        t[k] = np.bincount(y_true[idx], minlength=n_classes)
        p[k] = np.bincount(y_pred[idx], minlength=n_classes)
    return t, p


def alarm_stats(true_counts, pred_counts, crit_cols, n_values=N_VALUES):
    """Her N için yanlış KRİTİK ve düşürülen gerçek saldırı oranları.

    yanlis_kritik_parca: en az bir KRİTİK sınıf parçada hiç yokken >= N akışa o sınıf denmiş
    dusurulen_gercek: (parça, sınıf) çiftlerinde sınıf gerçekten varken < N tespit oranı
    """
    t, p = true_counts[:, crit_cols], pred_counts[:, crit_cols]
    absent, present = t == 0, t > 0
    rows = []
    for n in n_values:
        false_crit = (absent & (p >= n)).any(axis=1)
        downgraded = present & (p < n)
        rows.append({"N": n, "yanlis_kritik_parca": float(false_crit.mean()),
                     "dusurulen_gercek": (float(downgraded.sum() / present.sum())
                                          if present.any() else np.nan),
                     "gercek_saldiri_cifti": int(present.sum())})
    return pd.DataFrame(rows)


def choose_n(benign_table, size=TARGET_SIZE, max_rate=MAX_FALSE_RATE):
    """Seçim kuralı: `size` satırlık Benign parçalarda oranı <= max_rate olan en küçük N."""
    t = benign_table[benign_table["parca_boyutu"] == size]
    ok = t[t["yanlis_kritik_parca"] <= max_rate]
    return int(ok["N"].min()) if len(ok) else int(t["N"].max())


def validation_predictions(args, log):
    """Alt-eğitimde 9. hafta ayarlarıyla eğitir, doğrulama kümesinde tahmin yapar."""
    raw = load_raw(args.data, args.sample_frac, log, keep_port=True)
    classes = set(raw["Label"].map(config.map_label).dropna())
    cn = [c for c in config.CLASS_ORDER if c in classes]
    V = build_variant(raw, "yok", cn, log)
    del raw
    X_fit, y_fit, _ = resolve_label_conflicts(V["X_sub"], V["y_sub"], V["n_sub"],
                                              config.CONFLICT_MODE)
    feats, _ = select_features(X_fit, y_fit, log, use_extratrees=config.USE_EXTRATREES)
    P = prepare(V["X_sub"], V["y_sub"], V["n_sub"], V["X_val"], config.CONFLICT_MODE, log,
                features=feats)
    from sklearn.ensemble import RandomForestClassifier
    X, y, _ = oversample(P["X_fit"], P["y_fit"], log, target=config.SMOTE_TARGET)
    model = RandomForestClassifier(**config.RF_PARAMS).fit(X, y)
    pred, _ = predict_classes(model, P["X_eval"], cn, config.BOTNET_THRESHOLD)
    return cn, V["y_val"], np.asarray(pred), len(V["y_sub"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(config.DATA_DIR))
    ap.add_argument("--sample-frac", type=float, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--n-chunks", type=int, default=N_CHUNKS)
    args = ap.parse_args(argv)
    out = Path(args.out) if args.out else config.REPORTS_DIR / "hafta9"
    if args.sample_frac and not args.out:
        out = out / f"deneme_frac{args.sample_frac}"
    out.mkdir(parents=True, exist_ok=True)
    log = setup_logger(out / "alarm_esigi_log.txt")
    t0 = time.perf_counter()

    cn, y_val, y_pred, n_sub = validation_predictions(args, log)
    b = cn.index("Benign")
    crit = critical_classes(cn)
    benign_rows = np.flatnonzero(y_val == b)
    fp_rate = float((y_pred[benign_rows] != b).mean())
    fp_by_class = {cn[c]: int(((y_pred == c) & (y_val == b)).sum()) for c in range(len(cn)) if c != b}
    log(f"Doğrulama: {len(y_val):,} satır, Benign {len(benign_rows):,}; Benign akışların "
        f"%{fp_rate * 100:.3f}'ü saldırı sanıldı: {fp_by_class}")

    rng = np.random.default_rng(config.RANDOM_STATE)
    benign_tables, natural_tables, fp_dist = [], [], []
    for size in CHUNK_SIZES:
        if size > len(benign_rows):
            continue
        t, p = chunk_counts(y_val, y_pred, len(cn), size, args.n_chunks, rng, pool=benign_rows)
        benign_tables.append(alarm_stats(t, p, crit).assign(parca_boyutu=size))
        worst = p[:, crit].max(axis=1)               # parçadaki en kalabalık yanlış KRİTİK sınıf
        fp_dist.append({"parca_boyutu": size, "ortalama_yanlis_saldiri_akisi":
                        float(p[:, [c for c in range(len(cn)) if c != b]].sum(axis=1).mean()),
                        "en_kalabalik_sinif_medyan": float(np.median(worst)),
                        "en_kalabalik_sinif_p95": float(np.percentile(worst, 95)),
                        "en_kalabalik_sinif_max": int(worst.max())})
        t, p = chunk_counts(y_val, y_pred, len(cn), size, args.n_chunks, rng)
        natural_tables.append(alarm_stats(t, p, crit).assign(parca_boyutu=size))
    benign = pd.concat(benign_tables, ignore_index=True)
    natural = pd.concat(natural_tables, ignore_index=True)
    dist = pd.DataFrame(fp_dist)
    n_star = choose_n(benign)
    benign.to_csv(out / "alarm_esigi_benign_parcalar.csv", index=False, encoding="utf-8")
    natural.to_csv(out / "alarm_esigi_dogal_parcalar.csv", index=False, encoding="utf-8")
    dist.to_csv(out / "alarm_esigi_yanlis_akis_dagilimi.csv", index=False, encoding="utf-8")
    summary = {"secilen_N": n_star, "kural": f"{tr_int(TARGET_SIZE)} satırlık Benign parçalarda yanlış "
               f"KRİTİK oranı <= %{MAX_FALSE_RATE * 100:.0f} olan en küçük N",
               "dogrulama_satir": int(len(y_val)), "alt_egitim_satir": int(n_sub),
               "benign_dogrulama": int(len(benign_rows)), "benign_yanlis_oran": fp_rate,
               "benign_yanlis_sinif": fp_by_class, "parca_sayisi": args.n_chunks,
               "ornekleme_orani": args.sample_frac,
               "sure_dk": (time.perf_counter() - t0) / 60}
    (out / "alarm_esigi_ozet.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    write_report(out / "alarm_esigi.md", summary, benign, natural, dist)
    log(f"Seçilen N = {n_star} · {summary['sure_dk']:.1f} dk · Çıktılar: {out}")
    return summary, benign, natural


def write_report(path, s, benign, natural, dist):
    sizes = sorted(benign["parca_boyutu"].unique())
    show = sorted(set([1, 2, 3, 5, 8, 10, 15, 20, 30, 50, s["secilen_N"]]))
    L = ["# Alarm Eşiği Seçimi (doğrulama kümesi)\n"]
    if s["ornekleme_orani"]:
        L.append("> **Uyarı:** örneklem çalıştırması; sayılar rapora yazılmaz.\n")
    L.append(f"Alt-eğitimde ({tr_int(s['alt_egitim_satir'])} satır) 9. hafta ayarlarıyla eğitilen "
             f"model, görmediği doğrulama kümesinde ({tr_int(s['dogrulama_satir'])} satır) tahmin "
             f"yaptı. Doğrulamadaki {tr_int(s['benign_dogrulama'])} Benign akışın "
             f"{tr_pct(s['benign_yanlis_oran'], 3)}'ü saldırı sanıldı: "
             + ", ".join(f"{k} {tr_int(v)}" for k, v in s["benign_yanlis_sinif"].items()) + ".\n")
    L.append(f"Her boyut için {tr_int(s['parca_sayisi'])} rastgele parça çekildi. Seçim kuralı: "
             f"{s['kural']}. **Seçilen N = {s['secilen_N']}.**\n")
    L.append("## Yalnızca Benign parçalarda yanlış KRİTİK alarm çıkan parça oranı\n")
    L.append("| N | " + " | ".join(f"{tr_int(z)} satır" for z in sizes) + " |")
    L.append("| --- |" + " --- |" * len(sizes))
    for n in show:
        row = benign[benign["N"] == n].set_index("parca_boyutu")["yanlis_kritik_parca"]
        L.append(f"| {n} | " + " | ".join(tr_pct(row[z], 1) for z in sizes) + " |")
    L.append("\nBenign parçalarda yanlış saldırı akışı sayısı (en kalabalık KRİTİK sınıf):\n")
    L.append("| Parça | Ort. yanlış saldırı akışı | Medyan | %95'lik | En çok |\n| --- | --- | --- | --- | --- |")
    for r in dist.itertuples():
        L.append(f"| {tr_int(r.parca_boyutu)} | {tr_num(r.ortalama_yanlis_saldiri_akisi, 2)} | "
                 f"{tr_num(r.en_kalabalik_sinif_medyan, 1)} | {tr_num(r.en_kalabalik_sinif_p95, 1)} | "
                 f"{tr_int(r.en_kalabalik_sinif_max)} |")
    L.append("\n## Doğal dağılımlı parçalar (gerçek saldırılar dahil)\n")
    L.append("Yanlış KRİTİK: parçada olmayan bir sınıf için alarm. Düşürülen: parçada gerçekten "
             "bulunan bir saldırı sınıfının N'den az akışla tespit edilip sarı bilgiye düşmesi "
             "(gizlenmez).\n")
    L.append("| N | " + " | ".join(f"{tr_int(z)}: yanlış KRİTİK / düşürülen" for z in sizes) + " |")
    L.append("| --- |" + " --- |" * len(sizes))
    for n in show:
        row = natural[natural["N"] == n].set_index("parca_boyutu")
        L.append(f"| {n} | " + " | ".join(
            f"{tr_pct(row.loc[z, 'yanlis_kritik_parca'], 1)} / {tr_pct(row.loc[z, 'dusurulen_gercek'], 1)}"
            for z in sizes) + " |")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
