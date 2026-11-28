"""FP şablonundaki Benign ve Botnet satırları öznitelik bakımından birebir aynı mı? (11. hafta)

Şablon (experiments/botnet_importance.py çıktısı, doğrulama FP'lerinin en sık değer birleşimi):
Init_Win_bytes_forward = 8192, Init_Win_bytes_backward = 0, Total Length of Fwd Packets = 0,
Total Length of Bwd Packets = 18, Max Packet Length = 6.

Yalnızca alt-eğitim ve doğrulama kümeleri kullanılır (test kümesine bakılmaz). Karşılaştırma
modelin kullandığı 45 öznitelik üzerinden yapılır. Alt-eğitim için iki hal raporlanır:
çakışma silmeden ÖNCE ve SONRA (çakışma silme tüm sütunlara bakar; 45 öznitelikte aynı olup
elenen sütunlarda farklı olan satırlar silinmeden kalır).

Kullanım:  python experiments/botnet_template_check.py [--sample-frac 0.05]
Çıktı:     reports/hafta11/sablon_kontrol.md, sablon_kontrol.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_experiments import build_variant  # noqa: E402
from run_pipeline import setup_logger, tr_int  # noqa: E402
from src import config  # noqa: E402
from src.data_loader import load_raw  # noqa: E402
from src.preprocess import resolve_label_conflicts, select_features  # noqa: E402

TEMPLATE = {"Init_Win_bytes_forward": 8192, "Init_Win_bytes_backward": 0,
            "Total Length of Fwd Packets": 0, "Total Length of Bwd Packets": 18,
            "Max Packet Length": 6}


def template_mask(X, template=TEMPLATE):
    return np.all(np.column_stack([X[c].to_numpy() == v for c, v in template.items()]), axis=1)


def compare(X, y, feats, b, k):
    """Şablona uyan satırlarda Benign / Botnet karşılaştırması (45 öznitelik)."""
    m = template_mask(X)
    Xt = X.loc[m, feats].reset_index(drop=True)
    yt = np.asarray(y)[m]
    key = pd.util.hash_pandas_object(Xt, index=False).to_numpy()
    ben_keys, bot_keys = set(key[yt == b]), set(key[yt == k])
    both = ben_keys & bot_keys
    out = {"benign_satir": int((yt == b).sum()), "botnet_satir": int((yt == k).sum()),
           "benign_farkli_vektor": len(ben_keys), "botnet_farkli_vektor": len(bot_keys),
           "iki_etikette_ortak_vektor": len(both),
           "botnet_satiri_ortak_vektorde": int(np.isin(key[yt == k], list(both)).sum()),
           "benign_satiri_ortak_vektorde": int(np.isin(key[yt == b], list(both)).sum())}
    # Ortak olmayan satırlar hangi özniteliklerde ayrışıyor? (sabit olmayan sütunlar)
    diff = []
    for f in feats:
        vb, vk = Xt.loc[yt == b, f], Xt.loc[yt == k, f]
        if len(vb) == 0 or len(vk) == 0 or (vb.nunique() == 1 and vk.nunique() == 1
                                            and vb.iloc[0] == vk.iloc[0]):
            continue
        diff.append({"oznitelik": f, "benign_medyan": float(vb.median()),
                     "benign_q1": float(vb.quantile(.25)), "benign_q3": float(vb.quantile(.75)),
                     "botnet_medyan": float(vk.median()),
                     "botnet_q1": float(vk.quantile(.25)), "botnet_q3": float(vk.quantile(.75))})
    out["degisen_oznitelikler"] = diff
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(config.DATA_DIR))
    ap.add_argument("--sample-frac", type=float, default=None)
    args = ap.parse_args(argv)
    out = config.REPORTS_DIR / "hafta11"
    if args.sample_frac:
        out = out / f"deneme_frac{args.sample_frac}"
    out.mkdir(parents=True, exist_ok=True)
    log = setup_logger(out / "sablon_kontrol_log.txt")

    raw = load_raw(args.data, args.sample_frac, log, keep_port=True)
    classes = set(raw["Label"].map(config.map_label).dropna())
    cn = [c for c in config.CLASS_ORDER if c in classes]
    V = build_variant(raw, "yok", cn, log)
    del raw
    b, k = cn.index("Benign"), cn.index("Botnet")
    X_fit, y_fit, _ = resolve_label_conflicts(V["X_sub"], V["y_sub"], V["n_sub"],
                                              config.CONFLICT_MODE)
    feats, _ = select_features(X_fit, y_fit, log, use_extratrees=config.USE_EXTRATREES)
    feats = list(feats)

    res = {"sablon": TEMPLATE, "oznitelik_sayisi": len(feats),
           "alt_egitim_cakisma_oncesi": compare(V["X_sub"], V["y_sub"], feats, b, k),
           "alt_egitim_cakisma_sonrasi": compare(X_fit, y_fit, feats, b, k),
           "dogrulama": compare(V["X_val"], V["y_val"], feats, b, k),
           "ornekleme_orani": args.sample_frac}
    res["alt_egitim_sonrasi_arti_dogrulama"] = compare(
        pd.concat([X_fit, V["X_val"]], ignore_index=True),
        np.concatenate([np.asarray(y_fit), np.asarray(V["y_val"])]), feats, b, k)
    (out / "sablon_kontrol.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    write_report(out / "sablon_kontrol.md", res)
    log(f"Bitti · {out}")
    return res


def write_report(path, r):
    names = {"alt_egitim_cakisma_oncesi": "Alt-eğitim (çakışma silmeden önce)",
             "alt_egitim_cakisma_sonrasi": "Alt-eğitim (çakışma silindikten sonra; modelin gördüğü)",
             "dogrulama": "Doğrulama",
             "alt_egitim_sonrasi_arti_dogrulama": "Alt-eğitim (sonra) + doğrulama birlikte"}
    L = ["# FP şablonu: Benign ve Botnet satırları birebir aynı mı?\n"]
    if r["ornekleme_orani"]:
        L.append("> **Uyarı:** örneklem çalıştırması; sayılar rapora yazılmaz.\n")
    L.append("Şablon: " + ", ".join(f"{c} = {v}" for c, v in r["sablon"].items())
             + f". Karşılaştırma {r['oznitelik_sayisi']} öznitelik üzerinden.\n")
    L.append("| Küme | Benign satır | Botnet satır | Benign farklı vektör | Botnet farklı vektör | "
             "İki etikette ortak vektör | Ortak vektördeki Botnet satırı | "
             "Ortak vektördeki Benign satırı |")
    L.append("| --- |" + " --- |" * 7)
    for key, name in names.items():
        c = r[key]
        L.append(f"| {name} | {tr_int(c['benign_satir'])} | {tr_int(c['botnet_satir'])} | "
                 f"{tr_int(c['benign_farkli_vektor'])} | {tr_int(c['botnet_farkli_vektor'])} | "
                 f"{tr_int(c['iki_etikette_ortak_vektor'])} | "
                 f"{tr_int(c['botnet_satiri_ortak_vektorde'])} | "
                 f"{tr_int(c['benign_satiri_ortak_vektorde'])} |")
    L.append("\n## Şablon içinde değer alan öznitelikler (alt-eğitim, çakışma sonrası)\n")
    L.append("| Öznitelik | Benign medyan [Q1–Q3] | Botnet medyan [Q1–Q3] |\n| --- | --- | --- |")
    for d in r["alt_egitim_cakisma_sonrasi"]["degisen_oznitelikler"]:
        L.append(f"| {d['oznitelik']} | {d['benign_medyan']:.6g} [{d['benign_q1']:.6g}–"
                 f"{d['benign_q3']:.6g}] | {d['botnet_medyan']:.6g} [{d['botnet_q1']:.6g}–"
                 f"{d['botnet_q3']:.6g}] |")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
