"""Bir CSV analizinin tüm adımlarını bir araya getirir: tahmin -> veritabanı -> alarm.

Arayüz (app.py) yalnızca bu fonksiyonu çağırır; böylece aynı akış Streamlit olmadan da
(testlerde, betiklerde) çalıştırılabilir ve sınanabilir.
"""
from . import config, database
from .alarm import raise_alarms


def run_analysis(predictor, source, file_name, db_path=config.DB_PATH, logger=None):
    """Dönüş: (AnalysisResult, analiz_id, alarm listesi).

    Tahmin başarısız olursa (InferenceError) veritabanına hiçbir şey yazılmaz.
    """
    result = predictor.analyze(source)
    conn = database.connect(db_path)
    try:
        analiz_id = database.save_analysis(conn, file_name, result.total_rows,
                                           result.skipped_rows, result.duration_s,
                                           result.model_version)
        database.save_class_summaries(conn, analiz_id, result.class_summary)
        alarms = raise_alarms(result.class_summary, file_name, analiz_id, conn, logger)
    finally:
        conn.close()
    return result, analiz_id, alarms
