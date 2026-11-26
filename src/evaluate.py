"""Başarım metrikleri, hata matrisi ve süre ölçümleri."""
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import (accuracy_score, classification_report,
                             confusion_matrix, f1_score)

from .config import LATENCY_REPEATS


def predict_with_threshold(proba, botnet_col, t):
    """Botnet olasılığı >= t ise Botnet; değilse Botnet dışındaki en olası sütun.

    proba: predict_proba çıktısı (satır x sınıf). t=None -> düz argmax (varsayılan karar).
    Dönen değerler SÜTUN indeksidir; sınıf koduna çevirmek için model.classes_[...] kullanılır.
    Eğitimdeki değerlendirme ve uygulamadaki çıkarım bu TEK fonksiyonu kullanır.
    """
    if t is None or botnet_col is None:
        return proba.argmax(axis=1)
    rest = proba.copy()
    rest[:, botnet_col] = -np.inf          # Botnet'i dışarıda bırakıp en olası sınıfı bul
    return np.where(proba[:, botnet_col] >= t, botnet_col, rest.argmax(axis=1))


def predict_classes(model, X, class_names, botnet_threshold=None):
    """predict_proba + Botnet eşiği -> (sınıf kodları, olasılık matrisi)."""
    proba = model.predict_proba(X)
    classes = np.asarray(model.classes_)
    col = (list(classes).index(class_names.index("Botnet"))
           if botnet_threshold is not None and "Botnet" in class_names else None)
    return classes[predict_with_threshold(proba, col, botnet_threshold)], proba


def single_latency_ms(model, X, repeats=LATENCY_REPEATS):
    """Tek kayıtlık predict() çağrısının medyan süresi (ms).

    Gerçek zamanlı kullanımda tek akış geldiği için n_jobs=1 ile ölçülür;
    n_jobs=-1 tek kayıtta paralelleştirme ek yükü getirir.
    """
    old = getattr(model, "n_jobs", None)
    if old is not None:
        model.set_params(n_jobs=1)
    rng = np.random.default_rng(0)
    idx = rng.integers(0, len(X), repeats)
    for i in idx[:10]:                      # ısınma
        model.predict(X[i:i + 1])
    times = []
    for i in idx:
        t0 = time.perf_counter()
        model.predict(X[i:i + 1])
        times.append((time.perf_counter() - t0) * 1000)
    if old is not None:
        model.set_params(n_jobs=old)
    return float(np.median(times)), float(np.percentile(times, 95))


def plot_confusion(cm, class_names, title, path):
    cm_norm = cm / cm.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(8, 6.5))
    im = ax.imshow(cm_norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(class_names)), class_names, rotation=35, ha="right")
    ax.set_yticks(range(len(class_names)), class_names)
    ax.set_xlabel("Tahmin edilen sınıf")
    ax.set_ylabel("Gerçek sınıf")
    ax.set_title(title)
    for i in range(len(class_names)):
        for j in range(len(class_names)):
            color = "white" if cm_norm[i, j] > 0.5 else "black"
            ax.text(j, i, f"{cm[i, j]:,}\n%{cm_norm[i, j]*100:.1f}",
                    ha="center", va="center", fontsize=8, color=color)
    fig.colorbar(im, ax=ax, fraction=0.046, label="Satır oranı (recall)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def evaluate_model(name, model, X_test, y_test, class_names, out_dir, log=print,
                   botnet_threshold=None):
    """botnet_threshold verilirse tahmin predict_proba + eşik kuralıyla yapılır."""
    t0 = time.perf_counter()
    y_pred, _ = predict_classes(model, X_test, class_names, botnet_threshold)
    batch_s = time.perf_counter() - t0

    labels = list(range(len(class_names)))
    rep = classification_report(y_test, y_pred, labels=labels, target_names=class_names,
                                output_dict=True, zero_division=0, digits=4)
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    slug = name.lower().replace(" ", "_")
    plot_confusion(cm, class_names, f"{name} — Hata Matrisi (test kümesi)",
                   out_dir / f"confusion_matrix_{slug}.png")
    np.savetxt(out_dir / f"confusion_matrix_{slug}.csv", cm, fmt="%d", delimiter=",",
               header=",".join(class_names), comments="")

    lat_med, lat_p95 = single_latency_ms(model, X_test)

    # en çok karıştırılan sınıf çifti (köşegen dışı)
    off = cm.copy()
    np.fill_diagonal(off, 0)
    i, j = np.unravel_index(off.argmax(), off.shape)

    res = {
        "accuracy": accuracy_score(y_test, y_pred),
        "weighted_precision": rep["weighted avg"]["precision"],
        "weighted_recall": rep["weighted avg"]["recall"],
        "weighted_f1": rep["weighted avg"]["f1-score"],
        "macro_f1": f1_score(y_test, y_pred, average="macro"),
        "per_class": {c: {k: rep[c][k] for k in ("precision", "recall", "f1-score", "support")}
                      for c in class_names},
        "batch_total_s": batch_s,
        "batch_per_flow_ms": batch_s * 1000 / len(X_test),
        "single_latency_median_ms": lat_med,
        "single_latency_p95_ms": lat_p95,
        "most_confused": {"gercek": class_names[i], "tahmin": class_names[j],
                          "sayi": int(off[i, j])},
        "confusion_matrix": cm.tolist(),
    }
    log(f"[{name}] Accuracy={res['accuracy']:.4f} wF1={res['weighted_f1']:.4f} "
        f"macroF1={res['macro_f1']:.4f} tek-kayıt={lat_med:.3f} ms "
        f"toplu={res['batch_per_flow_ms']:.4f} ms/akış")
    log(classification_report(y_test, y_pred, labels=labels, target_names=class_names,
                              zero_division=0, digits=4))
    return res
