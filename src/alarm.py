"""Güvenlik günlüğü ve alarm üretimi (F11).

* logs/security.log dosyasına RotatingFileHandler ile yazılır: dosya `max_bytes`'a ulaşınca
  security.log.1, .2 ... olarak döndürülür ve en fazla `backup_count` eski dosya tutulur.
  Böylece günlük dosyası diski sınırsız doldurmaz.
* Her analiz için saldırı sınıfı başına TEK satır yazılır (akış başına değil). 10.000 DDoS akışı
  10.000 satır değil, "DoS/DDoS adet=10000" diyen tek bir satır üretir; günlük okunabilir kalır.
* Seviyeler config.ALARM_LEVELS'tan gelir: DoS/DDoS, Botnet, Web Attack, Brute Force -> CRITICAL;
  PortScan -> WARNING (keşif aşaması, tek başına zarar vermez); Benign -> alarm yok.
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import config, database

LEVELS = {"WARNING": logging.WARNING, "CRITICAL": logging.CRITICAL}


def get_security_logger(log_dir=config.LOG_DIR, max_bytes=1_000_000, backup_count=5):
    """security.log'a yazan logger'ı döndürür; aynı dosya için ikinci kez handler eklemez.

    Streamlit betiği her etkileşimde yeniden çalışır; kontrol olmasa her çalıştırmada yeni bir
    handler eklenir ve her alarm satırı defalarca yazılırdı.
    """
    path = (Path(log_dir) / "security.log").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"security.{path}")
    logger.setLevel(logging.WARNING)
    logger.propagate = False                 # kök logger'a (konsola) tekrar gönderme
    if not any(isinstance(h, RotatingFileHandler) and Path(h.baseFilename) == path
               for h in logger.handlers):
        h = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count,
                                encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s",
                                         "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(h)
    return logger


def raise_alarms(class_summary, file_name, analiz_id=None, conn=None, logger=None):
    """Sınıf özetinden alarm üretir; günlüğe ve (conn verilirse) veritabanına yazar.

    class_summary: sinif, adet, ortalama_guven sütunlu DataFrame (AnalysisResult.class_summary).
    Dönüş: üretilen alarmların listesi (sözlük).
    """
    alarms = []
    for row in class_summary.itertuples(index=False):
        level = config.ALARM_LEVELS.get(row.sinif)
        if level is None or int(row.adet) <= 0:          # Benign veya bilinmeyen sınıf
            continue
        alarm = {"sinif": row.sinif, "adet": int(row.adet), "seviye": level,
                 "ortalama_guven": float(row.ortalama_guven)}
        if logger is not None:
            logger.log(LEVELS[level], f"analiz_id={analiz_id} dosya={file_name} "
                                      f"sinif={row.sinif} adet={int(row.adet)} "
                                      f"ort_guven={float(row.ortalama_guven):.3f}")
        if conn is not None and analiz_id is not None:
            alarm["id"] = database.save_alarm(conn, analiz_id, row.sinif, row.adet, level)
        alarms.append(alarm)
    # Önce CRITICAL, sonra en çok akış: arayüzde en önemli alarm en üstte görünsün
    alarms.sort(key=lambda a: (a["seviye"] != "CRITICAL", -a["adet"]))
    return alarms
