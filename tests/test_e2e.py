"""Uçtan uca testler (10. hafta): CSV -> inference -> SQLite -> security.log -> alarm kartları,
hatalı girdilerde çökmeme ve Streamlit arayüzü duman testi (AppTest).

Hepsi testlerin küçük sahte modeliyle (conftest.py) ve geçici veritabanı / log klasörüyle
çalışır; data/analizler.db ve logs/security.log'a yazılmaz.
"""
import io
import zipfile

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src import config, database
from src.alarm import card_type, get_security_logger
from src.inference import InferenceError, Predictor
from src.service import run_analysis
from tests.conftest import FEATURES, make_flows

ROOT = config.ROOT


@pytest.fixture
def env(artifacts_dir, tmp_path):
    """Geçici veritabanı ve log; test bitince log dosyası kapatılır."""
    logger = get_security_logger(tmp_path / "logs")
    yield {"predictor": Predictor(artifacts_dir), "db": tmp_path / "e2e.db", "logger": logger,
           "log": tmp_path / "logs" / "security.log", "tmp": tmp_path}
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)


def _log_lines(env):
    return env["log"].read_text(encoding="utf-8").splitlines() if env["log"].exists() else []


def test_full_flow_csv_to_db_log_and_cards(env):
    path = env["tmp"] / "karma.csv"
    make_flows(n_per_class=20, seed=11).to_csv(path, index=False)      # 6 sınıf × 20 akış
    res, aid, alarms = run_analysis(env["predictor"], path, "karma.csv", env["db"], env["logger"])

    conn = database.connect(env["db"])
    analyses = database.list_analyses(conn)
    assert analyses["id"].tolist() == [aid]
    assert analyses.loc[0, "toplam_satir"] == 120 and analyses.loc[0, "atlanan_satir"] == 0
    summary = database.class_summaries(conn, aid).set_index("sinif")["adet"]
    assert summary.sum() == res.analyzed_rows == 120
    assert summary.to_dict() == res.class_summary.set_index("sinif")["adet"].to_dict()
    db_alarms = database.list_alarms(conn, aid).set_index("sinif")
    conn.close()

    # 120 akışta oranlı eşikler N_min'in altında kalır -> her sınıfın eşiği 9
    assert set(db_alarms.index) == {a["sinif"] for a in alarms} == set(config.ALARM_LEVELS)
    assert (db_alarms["esik"] == 9).all() and (db_alarms["dusuk_sayi"] == 0).all()
    cards = {a["sinif"]: card_type(a) for a in alarms}
    assert cards == {"DoS/DDoS": "kritik", "Brute Force": "kritik", "Web Attack": "kritik",
                     "Botnet": "kritik", "PortScan": "uyari"}

    lines = _log_lines(env)
    assert len(lines) == 5                                    # sınıf başına tek satır
    assert sum("| CRITICAL |" in l for l in lines) == 4
    assert all(f"analiz_id={aid} dosya=karma.csv" in l and l.endswith(" esik=9") for l in lines)


def test_few_attack_flows_give_review_card(env):
    df = make_flows(n_per_class=30, seed=12)
    df = pd.concat([df[df["Label"] == "BENIGN"], df[df["Label"] == "Bot"].head(3)])
    res, aid, alarms = run_analysis(env["predictor"], df.to_csv(index=False).encode(),
                                    "az.csv", env["db"], env["logger"])
    assert [(a["sinif"], card_type(a)) for a in alarms] == [("Botnet", "incelenmeli")]
    (line,) = _log_lines(env)
    assert "| WARNING |" in line and "sinif=Botnet adet=3" in line
    assert line.endswith("dusuk_sayi(esik=9) incelenmeli")     # 9. haftadaki biçim
    conn = database.connect(env["db"])
    row = database.list_alarms(conn, aid).iloc[0]
    conn.close()
    assert row["seviye"] == "WARNING" and row["dusuk_sayi"] == 1 and row["esik"] == 9


def _zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.csv", make_flows(3).to_csv(index=False))
    return buf.getvalue()


