"""Sızıntısız ön işleme: temizlik -> bölme -> (yalnızca eğitimde) seçim, ölçekleme, SMOTE."""
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.model_selection import train_test_split
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from .config import (CORR_THRESHOLD, FS_SAMPLE_SIZE, IMPORTANCE_CUMSUM,
                     RANDOM_STATE, SMOTE_K, SMOTE_TARGET, TEST_SIZE, VAL_SIZE,
                     map_label)


# ---------------------------------------------------------------- 1) temizlik
def clean(df: pd.DataFrame, log=print, count_col=None):
    """count_col verilirse, tekrar silmeden önce her satırın ham veride kaç kopyası olduğu
    bu adla bir sütuna yazılır (8. hafta etiket çakışması deneyinde çoğunluk oyu için).
    Bu sütun öznitelik DEĞİLDİR; bölmeden sonra X'ten çıkarılmalıdır."""
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
    if count_col:
        # Her satırın 64 bitlik özeti; aynı özete sahip satır sayısı = kopya sayısı
        h = pd.util.hash_pandas_object(df, index=False)
        mult = h.map(h.value_counts()).to_numpy()
        keep = ~df.duplicated().to_numpy()
        df = df[keep].assign(**{count_col: mult[keep].astype(np.int64)})
    else:
        df = df.drop_duplicates()
    stats["tekrar_silinen"] = int(n - len(df))
    stats["tekrar_sonrasi"] = int(len(df))

    feats = [c for c in df.columns if c not in ("Class", count_col)]
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


def split_train_val(X, y, val_size=VAL_SIZE):
    """Eğitim kümesini katmanlı olarak alt-eğitim / doğrulama diye böler (8. hafta).

    Model ve ayar karşılaştırmaları doğrulama kümesinde yapılır; test kümesi en sona saklanır.
    Dönüş sırası train_test_split ile aynı: X_alt, X_dog, y_alt, y_dog.
    """
    return train_test_split(X, y, test_size=val_size, stratify=y, random_state=RANDOM_STATE)


def port_category(port) -> np.ndarray:
    """Hedef portu IANA aralıklarına göre kategoriye çevirir.

    0: iyi bilinen (0-1023) · 1: kayıtlı (1024-49151) · 2: dinamik/özel (49152+)
    """
    p = np.asarray(port, dtype=np.float64)
    return np.select([p <= 1023, p <= 49151], [0, 1], default=2).astype(np.float32)


# ---------------------------------------------------------------- etiket çakışmaları
def resolve_label_conflicts(X: pd.DataFrame, y, counts=None, mode="birak"):
    """Öznitelikleri birebir aynı olup farklı etiket taşıyan satır gruplarını işler.

    YALNIZCA eğitim tarafına uygulanır; doğrulama/test kümesine dokunulmaz.
    mode:
      "birak"    : değişiklik yok
      "sil"      : çakışan grupların bütün satırları silinir
      "cogunluk" : her grupta, ham veride en çok kopyası olan etiket tutulur, diğerleri silinir.
                   (Tekrar silmeden sonra her grupta etiket başına 1 satır kaldığı için satır
                   sayısı oy vermez; oy için `counts` = ham kopya sayısı kullanılır.)
                   En çok oyu iki etiket paylaşırsa grup karar verilemediği için silinir.
    Dönüş: X, y (filtrelenmiş) ve özet sözlüğü.
    """
    y_arr = np.asarray(y)
    n_arr = np.ones(len(X), dtype=np.int64) if counts is None else np.asarray(counts)
    key = pd.util.hash_pandas_object(X, index=False).to_numpy()   # satır özeti
    d = pd.DataFrame({"k": key, "y": y_arr, "n": n_arr})
    conflict = (d.groupby("k")["y"].transform("nunique") > 1).to_numpy()
    info = {"mod": mode, "cakisan_grup": int(d.loc[conflict, "k"].nunique()),
            "cakisan_satir": int(conflict.sum()), "esit_oylu_grup": 0}

    if mode == "birak":
        keep = np.ones(len(X), dtype=bool)
    elif mode == "sil":
        keep = ~conflict
    elif mode == "cogunluk":
        c = d[conflict]
        votes = c.groupby(["k", "y"])["n"].sum()                     # grup x etiket oyları
        is_max = votes == votes.groupby(level=0).transform("max")
        n_max = is_max.groupby(level=0).transform("sum")
        winners = votes.index[is_max & (n_max == 1)]                 # tek kazananı olanlar
        info["esit_oylu_grup"] = int(n_max[is_max & (n_max > 1)].index
                                     .get_level_values(0).nunique())
        won = pd.MultiIndex.from_frame(c[["k", "y"]]).isin(winners)
        keep = ~conflict
        keep[np.flatnonzero(conflict)[won]] = True
    else:
        raise ValueError(f"Bilinmeyen mod: {mode}")

    info["silinen_satir"] = int((~keep).sum())
    y_out = y[keep] if hasattr(y, "iloc") else y_arr[keep]
    return X[keep], y_out, info


def _stratified_sample(X, y, size):
    if len(X) <= size:
        return X, y
    Xs, _, ys, _ = train_test_split(X, y, train_size=size, stratify=y,
                                    random_state=RANDOM_STATE)
    return Xs, ys


# ---------------------------------------------------------------- 3) öznitelik seçimi
def select_features(X_train: pd.DataFrame, y_train, log=print, use_extratrees=True):
    """Yalnızca eğitim kümesi kullanılır. Test kümesi bu fonksiyona hiç girmez.

    use_extratrees=False: yalnızca korelasyon elemesi yapılır, kalan TÜM öznitelikler döner.
    9. haftadan itibaren ana pipeline böyle çalışır (8. hafta Ek 1: ExtraTrees adımı doğrulamada
    yarar sağlamadı ve küçük veri değişikliklerinde seçilen kümeyi değiştirip kararsızlık yarattı).
    Varsayılan True, 8. hafta deney betikleri aynı sonucu üretebilsin diye korunur.
    """
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

    if not use_extratrees:
        log("ExtraTrees seçimi kapalı: korelasyon sonrası tüm öznitelikler kullanılıyor")
        return list(kept), {"korelasyonla_elenen": dropped, "korelasyon_sonrasi_sayi": len(kept),
                            "secilen_sayi": len(kept), "onem_skorlari": {}}

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


class SmoteTarget:
    """imblearn SMOTE için `sampling_strategy` olarak kullanılan çağrılabilir nesne.

    Her çağrıda (ör. çapraz doğrulamanın her katında) o anki y'ye bakar: en büyük sınıf
    hariç, `target` altındaki sınıfları `target`'a tamamlar. Sabit sözlük yerine bunun
    kullanılmasının nedeni, katlardaki sınıf sayılarının değişmesi ve hedefin altında
    kalmayan sınıf için imblearn'ün hata vermesidir. Windows'ta paralel işlerde
    taşınabilmesi (pickle) için modül düzeyinde sınıf olarak tanımlıdır.
    """

    def __init__(self, target):
        self.target = int(target)

    def __call__(self, y):
        counts = pd.Series(y).value_counts()
        majority = counts.idxmax()
        target = min(self.target, int(counts.max()))
        return {c: target for c, n in counts.items() if n < target and c != majority}


def oversample(X, y, log=print, target=SMOTE_TARGET):
    """target: küçük sınıfların tamamlanacağı satır sayısı (varsayılan config.SMOTE_TARGET)."""
    counts = pd.Series(y).value_counts()
    majority = counts.idxmax()   # en büyük sınıf (Benign) asla çoğaltılmaz
    target = min(int(target), int(counts.max()))
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
