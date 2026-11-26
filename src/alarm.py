"""Güvenlik günlüğü ve alarm üretimi (F11).

* logs/security.log dosyasına RotatingFileHandler ile yazılır: dosya `max_bytes`'a ulaşınca
  security.log.1, .2 ... olarak döndürülür ve en fazla `backup_count` eski dosya tutulur.
  Böylece günlük dosyası diski sınırsız doldurmaz.
* Her analiz için saldırı sınıfı başına TEK satır yazılır (akış başına değil). 10.000 DDoS akışı
  10.000 satır değil, "DoS/DDoS adet=10000" diyen tek bir satır üretir; günlük okunabilir kalır.
* Seviyeler config.ALARM_LEVELS'tan gelir: DoS/DDoS, Botnet, Web Attack, Brute Force -> CRITICAL;
  PortScan -> WARNING (keşif aşaması, tek başına zarar vermez); Benign -> alarm yok.
* Alarm eşiği: bir sınıftan eşikten az akış bulunduysa seviye WARNING olur ve "düşük sayıda
  şüpheli akış, incelenmeli" diye işaretlenir. 10. haftadan beri eşik dosya boyutuyla ölçeklenir:
  max(config.ALARM_MIN_FLOWS, ceil(config.ALARM_RATES[sınıf] × analiz edilen akış)).
"""
import logging
import math
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


def alarm_threshold(sinif, n_rows, min_flows=config.ALARM_MIN_FLOWS, rates=None):
    """Bir sınıfın alarm eşiği: max(min_flows, ceil(oran × n_rows)).

    n_rows: dosyada analiz edilen akış sayısı. Oran yoksa (0) eşik sabit min_flows'tur.
    round(): 0.00003 × 100000 gibi çarpımlar kayan noktada 3.0000000000000004 çıkıp
    yukarı yuvarlanınca eşik 1 fazla olmasın diye.
    """
    rate = (config.ALARM_RATES if rates is None else rates).get(sinif, 0.0)
    return max(int(min_flows), math.ceil(round(rate * int(n_rows), 6)))


def alarm_level(sinif, adet, min_flows=config.ALARM_MIN_FLOWS):
    """(seviye, dusuk_sayi) döndürür; Benign/bilinmeyen sınıf ya da 0 akış için (None, False).

    Alarm eşiği: bir saldırı sınıfından `min_flows`'tan AZ akış bulunduysa alarm yükseltilmez,
    WARNING + "düşük sayıda şüpheli akış, incelenmeli" olarak işaretlenir. Tek tük yanlış
    tahminler (normal trafikte 1-2 akış) böylece KRİTİK alarm üretmez ama gizlenmez de.
    Tahminler değişmez; eşik yalnızca alarmın seviyesini belirler.
    """
    level = config.ALARM_LEVELS.get(sinif)
    if level is None or int(adet) <= 0:
        return None, False
    if int(adet) < int(min_flows):
        return "WARNING", True
    return level, False


def card_type(alarm):
    """Arayüzdeki kart: 'kritik' (kırmızı), 'uyari' (turuncu) veya 'incelenmeli' (gri/mavi)."""
    if alarm["seviye"] == "CRITICAL":
        return "kritik"
    return "incelenmeli" if alarm["dusuk_sayi"] else "uyari"


def raise_alarms(class_summary, file_name, analiz_id=None, conn=None, logger=None,
                 min_flows=config.ALARM_MIN_FLOWS, rates=None):
    """Sınıf özetinden alarm üretir; günlüğe ve (conn verilirse) veritabanına yazar.

    class_summary: sinif, adet, ortalama_guven sütunlu DataFrame (AnalysisResult.class_summary).
    min_flows: N_min. rates: sınıf -> oran (None ise config.ALARM_RATES; {} = sabit eşik).
    Sınıfın eşiği = max(min_flows, ceil(oran × n)); n = özetteki toplam akış (analiz edilen).
    Dönüş: üretilen alarmların listesi (sözlük).
    """
    n_rows = int(class_summary["adet"].sum())
    alarms = []
    for row in class_summary.itertuples(index=False):
        esik = alarm_threshold(row.sinif, n_rows, min_flows, rates)
        level, low = alarm_level(row.sinif, row.adet, esik)
        if level is None:                                 # Benign veya bilinmeyen sınıf
            continue
        alarm = {"sinif": row.sinif, "adet": int(row.adet), "seviye": level,
                 "ortalama_guven": float(row.ortalama_guven), "dusuk_sayi": low,
                 "esik": esik}
        if logger is not None:
            # incelenmeli satırı 9. haftadaki biçimde; normal satırın sonuna yalnızca esik=X
            note = f" dusuk_sayi(esik={esik}) incelenmeli" if low else f" esik={esik}"
            logger.log(LEVELS[level], f"analiz_id={analiz_id} dosya={file_name} "
                                      f"sinif={row.sinif} adet={int(row.adet)} "
                                      f"ort_guven={float(row.ortalama_guven):.3f}{note}")
        if conn is not None and analiz_id is not None:
            alarm["id"] = database.save_alarm(conn, analiz_id, row.sinif, row.adet, level,
                                              dusuk_sayi=low, esik=esik)
        alarms.append(alarm)
    # Sıra: önce CRITICAL, sonra normal WARNING (PortScan), en sonda düşük sayılı uyarılar;
    # her grupta en çok akıştan aza. Arayüzde en önemli alarm en üstte görünür.
    alarms.sort(key=lambda a: (a["seviye"] != "CRITICAL", a["dusuk_sayi"], -a["adet"]))
    return alarms
