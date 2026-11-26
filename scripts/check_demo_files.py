"""Demo dosyalarını arayüzün kullandığı akışla (src/service.py::run_analysis) analiz eder ve
sonuçları reports/hafta9/ altına yazar. Arayüz açmadan uçtan uca kontrol için.

Ölçülen süre: CSV okuma + doğrulama + ölçekleme + tahmin (arayüzde gösterilen süreyle aynı).
Her dosya 3 kez analiz edilir; ilk çalıştırma ve 3 çalıştırmanın medyanı ayrı raporlanır.
Analizler geçici bir veritabanına yazılır (uygulamanın asıl geçmişine karışmaz).
Alarmlar iki kez hesaplanır: eşiksiz (N=1, her tespit edilen akış alarm) ve eşikli
(config.ALARM_MIN_FLOWS). Tahminler ikisinde de aynıdır; yalnızca alarm seviyesi değişir.

Kullanım:  python scripts/check_demo_files.py
"""
import json
import statistics
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.alarm import get_security_logger, raise_alarms  # noqa: E402
from src.inference import InferenceError, Predictor  # noqa: E402
from src.service import run_analysis  # noqa: E402

FILES = ["demo_normal.csv", "demo_ddos.csv", "demo_portscan.csv", "demo_karma.csv",
         "demo_10000_satir.csv", "demo_bozuk.csv", "demo_eksik_sutun.csv"]
REPEATS = 3


def _fmt(alarms):
    return "; ".join(f"{a['sinif']} {a['adet']} "
                     f"{'incelenmeli' if a['dusuk_sayi'] else a['seviye']}" for a in alarms)


def compare_thresholds(summary, n=None):
    """Aynı sınıf özetinden eşiksiz (N=1) ve eşikli alarmları üretir (log/DB'ye yazmadan)."""
    n = config.ALARM_MIN_FLOWS if n is None else n
    a1, an = raise_alarms(summary, "-", min_flows=1), raise_alarms(summary, "-", min_flows=n)
    return {"esiksiz_kritik": sum(a["seviye"] == "CRITICAL" for a in a1),
            "esiksiz_alarmlar": _fmt(a1), "esik_N": n,
            "esikli_kritik": sum(a["seviye"] == "CRITICAL" for a in an),
            "esikli_incelenmeli": sum(a["dusuk_sayi"] for a in an),
            "esikli_alarmlar": _fmt(an)}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    out = config.REPORTS_DIR / "hafta9"
    out.mkdir(parents=True, exist_ok=True)
    predictor = Predictor()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        db, logger = Path(tmp) / "demo.db", get_security_logger(Path(tmp) / "logs")
        for name in FILES:
            path = config.DEMO_DIR / name
            times, row = [], {"dosya": name}
            for _ in range(REPEATS):
                try:
                    res, _, alarms = run_analysis(predictor, path, name, db, logger,
                                                  min_flows=config.ALARM_MIN_FLOWS)
                except InferenceError as e:
                    row.update(durum="uyarı", mesaj=str(e))
                    break
                times.append(res.duration_s)
            if times:
                ev = res.evaluation or {}
                row.update(
                    durum="tamam", toplam_satir=res.total_rows, atlanan_satir=res.skipped_rows,
                    analiz_edilen=res.analyzed_rows, saldiri_tahmini=res.attack_rows,
                    dogruluk=ev.get("accuracy"), macro_f1=ev.get("macro_f1"),
                    alarm_sayisi=len(alarms),
                    kritik_alarm=sum(a["seviye"] == "CRITICAL" for a in alarms),
                    alarmlar="; ".join(f"{a['sinif']} ({a['adet']}, {a['seviye']})"
                                       for a in alarms),
                    **compare_thresholds(res.class_summary),
                    sure_ilk_sn=times[0], sure_medyan_sn=statistics.median(times),
                    satir_basi_ms=statistics.median(times) * 1000 / res.total_rows,
                    atlama_nedenleri=json.dumps(res.skipped_reasons, ensure_ascii=False))
            rows.append(row)
            print({k: row.get(k) for k in ("dosya", "durum", "dogruluk", "alarm_sayisi",
                                           "sure_medyan_sn", "mesaj") if row.get(k) is not None})
        for h in list(logger.handlers):
            h.close()
            logger.removeHandler(h)
    df = pd.DataFrame(rows)
    df.to_csv(out / "demo_sonuclari.csv", index=False, encoding="utf-8")
    print(f"Yazıldı: {out / 'demo_sonuclari.csv'}")


if __name__ == "__main__":
    main()
