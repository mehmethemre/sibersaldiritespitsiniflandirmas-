"""Analiz geçmişi için SQLite veritabanı (Python'un yerleşik sqlite3 modülü).

Tablolar:
  analizler       her CSV analizi için bir satır
  sinif_ozetleri  bir analizde her sınıftan kaç akış bulunduğu ve ortalama güven
  alarmlar        bir analizde üretilen alarmlar (saldırı sınıfı başına bir satır)

Neden böyle?
* Değerler SQL metnine asla birleştirilmez; hepsi `?` yer tutucusuyla parametre olarak verilir.
  Böylece dosya adındaki tırnak gibi karakterler SQL komutu olarak çalışamaz (SQL enjeksiyonu).
* SQLite'ta yabancı anahtar (FOREIGN KEY) denetimi varsayılan olarak KAPALIDIR; her bağlantıda
  `PRAGMA foreign_keys = ON` ile açılır. Böylece olmayan bir analize alarm eklenemez ve bir
  analiz silinince ona bağlı özetler/alarmlar da silinir (ON DELETE CASCADE).
* `with conn:` bloğu bir işlem (transaction) açar: blok hatasız biterse COMMIT, hata olursa
  ROLLBACK yapılır; yarım kalmış kayıt oluşmaz.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config

SCHEMA = """
-- Her analiz için bir satır. id otomatik artar; tarih ISO 8601 metni olarak tutulur.
CREATE TABLE IF NOT EXISTS analizler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dosya_adi     TEXT    NOT NULL,
    tarih         TEXT    NOT NULL,
    toplam_satir  INTEGER NOT NULL CHECK (toplam_satir >= 0),   -- dosyadaki veri satırı
    atlanan_satir INTEGER NOT NULL CHECK (atlanan_satir >= 0),  -- bozuk olduğu için atlanan
    sure_sn       REAL    NOT NULL CHECK (sure_sn >= 0),
    model_surumu  TEXT    NOT NULL
);

-- Bir analizdeki sınıf dağılımı. (analiz_id, sinif) çifti benzersizdir.
-- analiz_id, analizler.id'ye bağlıdır; analiz silinirse bu satırlar da silinir.
CREATE TABLE IF NOT EXISTS sinif_ozetleri (
    analiz_id      INTEGER NOT NULL REFERENCES analizler(id) ON DELETE CASCADE,
    sinif          TEXT    NOT NULL,
    adet           INTEGER NOT NULL CHECK (adet >= 0),
    ortalama_guven REAL,
    PRIMARY KEY (analiz_id, sinif)
);

-- Alarmlar: saldırı sınıfı başına tek satır. seviye yalnızca WARNING veya CRITICAL olabilir.
-- dusuk_sayi = 1: akış sayısı alarm eşiğinin (esik) altında kaldığı için WARNING'e düşürüldü.
CREATE TABLE IF NOT EXISTS alarmlar (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    analiz_id  INTEGER NOT NULL REFERENCES analizler(id) ON DELETE CASCADE,
    sinif      TEXT    NOT NULL,
    adet       INTEGER NOT NULL CHECK (adet > 0),
    seviye     TEXT    NOT NULL CHECK (seviye IN ('WARNING', 'CRITICAL')),
    zaman      TEXT    NOT NULL,
    dusuk_sayi INTEGER NOT NULL DEFAULT 0 CHECK (dusuk_sayi IN (0, 1)),
    esik       INTEGER
);

-- Bir analizin alarmlarını hızlı bulmak için dizin.
CREATE INDEX IF NOT EXISTS idx_alarmlar_analiz ON alarmlar(analiz_id);
"""


def _now():
    return datetime.now().isoformat(sep=" ", timespec="seconds")   # 2026-11-26 17:38:12


def connect(path=config.DB_PATH) -> sqlite3.Connection:
    """Veritabanına bağlanır, yabancı anahtarları açar, tablolar yoksa oluşturur.

    path=":memory:" -> yalnızca bellekte yaşayan geçici veritabanı (testler için).
    """
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row            # satırlara sütun adıyla erişim: row["sinif"]
    # Bu bağlantı için yabancı anahtar denetimini aç (SQLite'ta varsayılan kapalı)
    conn.execute("PRAGMA foreign_keys = ON")
    # Şemadaki tüm CREATE ... IF NOT EXISTS ifadelerini çalıştır (varsa dokunmaz)
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


# Sonradan eklenen sütunlar: (tablo, sütun, tanım). Eski bir veritabanı dosyasında tablo zaten
# var olduğu için CREATE TABLE IF NOT EXISTS yeni sütunları eklemez; bu adım ekler.
MIGRATIONS = [
    ("alarmlar", "dusuk_sayi", "INTEGER NOT NULL DEFAULT 0 CHECK (dusuk_sayi IN (0, 1))"),
    ("alarmlar", "esik", "INTEGER"),
]


def _migrate(conn):
    for table, column, definition in MIGRATIONS:
        # PRAGMA table_info: tablonun sütunlarını listeler (satır başına bir sütun, ad 'name')
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            with conn:
                # Eksik sütunu ekler; eski satırlara DEFAULT değeri (veya NULL) yazılır.
                # Tablo/sütun adları yukarıdaki sabit listeden gelir, kullanıcı girdisi değildir;
                # SQL'de ad (identifier) parametre olarak verilemediği için metne yazılır.
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def save_analysis(conn, dosya_adi, toplam_satir, atlanan_satir, sure_sn, model_surumu,
                  tarih=None) -> int:
    """Yeni analiz satırı ekler, oluşan id'yi döndürür."""
    with conn:
        # Yeni analiz kaydı; id'yi SQLite verir (AUTOINCREMENT)
        cur = conn.execute(
            "INSERT INTO analizler (dosya_adi, tarih, toplam_satir, atlanan_satir, sure_sn, "
            "model_surumu) VALUES (?, ?, ?, ?, ?, ?)",
            (str(dosya_adi), tarih or _now(), int(toplam_satir), int(atlanan_satir),
             float(sure_sn), str(model_surumu)))
    return int(cur.lastrowid)


