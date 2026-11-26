"""N3 bellek ve N2 süre ölçümü: tahmin yaparken sürecin tepe belleği (peak RSS) ve süresi.

Ölçülen durumlar (her biri AYRI bir alt süreçte, en az 3 tekrar):
  import          yalnızca kütüphanelerin yüklenmesi (taban)
  model           + modelin yüklenmesi (Predictor)
  <n> satır       + arayüzün kullandığı akışla (src/service.py::run_analysis) <n> satırlık CSV
                  analizi: okuma -> doğrulama -> tahmin -> SQLite -> alarm/log

Neden her durum ayrı süreçte? İşletim sisteminin verdiği "tepe bellek" sürecin ömrü boyunca
görülen en büyük değerdir; aynı süreçte arka arkaya ölçülse küçük dosya, önceki büyük dosyanın
tepesini miras alırdı.
  Windows: psutil memory_info().peak_wset (tepe çalışma kümesi = peak RSS)
  Linux:   resource.getrusage(RUSAGE_SELF).ru_maxrss (KB)

Ölçüm dosyaları TEST kümesinden örneklenir (make_demo_files.py ile aynı yeniden üretim) ve
yalnızca performans ölçümünde kullanılır; data/perf/ altına yazılır (GitHub'a yüklenmez).
Analizler geçici veritabanı ve geçici log dosyasına yazılır.

Kullanım:
    python scripts/measure_memory.py --prepare     # ölçüm dosyalarını üret (bir kez)
    python scripts/measure_memory.py               # ölçüm (varsayılan 3 tekrar)
Çıktılar: reports/hafta10/bellek_olcum.csv (ham), bellek_ozet.csv, ortam.json
"""
import argparse
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PERF_DIR = ROOT / "data" / "perf"
OUT_DIR = ROOT / "reports" / "hafta10"
SIZES = [1, 10_000, 100_000, "tum"]     # "tum" = tüm test kümesi
REPEATS = 3


def perf_file(size):
    return PERF_DIR / f"perf_{size}.csv"


def peak_mb():
    """Sürecin şimdiye kadarki tepe belleği (MB)."""
    if platform.system() == "Windows":
        import psutil
        return psutil.Process().memory_info().peak_wset / 1024**2
    import resource
    kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return kb / 1024 if platform.system() == "Linux" else kb / 1024**2   # macOS: bayt


def prepare():
    from src import config
    from src.data_loader import load_raw
    from src.preprocess import clean, split
    raw = load_raw(config.DATA_DIR, log=lambda *_: None)
    df, _ = clean(raw, log=lambda *_: None)
    del raw
    _, X_te, _, y_te = split(df)              # run_pipeline.py ile aynı bölme
    test = X_te.assign(Label=y_te.to_numpy())
    PERF_DIR.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        d = test if size == "tum" else test.sample(n=size, random_state=config.RANDOM_STATE)
        d.to_csv(perf_file(size), index=False)
        print(f"{perf_file(size).name}: {len(d):,} satır, "
              f"{perf_file(size).stat().st_size / 1024**2:.1f} MB")


def worker(case):
    """Tek bir durumu ölçer, sonucu JSON olarak stdout'a yazar."""
    t0 = time.perf_counter()
    from src.alarm import get_security_logger
    from src.inference import Predictor
    from src.service import run_analysis
    r = {"import_s": time.perf_counter() - t0}
    if case != "import":
        t1 = time.perf_counter()
        predictor = Predictor()
        r["model_yukleme_s"] = time.perf_counter() - t1
    if case not in ("import", "model"):
        path = perf_file(case)
        with tempfile.TemporaryDirectory() as tmp:
            logger = get_security_logger(Path(tmp) / "logs")
            t2 = time.perf_counter()
            res, _, alarms = run_analysis(predictor, path, path.name, Path(tmp) / "olcum.db",
                                          logger)
            r["uctan_uca_s"] = time.perf_counter() - t2     # analiz + SQLite + log
            for h in list(logger.handlers):                 # Windows: dosya kilidini bırak
                h.close()
                logger.removeHandler(h)
        r.update(analiz_s=res.duration_s, satir=res.total_rows,
                 dosya_mb=path.stat().st_size / 1024**2)
    r["tepe_mb"] = peak_mb()
    print(json.dumps(r))


def environment():
    import joblib
    import psutil
    import sklearn
    import streamlit
    from run_pipeline import hardware_info
    info = hardware_info()
    info.update(joblib=joblib.__version__, streamlit=streamlit.__version__,
                psutil=psutil.__version__, platform=platform.platform(),
                fiziksel_cekirdek=psutil.cpu_count(logical=False))
    info["scikit_learn"] = sklearn.__version__
    return info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--worker")
    ap.add_argument("--repeats", type=int, default=REPEATS)
    args = ap.parse_args(argv)
    if args.prepare:
        return prepare()
    if args.worker:
        return worker(args.worker)

    import pandas as pd
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "ortam.json").write_text(json.dumps(environment(), ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    cases = ["import", "model"] + [s for s in SIZES if perf_file(s).exists()]
    missing = [s for s in SIZES if not perf_file(s).exists()]
    if missing:
        print(f"Uyarı: ölçüm dosyası yok ({missing}); önce --prepare çalıştırın.")
    rows = []
    for case in cases:
        for k in range(args.repeats):
            p = subprocess.run([sys.executable, __file__, "--worker", str(case)],
                               capture_output=True, text=True, cwd=ROOT)
            if p.returncode != 0:
                print(p.stderr)
                raise SystemExit(f"Ölçüm başarısız: {case}")
            r = json.loads(p.stdout.strip().splitlines()[-1])
            rows.append({"durum": str(case), "tekrar": k + 1, **r})
            print(f"{case!s:>8} #{k + 1}: tepe {r['tepe_mb']:.0f} MB"
                  + (f", analiz {r['analiz_s']:.3f} sn" if "analiz_s" in r else ""))
    raw = pd.DataFrame(rows)
    raw.to_csv(OUT_DIR / "bellek_olcum.csv", index=False, encoding="utf-8")
    metrics = [c for c in ("tepe_mb", "model_yukleme_s", "analiz_s", "uctan_uca_s")
               if c in raw]
    summary = raw.groupby("durum", sort=False)[metrics].agg(["mean", "max"])
    summary.columns = [f"{m}_{'ort' if s == 'mean' else 'en_kotu'}" for m, s in summary.columns]
    summary.insert(0, "tekrar", raw.groupby("durum", sort=False).size())
    summary.to_csv(OUT_DIR / "bellek_ozet.csv", encoding="utf-8")
    print(summary.round(3).to_string())


if __name__ == "__main__":
    main()
