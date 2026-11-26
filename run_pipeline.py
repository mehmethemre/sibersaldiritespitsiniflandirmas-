"""Uçtan uca çalıştırma: veri yükleme -> temizlik -> bölme -> (yalnızca eğitimde) çakışma
silme, öznitelik seçimi, ölçekleme, SMOTE -> Decision Tree + Random Forest eğitimi ->
test kümesinde değerlendirme -> rapor tabloları + uygulamanın kullandığı artefaktlar.

9. haftadan itibaren ayarlar 8. hafta doğrulama deneylerinde seçilenlerdir (src/config.py):
çakışan gruplar silinir, ExtraTrees yok (korelasyon sonrası tüm öznitelikler), SMOTE 10.000,
Random Forest için Botnet karar eşiği 0,30.

Kullanım:
    python run_pipeline.py                      # tüm veri
    python run_pipeline.py --sample-frac 0.05   # hızlı deneme (%5 örneklem)
    python run_pipeline.py --data D:\\veri\\csv  # farklı veri klasörü
"""
import argparse
import json
import logging
import os
import platform
import sys
import time
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
import psutil
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier

from src import config
from src.data_loader import load_raw
from src.evaluate import evaluate_model
from src.preprocess import (clean, fit_scaler, oversample, resolve_label_conflicts,
                            select_features, split)


def setup_logger(path):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logger = logging.getLogger("pipeline")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(message)s", "%H:%M:%S")
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(path, "w", encoding="utf-8")):
        h.setFormatter(fmt)
        logger.addHandler(h)
    return logger.info


def hardware_info():
    cpu = platform.processor()
    if platform.system() == "Windows":
        try:   # Windows kayıt defterinden işlemcinin tam adı
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except Exception:
            pass
    return {
        "isletim_sistemi": f"{platform.system()} {platform.release()}",
        "islemci": cpu,
        "mantiksal_cekirdek": os.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
        "python": platform.python_version(),
        "pandas": pd.__version__, "numpy": np.__version__, "scikit_learn": sklearn.__version__,
    }


# --------------------------------------------------------- Türkçe sayı biçimleri
def tr_int(n):
    return f"{int(n):,}".replace(",", ".")


def tr_pct(x, d=2):
    return "%" + f"{x*100:.{d}f}".replace(".", ",")


def tr_num(x, d=3):
    return f"{x:.{d}f}".replace(".", ",")


