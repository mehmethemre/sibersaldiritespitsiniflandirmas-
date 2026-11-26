"""Çıkarım (inference): eğitilmiş modeli yükler, yeni bir CSV'deki akışları sınıflandırır.

Akış:  CSV oku -> sütun adlarını temizle -> gerekli öznitelikler var mı? -> sayıya çevir,
       bozuk satırları (sayı olmayan, Inf, NaN) atla -> eğitimdeki ölçekleyiciyle dönüştür ->
       predict_proba + Botnet eşiği -> sınıf + güven skoru -> (Label varsa) gerçekle karşılaştır.

Neden böyle?
* Model, eğitimde gördüğü ölçekleyici ve öznitelik SIRASI ile beslenmezse sessizce yanlış
  tahmin yapar. Bu yüzden features.json'daki sıra ve scaler.pkl aynen kullanılır.
* Botnet eşiği (model_config.json) eğitimdeki değerlendirmeyle AYNI fonksiyonla uygulanır
  (src/evaluate.py::predict_classes); kural iki yerde ayrı yazılmaz.
* Kullanıcıya gösterilecek her sorun InferenceError olarak yükseltilir; arayüz yalnızca bunu
  yakalayıp anlaşılır bir uyarı gösterir. Program bozuk dosyada çökmez (F4, N4).
"""
import io
import json
import logging
import re
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix

from . import config
from .evaluate import predict_classes

log = logging.getLogger(__name__)
LABEL_COLUMN = "Label"
# Dosya başı imzası -> türü (CSV yerine yüklenebilecek yaygın ikili dosyalar)
BINARY_SIGNATURES = {b"PK\x03\x04": "zip veya Excel .xlsx", b"\xd0\xcf\x11\xe0": "Excel .xls",
                     b"%PDF": "PDF", b"\x89PNG": "PNG resmi", b"\xff\xd8\xff": "JPEG resmi",
                     b"\x1f\x8b": "gzip"}


class InferenceError(Exception):
    """Kullanıcıya olduğu gibi gösterilebilecek, Türkçe mesajlı hata."""


class MissingColumnsError(InferenceError):
    def __init__(self, missing, n_required):
        self.missing = list(missing)
        shown = ", ".join(self.missing[:15])
        if len(self.missing) > 15:
            shown += f" ve {len(self.missing) - 15} sütun daha"
        super().__init__(
            f"Dosyada modelin ihtiyaç duyduğu {n_required} sütundan {len(self.missing)} tanesi "
            f"eksik: {shown}. CICFlowMeter / CICIDS2017 biçiminde bir CSV yükleyin.")


@dataclass
class AnalysisResult:
    predictions: pd.DataFrame        # satir_no, tahmin, guven, (gercek)
    class_summary: pd.DataFrame      # sinif, adet, ortalama_guven
    total_rows: int                  # dosyadaki veri satırı sayısı
    skipped_rows: int                # bozuk olduğu için atlanan satır
    skipped_reasons: dict            # neden -> satır sayısı (bir satır birden çok nedende olabilir)
    duration_s: float
    model_version: str
    evaluation: dict | None = None   # Label sütunu varsa gerçek etiketlerle karşılaştırma
    notes: list = field(default_factory=list)

    @property
    def analyzed_rows(self):
        return len(self.predictions)

    @property
    def attack_rows(self):
        return int((self.predictions["tahmin"] != "Benign").sum())


