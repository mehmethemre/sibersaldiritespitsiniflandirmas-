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
from tests.conftest import FEATURES, RAW_LABELS, make_flows

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
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")  # Model Hakkında: boş
    monkeypatch.setattr(config, "DEMO_DIR", tmp_path / "demo")        # boş durum: demo tablosu yok
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


# ------------------------------------------------------------------ 11. hafta arayüz eklemeleri
def _analyze(at, name="demo_karma.csv", seed=14):
    csv = make_flows(n_per_class=20, seed=seed).to_csv(index=False).encode()
    at.file_uploader[0].set_value((name, csv, "text/csv"))
    at.run()
    at.button[0].click()
    at.run()
    assert not at.exception


def test_app_threshold_explainer_table(app_env):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    _analyze(at)
    exp = [e for e in at.expander if e.label == "Alarm seviyeleri nasıl belirlenir?"]
    assert len(exp) == 1
    assert any("eşik = max(9, ⌈oran × n⌉)" in m.value for m in exp[0].markdown)
    table = exp[0].dataframe[0].value
    assert list(table["Sınıf"]) == [c for c in config.CLASS_ORDER if c in config.ALARM_LEVELS]
    row = table.set_index("Sınıf")
    assert row.loc["DoS/DDoS", "Oran"] == "0,00044"
    assert row.loc["Brute Force", "Oran"] == "0 (oran yok)"
    assert row.loc["DoS/DDoS", "Eşik"] == 9                    # 120 akış: max(9, ⌈0,053⌉)
    assert row.loc["PortScan", "Sonuç"] == "UYARI"
    assert row.loc["Botnet", "Sonuç"] == "KRİTİK alarm"


def test_app_confusion_heatmap_shown_for_labeled_file(app_env):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    _analyze(at)
    # sınıf dağılımı + hata matrisi ısı haritası = 2 grafik; ham hata matrisi tablosu yok
    assert len(at.get("vega_lite_chart")) == 2
    assert any("renk: gerçek sınıfın yüzde" in m.value for m in at.markdown)


def test_app_about_page_without_reports_shows_info(app_env):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value("Model Hakkında").run()
    assert not at.exception and not at.error
    assert at.title[0].value == "Model Hakkında"
    infos = [i.value for i in at.info]
    assert any("metrics.json" in i for i in infos) and any("onem_tablosu.csv" in i for i in infos)