def write_report_tables(m, path):
    c = m["temizlik"]
    order = [k for k in config.CLASS_ORDER if k in m["sinif_adlari"]]
    dt, rf = m["modeller"]["Decision Tree"], m["modeller"]["Random Forest"]
    L = []
    L.append("# Ana Pipeline Sonuçları (9. hafta ayarları)\n")
    L.append(f"Model sürümü: {m['model_surumu']} · Çakışma modu: {m['cakisma']['mod']} · "
             f"SMOTE hedefi: {tr_int(m['smote_hedefi'])} · Random Forest Botnet eşiği: "
             f"{tr_num(m['botnet_esigi'], 2)} · ExtraTrees seçimi: "
             f"{'açık' if m['extratrees'] else 'kapalı'}\n")
    L.append(f"Çalıştırma zamanı: {m['zaman']} · Örneklem oranı: {m['ornekleme_orani'] or 'tam veri'}\n")
    L.append("## 4.1 Temizlik Sonuçları\n")
    L.append("| Adım | Kalan Satır | Silinen Satır |\n| --- | --- | --- |")
    L.append(f"| Ham veri (8 CSV birleşik) | {tr_int(c['ham_satir'])} | — |")
    L.append(f"| Kapsam dışı sınıfların çıkarılması | {tr_int(c['kapsam_disi_sonrasi'])} | {tr_int(c['kapsam_disi_silinen'])} |")
    L.append(f"| Inf/NaN temizliği | {tr_int(c['inf_nan_sonrasi'])} | {tr_int(c['inf_nan_silinen'])} |")
    L.append(f"| Tekrarlayan kayıtların silinmesi | {tr_int(c['tekrar_sonrasi'])} | {tr_int(c['tekrar_silinen'])} |")
    L.append(f"| Eğitim kümesi (%80) / Test kümesi (%20) | {tr_int(m['egitim_satir_bolme'])} / {tr_int(m['test_satir'])} | — |")
    L.append(f"| Etiketi çakışan grupların silinmesi (yalnızca eğitim) | {tr_int(m['egitim_satir'])} | {tr_int(m['cakisma']['silinen_satir'])} |\n")
    fs = m["oznitelik_secimi"]
    L.append(f"Sabit olduğu için çıkarılan sütun sayısı: {len(c['sabit_sutunlar'])}. "
             f"Korelasyon elemesinden sonra kalan: {fs['korelasyon_sonrasi_sayi']}. "
             f"Kullanılan öznitelik sayısı: **{fs['secilen_sayi']}**.\n")
    L.append("Kullanılan öznitelikler: " + ", ".join(m["secilen_oznitelikler"]) + "\n")

    L.append("## Sınıf Dağılımı\n")
    L.append("| Sınıf | Eğitim (SMOTE öncesi) | Eğitim (SMOTE sonrası) | Test |\n| --- | --- | --- | --- |")
    for cls in order:
        L.append(f"| {cls} | {tr_int(m['dagilim']['egitim_once'][cls])} | "
                 f"{tr_int(m['dagilim']['egitim_sonra'][cls])} | {tr_int(m['dagilim']['test'][cls])} |")
    L.append(f"\nSMOTE yöntemi: {m['smote_yontemi']}\n")

    L.append("## 4.2 Model Karşılaştırması\n")
    L.append("| Kriter | Decision Tree | Random Forest | Hedef |\n| --- | --- | --- | --- |")
    L.append(f"| Accuracy | {tr_pct(dt['accuracy'])} | {tr_pct(rf['accuracy'])} | ≥ %95 (N1) |")
    L.append(f"| Ağırlıklı F1 | {tr_pct(dt['weighted_f1'])} | {tr_pct(rf['weighted_f1'])} | — |")
    L.append(f"| Macro F1 | {tr_pct(dt['macro_f1'])} | {tr_pct(rf['macro_f1'])} | — |")
    L.append(f"| Eğitim süresi (sn) | {tr_num(dt['egitim_suresi_s'], 2)} | {tr_num(rf['egitim_suresi_s'], 2)} | — |")
    L.append(f"| Tek kayıt gecikmesi, medyan (ms) | {tr_num(dt['single_latency_median_ms'])} | {tr_num(rf['single_latency_median_ms'])} | < 50 ms (N2) |")
    L.append(f"| Toplu tahminde akış başına ortalama (ms) | {tr_num(dt['batch_per_flow_ms'], 4)} | {tr_num(rf['batch_per_flow_ms'], 4)} | — |")
    L.append(f"| Model dosya boyutu (MB) | {tr_num(dt['dosya_mb'], 2)} | {tr_num(rf['dosya_mb'], 2)} | — |\n")

    L.append("## 4.3 Random Forest Sınıf Bazında Başarım (Botnet eşiği uygulanmış)\n")
    L.append("| Sınıf | Precision | Recall | F1 | Test Örnek Sayısı |\n| --- | --- | --- | --- | --- |")
    for cls in order:
        p = rf["per_class"][cls]
        L.append(f"| {cls} | {tr_pct(p['precision'])} | {tr_pct(p['recall'])} | "
                 f"{tr_pct(p['f1-score'])} | {tr_int(p['support'])} |")
    crit = [k for k in order if k != "Benign"]
    low = [c for c in crit if rf["per_class"][c]["f1-score"] < 0.90]
    L.append("\nKritik saldırı sınıflarında F1 ≥ %90 (N1): "
             + ("karşılandı." if not low else "karşılanmadı → " + ", ".join(low)) + "\n")
    mc = rf["most_confused"]
    L.append("## 4.4 Hata Matrisi\n")
    L.append(f"Görsel: `reports/confusion_matrix_random_forest.png`. En çok karıştırılan çift: "
             f"gerçek **{mc['gercek']}** → tahmin **{mc['tahmin']}** ({tr_int(mc['sayi'])} örnek).\n")
    L.append("## Donanım\n")
    for k, v in m["donanim"].items():
        L.append(f"- {k}: {v}")
    path.write_text("\n".join(L), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(config.DATA_DIR))
    ap.add_argument("--sample-frac", type=float, default=None,
                    help="Hızlı deneme için her CSV'den alınacak oran (ör. 0.05)")
    args = ap.parse_args()

    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    log = setup_logger(config.REPORTS_DIR / "run_log.txt")
    t_start = time.perf_counter()
    hw = hardware_info()
    log(f"Donanım: {hw}")

    # 1) yükleme + temizlik
    raw = load_raw(args.data, args.sample_frac, log)
    df, clean_stats = clean(raw, log)
    del raw

    # 2) bölme (bundan sonra test kümesi yalnızca değerlendirmede kullanılır)
    X_tr_df, X_te_df, y_tr_s, y_te_s = split(df)
    del df
    log(f"Bölme: eğitim {len(X_tr_df):,} / test {len(X_te_df):,}")

    n_train_split = len(X_tr_df)

    # Etiket kodlama: sınıflar sabit sırada (Benign=0, DoS/DDoS=1, ...) tamsayıya çevrilir
    class_names = [c for c in config.CLASS_ORDER if c in set(y_tr_s)]
    code = {c: i for i, c in enumerate(class_names)}
    y_tr = y_tr_s.map(code).to_numpy(np.int64)
    y_te = y_te_s.map(code).to_numpy(np.int64)

    # 2b) etiketi çakışan gruplar (yalnızca eğitim; test kümesine dokunulmaz)
    X_tr_df, y_tr, conflict_info = resolve_label_conflicts(X_tr_df, y_tr, None,
                                                           config.CONFLICT_MODE)
    log(f"Çakışma modu '{config.CONFLICT_MODE}': {conflict_info['cakisan_grup']:,} grup, "
        f"{conflict_info['silinen_satir']:,} satır eğitimden silindi")

    # 3) öznitelik seçimi (yalnızca eğitim)
    features, fs_info = select_features(X_tr_df, y_tr, log,
                                        use_extratrees=config.USE_EXTRATREES)

    # 4) ölçekleme (yalnızca eğitime fit)
    scaler = fit_scaler(X_tr_df[features].to_numpy(np.float32))
    X_tr = scaler.transform(X_tr_df[features].to_numpy(np.float32)).astype(np.float32)
    X_te = scaler.transform(X_te_df[features].to_numpy(np.float32)).astype(np.float32)
    del X_tr_df, X_te_df

    # 5) SMOTE (yalnızca eğitim)
    dist_before = pd.Series(y_tr).value_counts()
    X_tr_res, y_tr_res, smote_method = oversample(X_tr, y_tr, log)
    dist_after = pd.Series(y_tr_res).value_counts()
    dist_test = pd.Series(y_te).value_counts()

    # artefaktlar
    joblib.dump(scaler, config.ARTIFACTS_DIR / "scaler.pkl")
    (config.ARTIFACTS_DIR / "features.json").write_text(
        json.dumps(features, ensure_ascii=False, indent=2), encoding="utf-8")
    (config.ARTIFACTS_DIR / "label_map.json").write_text(
        json.dumps({int(i): c for i, c in enumerate(class_names)}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    (config.REPORTS_DIR / "feature_selection.json").write_text(
        json.dumps(fs_info, ensure_ascii=False, indent=2), encoding="utf-8")

    # 6) eğitim + değerlendirme
    results = {}
    models = {
        "Decision Tree": (DecisionTreeClassifier(**config.DT_PARAMS), "dt_model.pkl"),
        "Random Forest": (RandomForestClassifier(**config.RF_PARAMS), "random_forest_model.pkl"),
    }
    # Botnet eşiği yalnızca uygulamada kullanılan Random Forest'a uygulanır;
    # Decision Tree temel model olarak düz predict() ile değerlendirilir.
    thresholds = {"Decision Tree": None, "Random Forest": config.BOTNET_THRESHOLD}
    for name, (model, fname) in models.items():
        log(f"--- {name} eğitiliyor ---")
        t0 = time.perf_counter()
        model.fit(X_tr_res, y_tr_res)
        train_s = time.perf_counter() - t0
        log(f"{name} eğitim süresi: {train_s:.2f} sn")
        path = config.ARTIFACTS_DIR / fname
        joblib.dump(model, path)
        res = evaluate_model(name, model, X_te, y_te, class_names, config.REPORTS_DIR, log,
                             botnet_threshold=thresholds[name])
        res["egitim_suresi_s"] = train_s
        res["dosya_mb"] = path.stat().st_size / 1024**2
        res["parametreler"] = {k: v for k, v in model.get_params().items()
                               if k in ("criterion", "max_depth", "min_samples_split", "n_estimators")}
        results[name] = res

    to_names = lambda s: {class_names[int(k)]: int(v) for k, v in s.items()}
    metrics = {
        "zaman": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ornekleme_orani": args.sample_frac,
        "donanim": hw,
        "temizlik": clean_stats,
        "model_surumu": config.MODEL_VERSION,
        "cakisma": {"mod": config.CONFLICT_MODE, **conflict_info},
        "smote_hedefi": config.SMOTE_TARGET, "botnet_esigi": config.BOTNET_THRESHOLD,
        "extratrees": config.USE_EXTRATREES,
        "egitim_satir_bolme": int(n_train_split),
        "egitim_satir": int(len(X_tr)), "test_satir": int(len(X_te)),
        "sinif_adlari": class_names,
        "dagilim": {"egitim_once": to_names(dist_before), "egitim_sonra": to_names(dist_after),
                    "test": to_names(dist_test)},
        "smote_yontemi": smote_method,
        "oznitelik_secimi": {k: v for k, v in fs_info.items() if k != "onem_skorlari"},
        "secilen_oznitelikler": features,
        "modeller": results,
        # Windows'ta peak_wset = sürecin ulaştığı en yüksek RAM; diğer sistemlerde anlık RSS
        "egitim_sureci_ram_mb": round(getattr(psutil.Process().memory_info(), "peak_wset",
                                              psutil.Process().memory_info().rss) / 1024**2, 1),
        "toplam_sure_dk": round((time.perf_counter() - t_start) / 60, 2),
    }
    # Uygulamanın (src/inference.py) modeli eğitimdekiyle aynı kuralla kullanması için gereken
    # her şey tek dosyada: sınıf sırası, Botnet eşiği, öznitelik sayısı, test sonucu
    rf_res = results["Random Forest"]
    model_config = {
        "model_surumu": config.MODEL_VERSION,
        "model_dosyasi": "random_forest_model.pkl",
        "olcekleyici_dosyasi": "scaler.pkl",
        "siniflar": class_names,
        "botnet_esigi": config.BOTNET_THRESHOLD,
        "oznitelik_sayisi": len(features),
        "smote_hedefi": config.SMOTE_TARGET, "cakisma_modu": config.CONFLICT_MODE,
        "extratrees": config.USE_EXTRATREES,
        "rf_parametreleri": dict(config.RF_PARAMS),
        "egitim_zamani": metrics["zaman"], "ornekleme_orani": args.sample_frac,
        "test_sonucu": {"accuracy": rf_res["accuracy"], "macro_f1": rf_res["macro_f1"],
                        "botnet_f1": rf_res["per_class"]["Botnet"]["f1-score"]
                        if "Botnet" in class_names else None},
    }
    (config.ARTIFACTS_DIR / "model_config.json").write_text(
        json.dumps(model_config, ensure_ascii=False, indent=2), encoding="utf-8")

    (config.REPORTS_DIR / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report_tables(metrics, config.REPORTS_DIR / "rapor_tablolari.md")
    log(f"Bitti. Toplam süre: {metrics['toplam_sure_dk']} dk. Çıktılar: {config.REPORTS_DIR}")


if __name__ == "__main__":   # Windows'ta paralel işlemler için gerekli
    main()