BAD_INPUTS = {
    "bos": b"",
    "yalnizca_baslik": (",".join(FEATURES) + ",Label\n").encode(),
    "eksik_sutun": make_flows(3).drop(columns=FEATURES[:2]).to_csv(index=False).encode(),
    "hepsi_bozuk": pd.DataFrame({f: ["x", "nan", "inf"] for f in FEATURES}).to_csv(
        index=False).encode(),
    "csv_degil_zip": _zip(),
    "csv_degil_metin": "Merhaba, bu bir rapor.\nİkinci satır.\n".encode(),
    "noktali_virgul": make_flows(3).to_csv(index=False, sep=";").encode(),
}


@pytest.mark.parametrize("name", BAD_INPUTS)
def test_bad_input_turkish_error_and_nothing_written(env, name):
    with pytest.raises(InferenceError) as e:
        run_analysis(env["predictor"], BAD_INPUTS[name], f"{name}.csv", env["db"], env["logger"])
    msg = str(e.value)
    assert msg and any(ch in msg for ch in "ıİşŞğĞüÜöÖçÇ")    # Türkçe mesaj
    assert "Traceback" not in msg and "Error tokenizing" not in msg
    conn = database.connect(env["db"])
    assert database.list_analyses(conn).empty and database.list_alarms(conn).empty
    conn.close()
    assert _log_lines(env) == []


def test_partially_bad_values_are_analyzed(env):
    df = make_flows(n_per_class=10, seed=13).reset_index(drop=True).astype(
        {f: object for f in FEATURES[:3]})
    df.loc[0, FEATURES[0]], df.loc[1, FEATURES[1]], df.loc[2, FEATURES[2]] = "abc", "inf", None
    df.columns = [f"  {c} " for c in df.columns]               # baştaki/sondaki boşluk
    res, aid, _ = run_analysis(env["predictor"], df.to_csv(index=False).encode(), "kismi.csv",
                               env["db"], env["logger"])
    assert res.skipped_rows == 3 and res.analyzed_rows == 57
    conn = database.connect(env["db"])
    assert database.list_analyses(conn).loc[0, "atlanan_satir"] == 3
    conn.close()


# ------------------------------------------------------------------ Streamlit duman testi
@pytest.fixture
def app_env(artifacts_dir, tmp_path, monkeypatch):
    """Uygulamayı sahte model + geçici veritabanı / log klasörüyle çalıştırır."""
    monkeypatch.setattr(config, "ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    st.cache_resource.clear()                 # önceki testin modeli/logger'ı kullanılmasın
    yield tmp_path
    st.cache_resource.clear()
    logger = get_security_logger(tmp_path / "logs")
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)


def test_app_smoke_page_opens_and_analyzes(app_env):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert at.title[0].value == "Ağ Trafiği Analizi"
    assert at.sidebar.number_input[0].value == config.ALARM_MIN_FLOWS

    csv = make_flows(n_per_class=20, seed=14).to_csv(index=False).encode()
    at.file_uploader[0].set_value(("demo_karma.csv", csv, "text/csv"))
    at.run()
    at.button[0].click()
    at.run()
    assert not at.exception
    errors = [e.value for e in at.error]                       # kırmızı KRİTİK kartları
    assert len(errors) == 4 and all(e.startswith("KRİTİK SALDIRI") for e in errors)
    assert any("Port taraması" in m.value for m in at.markdown)  # turuncu UYARI kartı
    assert any("Alarm eşikleri (bu dosya, 120 akış)" in c.value for c in at.caption)
    conn = database.connect(app_env / "app.db")                # geçici veritabanına yazıldı
    assert len(database.list_analyses(conn)) == 1
    conn.close()
    assert (app_env / "logs" / "security.log").exists()


def test_app_bad_file_shows_warning_not_crash(app_env):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.file_uploader[0].set_value(("rapor.csv", _zip(), "text/csv"))
    at.run()
    at.button[0].click()
    at.run()
    assert not at.exception and not at.error
    assert len(at.warning) == 1 and "CSV metin dosyası değil" in at.warning[0].value