class Predictor:
    """Model ve yardımcı dosyaları bir kez yükler; `analyze` ile CSV analiz eder."""

    def __init__(self, artifacts_dir=config.ARTIFACTS_DIR):
        d = Path(artifacts_dir)
        try:
            self.model_config = json.loads((d / "model_config.json").read_text(encoding="utf-8"))
            self.features = json.loads((d / "features.json").read_text(encoding="utf-8"))
            self.model = joblib.load(d / self.model_config["model_dosyasi"])
            self.scaler = joblib.load(d / self.model_config["olcekleyici_dosyasi"])
        except FileNotFoundError as e:
            raise InferenceError(
                f"Model dosyası bulunamadı ({Path(e.filename).name}). Önce modeli eğitin: "
                "python run_pipeline.py") from e
        self.class_names = self.model_config["siniflar"]
        self.botnet_threshold = self.model_config.get("botnet_esigi")
        self.version = self.model_config.get("model_surumu", "bilinmiyor")
        if len(self.features) != self.scaler.n_features_in_:
            raise InferenceError("features.json ile ölçekleyici uyumsuz; modeli yeniden eğitin.")

    # ------------------------------------------------------------ 1) okuma
    @staticmethod
    def read_csv(source) -> pd.DataFrame:
        """Yol, bayt dizisi veya dosya benzeri nesneden (Streamlit yüklemesi) CSV okur."""
        if isinstance(source, (str, Path)):
            data = Path(source).read_bytes()
        elif isinstance(source, (bytes, bytearray)):
            data = bytes(source)
        elif hasattr(source, "getvalue"):
            data = source.getvalue()
        else:
            data = source.read()
        if not data or not data.strip():
            raise InferenceError("Dosya boş.")
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):     # Excel'in "Unicode metin" (UTF-16) kaydı
            try:
                data = data.decode("utf-16").encode("utf-8")
            except UnicodeDecodeError as e:
                raise InferenceError("Dosyanın karakter kodlaması okunamadı (UTF-16).") from e
        # İkili dosya (Excel, zip, resim...) CSV gibi okunmaya çalışılırsa yanıltıcı "sütun eksik"
        # mesajları çıkar; imzasından tanınıp açıkça söylenir. NUL baytı metin dosyasında olmaz.
        kind = next((v for k, v in BINARY_SIGNATURES.items() if data.startswith(k)), None)
        if kind or b"\x00" in data[:4096]:
            raise InferenceError(
                f"Dosya bir CSV metin dosyası değil ({kind or 'ikili veri'}). Excel'de "
                "açtıysanız \"CSV (virgülle ayrılmış)\" olarak kaydedip yeniden yükleyin.")
        # Önce UTF-8; CICIDS dosyalarında bozuk kodlanmış karakterler olabildiği için latin-1 yedek
        for enc in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(data), encoding=enc, low_memory=False)
                break
            except UnicodeDecodeError:
                continue
            except pd.errors.EmptyDataError as e:
                raise InferenceError("Dosyada okunabilir veri yok.") from e
            except pd.errors.ParserError as e:
                m = re.search(r"line (\d+)", str(e))     # pandas mesajı İngilizce; satırı al
                where = f"{m.group(1)}. satırda " if m else ""
                raise InferenceError(
                    f"CSV biçimi okunamadı: {where}başlıktakinden farklı sayıda alan var. "
                    "Dosyanın virgülle ayrılmış bir CSV olduğundan emin olun.") from e
        df.columns = [str(c).strip() for c in df.columns]   # gerçek dosyalarda baştaki boşluk
        if len(df) == 0:
            raise InferenceError("Dosyada başlık satırı var ama veri satırı yok.")
        return df

    # ------------------------------------------------------------ 2) doğrulama
    def _match_columns(self, df):
        """Büyük/küçük harf farkıyla yazılmış sütunları modeldeki adlara eşler."""
        lower = {c.lower(): c for c in df.columns}
        rename = {lower[f.lower()]: f for f in self.features
                  if f not in df.columns and f.lower() in lower}
        return df.rename(columns=rename) if rename else df

    def prepare(self, df):
        """Gerekli öznitelikleri seçer, bozuk satırları ayıklar, ölçekler.

        Dönüş: (X ölçeklenmiş, geçerli satırların maskesi, neden->sayı sözlüğü)
        """
        df = self._match_columns(df)
        missing = [f for f in self.features if f not in df.columns]
        if len(missing) == len(self.features) and len(df.columns) == 1 and \
                any(s in df.columns[0] for s in (";", "\t")):
            raise InferenceError(
                "Sütunlar virgülle değil, noktalı virgül veya sekmeyle ayrılmış görünüyor "
                "(Türkçe Excel ayarı). Dosyayı virgülle ayrılmış CSV olarak kaydedin.")
        if missing:
            raise MissingColumnsError(missing, len(self.features))

        raw = df[self.features]
        num = raw.apply(pd.to_numeric, errors="coerce")       # sayı olmayan hücre -> NaN
        with np.errstate(over="ignore"):
            arr = num.to_numpy(np.float64).astype(np.float32)  # float32'ye sığmayan -> inf
        reasons = {
            "boş hücre": int(raw.isna().any(axis=1).sum()),
            "sayıya çevrilemeyen değer": int((num.isna() & raw.notna()).any(axis=1).sum()),
            "sonsuz (Inf) veya aşırı büyük değer": int(np.isinf(arr).any(axis=1).sum()),
        }
        valid = np.isfinite(arr).all(axis=1)
        reasons = {k: v for k, v in reasons.items() if v}
        if not valid.any():
            raise InferenceError(
                f"Dosyadaki {len(df):,} satırın hiçbiri analiz edilemedi "
                f"({', '.join(f'{k}: {v:,}' for k, v in reasons.items())}).")
        X = self.scaler.transform(arr[valid]).astype(np.float32)
        return X, valid, reasons

    # ------------------------------------------------------------ 3) tahmin
    def predict(self, df, t_start=None):
        t_start = time.perf_counter() if t_start is None else t_start
        X, valid, reasons = self.prepare(df)
        codes, proba = predict_classes(self.model, X, self.class_names, self.botnet_threshold)
        col_of = {c: i for i, c in enumerate(self.model.classes_)}
        conf = proba[np.arange(len(codes)), [col_of[c] for c in codes]]
        names = np.asarray(self.class_names)[codes]

        pred = pd.DataFrame({"satir_no": np.flatnonzero(valid) + 1,   # 1 = ilk veri satırı
                             "tahmin": names, "guven": conf.astype(float)})
        evaluation, notes = None, []
        if LABEL_COLUMN in df.columns:
            truth = df.loc[valid, LABEL_COLUMN].map(config.map_label).to_numpy()
            pred["gercek"] = truth
            evaluation = self._evaluate(truth, names)
            if evaluation is None:
                notes.append("Label sütunu var ama proje sınıflarıyla eşleşen etiket yok.")

        summary = (pred.groupby("tahmin")["guven"].agg(adet="size", ortalama_guven="mean")
                   .reindex([c for c in self.class_names if c in set(names)])
                   .rename_axis("sinif").reset_index())
        summary["adet"] = summary["adet"].astype(int)
        return AnalysisResult(
            predictions=pred, class_summary=summary, total_rows=int(len(df)),
            skipped_rows=int((~valid).sum()), skipped_reasons=reasons,
            duration_s=time.perf_counter() - t_start, model_version=self.version,
            evaluation=evaluation, notes=notes)

    def _evaluate(self, truth, pred):
        """Gerçek etiketi kapsam içinde olan satırlarda doğruluk ve sınıf bazında sonuç."""
        in_scope = pd.notna(truth)
        if not in_scope.any():
            return None
        t, p = truth[in_scope].astype(str), pred[in_scope]
        labels = [c for c in self.class_names if c in set(t) | set(p)]
        rep = classification_report(t, p, labels=labels, output_dict=True, zero_division=0)
        report = pd.DataFrame(
            [{"sinif": c, "precision": rep[c]["precision"], "recall": rep[c]["recall"],
              "f1": rep[c]["f1-score"], "destek": int(rep[c]["support"])} for c in labels])
        with warnings.catch_warnings():     # tek sınıflı dosyada sklearn'ün zararsız uyarısı
            warnings.simplefilter("ignore", UserWarning)
            cm_values = confusion_matrix(t, p, labels=labels)
        cm = pd.DataFrame(cm_values,
                          index=pd.Index(labels, name="Gerçek"),
                          columns=pd.Index(labels, name="Tahmin"))
        # Macro F1, dosyada GERÇEKTE bulunan sınıflar üzerinden: yalnızca Benign içeren bir
        # dosyada yanlışlıkla 2 akışa "DoS" denirse, dosyada hiç olmayan DoS sınıfı F1=0 ile
        # ortalamaya girip skoru %33'e düşürmesin.
        present = [c for c in labels if c in set(t)]
        macro = float(report.set_index("sinif").loc[present, "f1"].mean())
        return {"accuracy": float((t == p).mean()), "karsilastirilan": int(in_scope.sum()),
                "kapsam_disi_etiket": int((~in_scope).sum()), "rapor": report,
                "hata_matrisi": cm, "macro_f1": macro, "macro_f1_siniflari": present}

    # ------------------------------------------------------------ hepsi bir arada
    def analyze(self, source):
        """CSV'yi okuyup analiz eder. Bilinen her sorunda InferenceError yükseltir."""
        t0 = time.perf_counter()
        try:
            return self.predict(self.read_csv(source), t_start=t0)
        except InferenceError:
            raise
        except MemoryError as e:
            raise InferenceError("Dosya bu bilgisayarın belleği için çok büyük.") from e
        except Exception as e:  # beklenmeyen her şey: kayda geç, kullanıcıya sade mesaj ver
            log.exception("Analiz sırasında beklenmeyen hata")
            raise InferenceError(f"Dosya analiz edilemedi ({type(e).__name__}: {e}).") from e
