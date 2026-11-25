"""analysis/dedup_by_class.py hesaplarını elle kurulmuş küçük bir tabloyla doğrular."""
import pandas as pd

from analysis.dedup_by_class import PORT, dedup_by_class, label_conflicts


def _tablo():
    rows = [
        (80, 1, 1, "Benign"), (80, 1, 1, "Benign"),       # birebir tekrar
        (443, 1, 1, "PortScan"),                          # port hariç Benign ile çakışır
        (22, 2, 2, "PortScan"), (23, 2, 2, "PortScan"),   # yalnızca portla ayrışan tekrar
        (80, 3, 3, "Benign"), (80, 3, 3, "Botnet"),       # üç sınıflı çakışma grubu
        (81, 3, 3, "DoS/DDoS"),
        (1, 4, 4, "Web Attack"),                          # tekil
    ]
    return pd.DataFrame(rows, columns=[PORT, "f1", "f2", "Class"]).astype(
        {PORT: "float32", "f1": "float32", "f2": "float32"})


def test_dedup_by_class():
    out = dedup_by_class(_tablo())
    assert out.loc["Benign", "once"] == 3
    assert out.loc["Benign", "silinen_port_dahil"] == 1
    assert out.loc["Benign", "silinen_port_haric"] == 1
    assert out.loc["PortScan", "silinen_port_dahil"] == 0
    assert out.loc["PortScan", "silinen_port_haric"] == 1
    assert out.loc["TOPLAM", "once"] == 9
    assert out.loc["TOPLAM", "kalan_port_haric"] == 7


def test_label_conflicts():
    pairs, summary = label_conflicts(_tablo())
    p = {(r.sinif_A, r.sinif_B): r for r in pairs.itertuples()}
    assert set(p) == {("Benign", "PortScan"), ("Benign", "DoS/DDoS"),
                      ("Benign", "Botnet"), ("DoS/DDoS", "Botnet")}
    bp = p[("Benign", "PortScan")]
    assert (bp.grup_sayisi, bp.satir_tekrar_sonrasi, bp.satir_tekrar_oncesi,
            bp.satir_A, bp.satir_B) == (1, 2, 3, 2, 1)
    assert p[("DoS/DDoS", "Botnet")].satir_tekrar_oncesi == 2
    assert summary == {"cakisan_grup": 2, "satir_tekrar_sonrasi": 5,
                       "satir_tekrar_oncesi": 6, "grup_sinif_sayisi_dagilimi": {2: 1, 3: 1}}
