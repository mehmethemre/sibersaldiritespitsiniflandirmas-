"""src/alarm.py testleri: sınıf başına tek satır, doğru seviyeler, veritabanı kaydı, döndürme."""
import logging

import pandas as pd

from src import database
from src.alarm import get_security_logger, raise_alarms

SUMMARY = pd.DataFrame({
    "sinif": ["Benign", "DoS/DDoS", "PortScan", "Botnet"],
    "adet": [5000, 1200, 40, 3],
    "ortalama_guven": [0.99, 0.97, 0.9, 0.55],
})


def _close(logger):
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)


def test_one_line_per_attack_class_with_levels(tmp_path):
    logger = get_security_logger(tmp_path)
    # eşiksiz (N=1): sınıf bazındaki seviye kuralı sınanır
    alarms = raise_alarms(SUMMARY, "demo.csv", analiz_id=7, logger=logger, min_flows=1)
    _close(logger)
    lines = (tmp_path / "security.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3                              # Benign alarm üretmez
    assert sum("| CRITICAL |" in l for l in lines) == 2
    assert sum("| WARNING |" in l and "sinif=PortScan" in l for l in lines) == 1
    assert all("analiz_id=7" in l and "dosya=demo.csv" in l for l in lines)
    assert any("sinif=DoS/DDoS adet=1200" in l for l in lines)
    # sıralama: önce CRITICAL (çok akıştan aza), en sonda WARNING
    assert [a["sinif"] for a in alarms] == ["DoS/DDoS", "Botnet", "PortScan"]


def test_no_alarm_for_benign_only(tmp_path):
    logger = get_security_logger(tmp_path)
    assert raise_alarms(SUMMARY.iloc[:1], "normal.csv", logger=logger) == []
    _close(logger)
    assert (tmp_path / "security.log").read_text(encoding="utf-8") == ""


def test_alarms_saved_to_database():
    conn = database.connect(":memory:")
    aid = database.save_analysis(conn, "demo.csv", 6243, 0, 1.0, "v1")
    alarms = raise_alarms(SUMMARY, "demo.csv", aid, conn)
    rows = database.list_alarms(conn, aid)
    assert len(rows) == 3 and all("id" in a for a in alarms)
    assert set(rows["seviye"]) == {"CRITICAL", "WARNING"}
    conn.close()


def test_logger_is_not_duplicated(tmp_path):
    a = get_security_logger(tmp_path)
    b = get_security_logger(tmp_path)
    assert a is b and len(a.handlers) == 1
    assert a.level == logging.WARNING and a.propagate is False
    _close(a)


def test_log_rotation(tmp_path):
    logger = get_security_logger(tmp_path, max_bytes=300, backup_count=2)
    for i in range(20):
        raise_alarms(SUMMARY, f"dosya_{i}.csv", i, logger=logger)
    _close(logger)
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["security.log", "security.log.1", "security.log.2"]


# ---------------------------------------------------------------- alarm eşiği
from src.alarm import alarm_level  # noqa: E402


def test_alarm_level_threshold():
    assert alarm_level("Benign", 500, 5) == (None, False)
    assert alarm_level("Botnet", 0, 5) == (None, False)
    assert alarm_level("Botnet", 4, 5) == ("WARNING", True)       # eşik altı -> incelenmeli
    assert alarm_level("Botnet", 5, 5) == ("CRITICAL", False)     # eşik dahil
    assert alarm_level("PortScan", 2, 5) == ("WARNING", True)
    assert alarm_level("PortScan", 50, 5) == ("WARNING", False)
    assert alarm_level("DoS/DDoS", 1, 1) == ("CRITICAL", False)   # N=1: eski davranış


def test_threshold_downgrades_but_never_hides(tmp_path):
    logger = get_security_logger(tmp_path)
    conn = database.connect(":memory:")
    aid = database.save_analysis(conn, "demo.csv", 6243, 0, 1.0, "v1")
    alarms = raise_alarms(SUMMARY, "demo.csv", aid, conn, logger, min_flows=10)
    _close(logger)
    by = {a["sinif"]: a for a in alarms}
    assert set(by) == {"DoS/DDoS", "PortScan", "Botnet"}           # hiçbir tespit gizlenmedi
    assert by["DoS/DDoS"]["seviye"] == "CRITICAL" and not by["DoS/DDoS"]["dusuk_sayi"]
    assert by["Botnet"]["seviye"] == "WARNING" and by["Botnet"]["dusuk_sayi"]
    assert by["PortScan"]["dusuk_sayi"] is False                  # 40 >= 10
    assert [a["sinif"] for a in alarms] == ["DoS/DDoS", "PortScan", "Botnet"]
    lines = (tmp_path / "security.log").read_text(encoding="utf-8").splitlines()
    botnet = [l for l in lines if "sinif=Botnet" in l]
    assert len(botnet) == 1 and "| WARNING |" in botnet[0] and "incelenmeli" in botnet[0]
    rows = database.list_alarms(conn, aid).set_index("sinif")
    assert rows.loc["Botnet", "dusuk_sayi"] == 1 and rows.loc["Botnet", "esik"] == 10
    assert rows.loc["DoS/DDoS", "dusuk_sayi"] == 0
    assert database.list_analyses(conn).loc[0, "kritik_alarm"] == 1
    conn.close()
