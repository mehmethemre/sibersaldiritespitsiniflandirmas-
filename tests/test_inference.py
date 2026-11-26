"""src/inference.py ve src/service.py testleri: geçerli dosya, eksik sütun, bozuk değerler,
boş dosya, Label ile karşılaştırma ve Botnet eşiğinin eğitimdekiyle aynı uygulanması."""
import io

import numpy as np
import pandas as pd
import pytest

from src import database
from src.alarm import get_security_logger
from src.evaluate import predict_with_threshold
from src.inference import InferenceError, MissingColumnsError, Predictor
from src.service import run_analysis
from tests.conftest import FEATURES, make_flows


@pytest.fixture(scope="module")
def predictor(artifacts_dir):
    return Predictor(artifacts_dir)


def to_bytes(df):
    return df.to_csv(index=False).encode("utf-8")


def test_valid_file_with_label(predictor):
    df = make_flows(n_per_class=20, seed=1)
    res = predictor.analyze(to_bytes(df))
    assert res.total_rows == len(df) and res.skipped_rows == 0
    assert res.analyzed_rows == len(df)
    assert set(res.predictions.columns) >= {"satir_no", "tahmin", "guven", "gercek"}
    assert res.predictions["guven"].between(0, 1).all()
    assert res.class_summary["adet"].sum() == len(df)
    ev = res.evaluation
    assert ev["karsilastirilan"] == len(df) and ev["accuracy"] > 0.95
    assert list(ev["hata_matrisi"].index) == list(ev["rapor"]["sinif"])


def test_columns_are_stripped_and_case_insensitive(predictor):
    df = make_flows(n_per_class=5, seed=2).drop(columns="Label")
    df.columns = ["  " + c.upper() + " " for c in df.columns]   # " FLOW DURATION "
    res = predictor.analyze(to_bytes(df))
    assert res.analyzed_rows == len(df) and res.evaluation is None


def test_missing_columns_named_in_error(predictor):
    df = make_flows(n_per_class=5).drop(columns=["Flow IAT Mean", "Total Fwd Packets"])
    with pytest.raises(MissingColumnsError) as e:
        predictor.analyze(to_bytes(df))
    assert set(e.value.missing) == {"Flow IAT Mean", "Total Fwd Packets"}
    assert "Flow IAT Mean" in str(e.value) and "eksik" in str(e.value)


def test_bad_values_are_skipped_and_counted(predictor):
    df = make_flows(n_per_class=10, seed=3).reset_index(drop=True).astype({FEATURES[0]: object})
    df.loc[0, FEATURES[0]] = "abc"           # sayı değil
    df.loc[1, FEATURES[1]] = np.inf          # sonsuz
    df.loc[2, FEATURES[2]] = np.nan          # boş hücre
    df.loc[3, FEATURES[3]] = 1e300           # float32'ye sığmaz -> inf
    res = predictor.analyze(to_bytes(df))
    assert res.skipped_rows == 4 and res.analyzed_rows == len(df) - 4
    assert set(res.predictions["satir_no"]).isdisjoint({1, 2, 3, 4})
    r = res.skipped_reasons
    assert r["sayıya çevrilemeyen değer"] == 1 and r["boş hücre"] == 1
    assert r["sonsuz (Inf) veya aşırı büyük değer"] == 2


@pytest.mark.parametrize("content, message", [
    (b"", "boş"),
    (b"   \n  \n", "boş"),
    (",".join(FEATURES).encode() + b"\n", "veri satırı yok"),
    (b"bu bir csv degil\nsadece metin\n", "eksik"),
])
def test_empty_or_invalid_files_raise_clear_error(predictor, content, message):
    with pytest.raises(InferenceError, match=message):
        predictor.analyze(content)


def test_all_rows_invalid(predictor):
    df = pd.DataFrame({f: ["x", "y"] for f in FEATURES})
    with pytest.raises(InferenceError, match="hiçbiri"):
        predictor.analyze(to_bytes(df))


def test_file_like_and_path_inputs(predictor, tmp_path):
    df = make_flows(n_per_class=3)
    p = tmp_path / "a.csv"
    df.to_csv(p, index=False)
    assert predictor.analyze(p).analyzed_rows == len(df)
    assert predictor.analyze(io.BytesIO(to_bytes(df))).analyzed_rows == len(df)


def test_botnet_threshold_matches_training_rule(predictor):
    df = make_flows(n_per_class=10, seed=4)
    res = predictor.analyze(to_bytes(df))
    X = predictor.scaler.transform(df[FEATURES].to_numpy(np.float32))
    proba = predictor.model.predict_proba(X)
    col = list(predictor.model.classes_).index(predictor.class_names.index("Botnet"))
    expected = np.asarray(predictor.class_names)[
        predictor.model.classes_[predict_with_threshold(proba, col, 0.30)]]
    assert (res.predictions["tahmin"].to_numpy() == expected).all()


def test_macro_f1_uses_classes_present_in_file(predictor):
    df = make_flows(n_per_class=10, seed=6)
    df = df[df["Label"] == "BENIGN"].copy()
    df.loc[df.index[0], FEATURES] = 8.0                 # bu satır PortScan gibi görünür
    ev = predictor.analyze(to_bytes(df)).evaluation
    assert len(ev["rapor"]) == 2                        # Benign + yanlış tahmin edilen sınıf
    assert ev["macro_f1_siniflari"] == ["Benign"]
    assert ev["macro_f1"] == pytest.approx(
        ev["rapor"].set_index("sinif").loc["Benign", "f1"])


def test_out_of_scope_labels_excluded_from_comparison(predictor):
    df = make_flows(n_per_class=5, seed=5).reset_index(drop=True)
    df.loc[:2, "Label"] = "Infiltration"
    ev = predictor.analyze(to_bytes(df)).evaluation
    assert ev["kapsam_disi_etiket"] == 3 and ev["karsilastirilan"] == len(df) - 3


def test_missing_model_gives_clear_error(tmp_path):
    with pytest.raises(InferenceError, match="run_pipeline"):
        Predictor(tmp_path)


def test_run_analysis_writes_db_and_alarms(predictor, tmp_path):
    db = tmp_path / "a.db"
    logger = get_security_logger(tmp_path / "logs")
    res, aid, alarms = run_analysis(predictor, to_bytes(make_flows(10)), "demo.csv", db, logger)
    conn = database.connect(db)
    assert database.list_analyses(conn).loc[0, "id"] == aid
    assert database.class_summaries(conn, aid)["adet"].sum() == res.analyzed_rows
    assert len(database.list_alarms(conn, aid)) == len(alarms) == 5   # 5 saldırı sınıfı
    conn.close()
    with pytest.raises(InferenceError):                # bozuk dosya -> kayıt yok
        run_analysis(predictor, b"", "bos.csv", db, logger)
    conn = database.connect(db)
    assert len(database.list_analyses(conn)) == 1
    conn.close()
