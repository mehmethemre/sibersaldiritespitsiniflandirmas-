"""src/database.py testleri (bellekteki SQLite ile; diske dosya yazılmaz)."""
import sqlite3

import pandas as pd
import pytest

from src import database


@pytest.fixture
def conn():
    c = database.connect(":memory:")
    yield c
    c.close()


def test_tables_and_foreign_keys_enabled(conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"analizler", "sinif_ozetleri", "alarmlar"} <= names
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_save_and_list(conn):
    aid = database.save_analysis(conn, "demo.csv", 100, 3, 0.5, "v1")
    database.save_class_summaries(conn, aid, pd.DataFrame(
        {"sinif": ["Benign", "Botnet"], "adet": [90, 7], "ortalama_guven": [0.99, 0.6]}))
    database.save_alarm(conn, aid, "Botnet", 7, "CRITICAL")
    a = database.list_analyses(conn)
    assert a.loc[0, "dosya_adi"] == "demo.csv" and a.loc[0, "alarm_sayisi"] == 1
    assert a.loc[0, "saldiri_akisi"] == 7
    al = database.list_alarms(conn)
    assert al.loc[0, "seviye"] == "CRITICAL" and al.loc[0, "dosya_adi"] == "demo.csv"
    assert database.class_summaries(conn, aid)["sinif"].tolist() == ["Benign", "Botnet"]


def test_foreign_key_rejects_unknown_analysis(conn):
    with pytest.raises(sqlite3.IntegrityError):
        database.save_alarm(conn, 999, "Botnet", 1, "CRITICAL")


def test_cascade_delete(conn):
    aid = database.save_analysis(conn, "x.csv", 1, 0, 0.1, "v1")
    database.save_class_summaries(conn, aid, [("Botnet", 1, 0.5)])
    database.save_alarm(conn, aid, "Botnet", 1, "CRITICAL")
    database.delete_analysis(conn, aid)
    assert conn.execute("SELECT COUNT(*) FROM alarmlar").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sinif_ozetleri").fetchone()[0] == 0


def test_check_constraints(conn):
    aid = database.save_analysis(conn, "x.csv", 1, 0, 0.1, "v1")
    with pytest.raises(sqlite3.IntegrityError):
        database.save_alarm(conn, aid, "Botnet", 1, "INFO")        # geçersiz seviye
    with pytest.raises(sqlite3.IntegrityError):
        database.save_analysis(conn, "y.csv", -1, 0, 0.1, "v1")   # negatif satır


def test_parameters_are_not_executed_as_sql(conn):
    evil = "a.csv'); DROP TABLE analizler; --"
    aid = database.save_analysis(conn, evil, 1, 0, 0.1, "v1")
    assert database.list_analyses(conn).loc[0, "dosya_adi"] == evil
    assert database.list_alarms(conn, aid).empty


def test_file_database_persists(tmp_path):
    p = tmp_path / "alt" / "a.db"
    c = database.connect(p)
    database.save_analysis(c, "x.csv", 1, 0, 0.1, "v1")
    c.close()
    c = database.connect(p)
    assert len(database.list_analyses(c)) == 1
    c.close()