def save_class_summaries(conn, analiz_id, rows):
    """rows: (sinif, adet, ortalama_guven) üçlüleri veya bu sütunlara sahip DataFrame."""
    if isinstance(rows, pd.DataFrame):
        rows = rows[["sinif", "adet", "ortalama_guven"]].itertuples(index=False, name=None)
    data = [(int(analiz_id), str(s), int(a), None if pd.isna(g) else float(g))
            for s, a, g in rows]
    with conn:
        # Her sınıf için bir satır; executemany aynı ifadeyi her üçlü için çalıştırır
        conn.executemany(
            "INSERT INTO sinif_ozetleri (analiz_id, sinif, adet, ortalama_guven) "
            "VALUES (?, ?, ?, ?)", data)


def save_alarm(conn, analiz_id, sinif, adet, seviye, zaman=None, dusuk_sayi=False,
               esik=None) -> int:
    with conn:
        # Alarm kaydı; analiz_id geçerli bir analize işaret etmiyorsa FOREIGN KEY hata verir
        cur = conn.execute(
            "INSERT INTO alarmlar (analiz_id, sinif, adet, seviye, zaman, dusuk_sayi, esik) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(analiz_id), str(sinif), int(adet), str(seviye), zaman or _now(),
             int(bool(dusuk_sayi)), None if esik is None else int(esik)))
    return int(cur.lastrowid)


def delete_analysis(conn, analiz_id):
    with conn:
        # Analizi siler; CASCADE sayesinde özetleri ve alarmları da silinir
        conn.execute("DELETE FROM analizler WHERE id = ?", (int(analiz_id),))


def list_analyses(conn, limit=200) -> pd.DataFrame:
    """Son analizler (yeniden eskiye), her birinin alarm ve saldırı akışı sayısıyla."""
    # LEFT JOIN yerine alt sorgular: alarmı olmayan analizler de 0 ile listelenir
    sql = """
        SELECT a.id, a.dosya_adi, a.tarih, a.toplam_satir, a.atlanan_satir, a.sure_sn,
               a.model_surumu,
               (SELECT COUNT(*) FROM alarmlar al
                 WHERE al.analiz_id = a.id AND al.seviye = 'CRITICAL') AS kritik_alarm,
               (SELECT COUNT(*) FROM alarmlar al WHERE al.analiz_id = a.id) AS alarm_sayisi,
               (SELECT COALESCE(SUM(s.adet), 0) FROM sinif_ozetleri s
                 WHERE s.analiz_id = a.id AND s.sinif <> 'Benign') AS saldiri_akisi
        FROM analizler a
        ORDER BY a.id DESC
        LIMIT ?
    """
    return pd.read_sql_query(sql, conn, params=(int(limit),))


def list_alarms(conn, analiz_id=None, limit=500) -> pd.DataFrame:
    """Alarmlar, ait oldukları dosya adıyla birlikte (isteğe bağlı olarak tek analiz için)."""
    # JOIN: her alarmın hangi dosyanın analizinden geldiğini göstermek için
    sql = """
        SELECT al.id, al.analiz_id, a.dosya_adi, al.sinif, al.adet, al.seviye,
               al.dusuk_sayi, al.esik, al.zaman
        FROM alarmlar al JOIN analizler a ON a.id = al.analiz_id
        WHERE (? IS NULL OR al.analiz_id = ?)
        ORDER BY al.id DESC
        LIMIT ?
    """
    aid = None if analiz_id is None else int(analiz_id)
    return pd.read_sql_query(sql, conn, params=(aid, aid, int(limit)))


def class_summaries(conn, analiz_id) -> pd.DataFrame:
    # Tek bir analizin sınıf dağılımı, en çok akıştan en aza
    return pd.read_sql_query(
        "SELECT sinif, adet, ortalama_guven FROM sinif_ozetleri WHERE analiz_id = ? "
        "ORDER BY adet DESC", conn, params=(int(analiz_id),))