def test_app_about_page_reads_report_files(app_env):
    import json
    rep = app_env / "reports"
    (rep / "hafta11").mkdir(parents=True)
    names = list(config.CLASS_ORDER)
    per = {c: {"precision": 0.9, "recall": 0.8, "f1-score": 0.85, "support": 10.0} for c in names}
    metrics = {"model_surumu": "test-model", "zaman": "2026-11-28 12:00", "test_satir": 60,
               "sinif_adlari": names,
               "modeller": {"Random Forest": {
                   "accuracy": 0.95, "macro_f1": 0.85, "single_latency_median_ms": 4.5,
                   "per_class": per,
                   "confusion_matrix": [[10 if i == j else 0 for j in names] for i in names]}}}
    (rep / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    pd.DataFrame({"oznitelik": FEATURES, "impurity": 1.0, "perm_macro_f1": 0.5,
                  "perm_botnet_f1": 0.2}).to_csv(rep / "hafta11" / "onem_tablosu.csv", index=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value("Model Hakkında").run()
    assert not at.exception
    caps = " ".join(c.value for c in at.caption)
    assert "Küme: **test**" in caps and "Küme: **doğrulama**" in caps
    assert any("**Hata matrisi** (küme: test" in m.value for m in at.markdown)
    assert at.dataframe[0].value["Sınıf"].tolist() == names
    # sahte modelin sürümü farklı -> uyarı
    assert any("test-model" in w.value for w in at.warning)
    # yöntem değiştirilebilir, grafik ekseninde yöntem ve küme yazıyor
    method = [r for r in at.radio if r.label == "Yöntem"][0]
    method.set_value("Impurity (RF'nin kendi önemi)").run()
    assert not at.exception
    assert any("Botnet" in m.value and "F1" in m.value for m in at.markdown)  # bilinen sınırlar


def test_app_history_shows_one_date_format(app_env):
    conn = database.connect(app_env / "app.db")
    a = database.save_analysis(conn, "eski.csv", 10, 0, 0.1, "m", tarih="2026-11-26T17:38:12")
    database.save_alarm(conn, a, "DoS/DDoS", 10, "CRITICAL", zaman="2026-11-26T17:38:12", esik=9)
    database.save_analysis(conn, "yeni.csv", 10, 0, 0.1, "m", tarih="2026-11-26 18:04:29")
    raw = database.list_analyses(conn)["tarih"].tolist()
    conn.close()
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value("Geçmiş Analizler").run()
    assert not at.exception
    shown = sorted(at.dataframe[0].value["tarih"].tolist())
    assert shown == ["26.11.2026 17:38:12", "26.11.2026 18:04:29"]
    assert "2026-11-26T17:38:12" in raw                         # veritabanı değişmedi
    zaman = at.dataframe[-1].value["zaman"].tolist()           # tüm alarmlar tablosu
    assert zaman == ["26.11.2026 17:38:12"]


def test_app_alarm_summary_download_only_with_alarms(app_env):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    _analyze(at)
    labels = [b.proto.label for b in at.get("download_button")]
    assert "Alarm özetini indir (CSV)" in labels
    flows = make_flows(n_per_class=20, seed=3)
    # make_flows satırları karıştırır; ilk satırın etiketi değil, açıkça BENIGN seçilir
    benign = flows[flows["Label"] == RAW_LABELS["Benign"]]
    assert len(benign) == 20
    at2 = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at2.run()
    at2.file_uploader[0].set_value(("tek.csv", benign.to_csv(index=False).encode(), "text/csv"))
    at2.run()
    at2.button[0].click()
    at2.run()
    assert not at2.exception
    assert at2.success and "Saldırı tespit edilmedi" in at2.success[0].value
    labels = [b.proto.label for b in at2.get("download_button")]
    assert "Alarm özetini indir (CSV)" not in labels
    assert "Tüm tahminleri CSV olarak indir" in labels


def test_app_empty_state_guide_and_demo_table(app_env):
    import json
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert any("Nasıl kullanılır?" in i.value for i in at.info)
    assert not at.dataframe                                  # demo_icerik.json yok -> tablo yok
    assert "Botnet karar eşiği 0,30" in at.caption[0].value  # Türkçe ondalık

    (app_env / "demo").mkdir()
    (app_env / "demo" / "demo_icerik.json").write_text(json.dumps(
        {"demo_karma.csv": {"Benign": 2000, "Botnet": 200},
         "demo_bozuk.csv": {"satir": 500, "bozulan_satir": {"inf": 15}}}), encoding="utf-8")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    table = at.dataframe[0].value
    assert table["Dosya"].tolist() == ["demo_karma.csv", "demo_bozuk.csv"]
    assert table["İçerik (gerçek etiket)"].tolist() == ["Benign 2.000, Botnet 200", "500 satır"]
    assert "kırmızı" in table.loc[0, "Ne gösterir"]

    _analyze(at)                                             # sonuç gelince rehber kaybolur
    assert not any("Nasıl kullanılır?" in i.value for i in at.info)


def test_app_nmin_in_advanced_settings_and_note_when_changed(app_env):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    exp = [e for e in at.sidebar.expander if e.label == "Gelişmiş ayarlar"]
    assert len(exp) == 1 and exp[0].number_input[0].value == config.ALARM_MIN_FLOWS
    _analyze(at)
    assert not any("N_min =" in w.value for w in at.warning)  # varsayılan: not yok

    # eleman ağacı her çalıştırmada yenilenir; eski `exp` yerine güncel ağaçtan sorgulanır
    [e for e in at.sidebar.expander if e.label == "Gelişmiş ayarlar"][0].number_input[0]         .set_value(20)
    _analyze(at)
    notes = [w.value for w in at.warning if "N_min =" in w.value]
    assert len(notes) == 1 and "N_min = 20" in notes[0]
