"""Sızıntısız ön işleme: temizlik -> bölme -> (yalnızca eğitimde) seçim, ölçekleme, SMOTE."""
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.model_selection import train_test_split
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from .config import (CORR_THRESHOLD, FS_SAMPLE_SIZE, IMPORTANCE_CUMSUM,
                     RANDOM_STATE, SMOTE_K, SMOTE_TARGET, TEST_SIZE, map_label)


# ---------------------------------------------------------------- 1) temizlik
def clean(df: pd.DataFrame, log=print):
    stats = {"ham_satir": int(len(df))}

    df = df.copy()
    df["Class"] = df["Label"].map(map_label)
    n = len(df)
    df = df[df["Class"].notna()].drop(columns=["Label"])
    stats["kapsam_disi_silinen"] = int(n - len(df))
    stats["kapsam_disi_sonrasi"] = int(len(df))

    n = len(df)
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    stats["inf_nan_silinen"] = int(n - len(df))
    stats["inf_nan_sonrasi"] = int(len(df))

    n = len(df)
    df = df.drop_duplicates()
    stats["tekrar_silinen"] = int(n - len(df))
    stats["tekrar_sonrasi"] = int(len(df))

    feats = [c for c in df.columns if c != "Class"]
    const = [c for c in feats if df[c].nunique() <= 1]
    df = df.drop(columns=const)
    stats["sabit_sutunlar"] = const

    log(f"Kapsam dışı silinen: {stats['kapsam_disi_silinen']:,}")
    log(f"Inf/NaN silinen: {stats['inf_nan_silinen']:,}")
    log(f"Tekrarlayan silinen: {stats['tekrar_silinen']:,}")
    log(f"Sabit sütunlar ({len(const)}): {const}")
    log(f"Temiz veri: {len(df):,} satır")
    return df.reset_index(drop=True), stats


# ---------------------------------------------------------------- 2) bölme
def split(df: pd.DataFrame):
    X = df.drop(columns=["Class"])
    y = df["Class"]
    return train_test_split(X, y, test_size=TEST_SIZE, stratify=y,
                            random_state=RANDOM_STATE)


def _stratified_sample(X, y, size):
    if len(X) <= size:
        return X, y
    Xs, _, ys, _ = train_test_split(X, y, train_size=size, stratify=y,
                                    random_state=RANDOM_STATE)
    return Xs, ys


# ---------------------------------------------------------------- 3) öznitelik seçimi
def select_features(X_train: pd.DataFrame, y_train, log=print):
    """Yalnızca eğitim kümesi kullanılır. Test kümesi bu fonksiyona hiç girmez."""
    Xs, ys = _stratified_sample(X_train, y_train, FS_SAMPLE_SIZE)

    # a) Korelasyon: varyansı yüksek olandan başlayarak, tutulanlarla > eşik olanları ele
    corr = Xs.astype("float64").corr().abs().fillna(0.0)
    order = Xs.var().sort_values(ascending=False).index
    kept, dropped = [], []
    for c in order:
        if any(corr.loc[c, k] > CORR_THRESHOLD for k in kept):
            dropped.append(c)
        else:
            kept.append(c)
    log(f"Korelasyon elemesi: {len(dropped)} öznitelik elendi, {len(kept)} kaldı")

    # b) ExtraTrees önem sıralaması
    et = ExtraTreesClassifier(n_estimators=100, n_jobs=-1, random_state=RANDOM_STATE)
    et.fit(Xs[kept], ys)
    imp = pd.Series(et.feature_importances_, index=kept).sort_values(ascending=False)
    cum = imp.cumsum()
    n_sel = int((cum < IMPORTANCE_CUMSUM).sum()) + 1
    selected = list(imp.index[:n_sel])
    log(f"ExtraTrees: kümülatif önem %{IMPORTANCE_CUMSUM*100:.0f} için {len(selected)} öznitelik seçildi")

    info = {
        "korelasyonla_elenen": dropped,
        "korelasyon_sonrasi_sayi": len(kept),
        "secilen_sayi": len(selected),
        "onem_skorlari": {k: float(v) for k, v in imp.items()},
    }
    return selected, info


# ---------------------------------------------------------------- 4) ölçekleme
def fit_scaler(X_train: np.ndarray):
    scaler = StandardScaler()
    scaler.fit(X_train)
    return scaler


# ---------------------------------------------------------------- 5) SMOTE
def _simple_smote(X, y, strategy, k, random_state):
    """imbalanced-learn kurulu değilse kullanılan, aynı mantıkta basit SMOTE."""
    rng = np.random.default_rng(random_state)
    Xs, ys = [X], [y]
    for cls, target in strategy.items():
        Xc = X[y == cls]
        n_new = target - len(Xc)
        if n_new <= 0:
            continue
        kk = min(k, len(Xc) - 1)
        nn = NearestNeighbors(n_neighbors=kk + 1).fit(Xc)
        base = rng.integers(0, len(Xc), n_new)
        neigh = nn.kneighbors(Xc[base], return_distance=False)[:, 1:]
        pick = neigh[np.arange(n_new), rng.integers(0, kk, n_new)]
        gap = rng.random((n_new, 1)).astype(X.dtype)
        Xs.append(Xc[base] + gap * (Xc[pick] - Xc[base]))
        ys.append(np.full(n_new, cls, dtype=y.dtype))
    return np.vstack(Xs), np.concatenate(ys)


def oversample(X, y, log=print):
    counts = pd.Series(y).value_counts()
    majority = counts.idxmax()   # en büyük sınıf (Benign) asla çoğaltılmaz
    target = min(SMOTE_TARGET, int(counts.max()))
    strategy = {int(c): target for c, n in counts.items() if n < target and c != majority}
    if not strategy:
        log("SMOTE: hedefin altında sınıf yok, atlandı")
        return X, y, "yok"
    k = min(SMOTE_K, int(counts[list(strategy)].min()) - 1)
    try:
        from imblearn.over_sampling import SMOTE
        sm = SMOTE(sampling_strategy=strategy, k_neighbors=k, random_state=RANDOM_STATE)
        Xr, yr = sm.fit_resample(X, y)
        method = "imblearn.SMOTE"
    except ImportError:
        log("UYARI: imbalanced-learn bulunamadı, yedek SMOTE kullanılıyor")
        Xr, yr = _simple_smote(X, y, strategy, k, RANDOM_STATE)
        method = "yedek SMOTE (imblearn yok)"
    log(f"SMOTE ({method}, k={k}): {len(X):,} -> {len(Xr):,} satır")
    return Xr.astype(np.float32), yr, method
