"""8. hafta ek deneyleri (eşik ayarı, rapor ekleme) için testler."""
import numpy as np
import pytest

from experiments import run_experiments, run_followup
from experiments.run_followup import append_report, predict_with_threshold, sweep_threshold
from tests.make_synthetic import make

NAMES = ["Benign", "PortScan", "Botnet"]
PROBA = np.array([[0.70, 0.10, 0.20],    # Benign, Botnet 0,20
                  [0.40, 0.05, 0.55],    # argmax Botnet
                  [0.30, 0.45, 0.25],    # argmax PortScan, Botnet 0,25
                  [0.10, 0.10, 0.80]])


def test_predict_with_threshold():
    assert predict_with_threshold(PROBA, 2, None).tolist() == [0, 2, 1, 2]
    # düşük eşik: Botnet olasılığı 0,20 ve 0,25 olanlar da Botnet olur
    assert predict_with_threshold(PROBA, 2, 0.2).tolist() == [2, 2, 2, 2]
    # yüksek eşik: 0,55 Botnet olmaktan çıkar, kalanlardan en olası (Benign) seçilir
    assert predict_with_threshold(PROBA, 2, 0.6).tolist() == [0, 0, 1, 2]


def test_sweep_threshold_picks_best_botnet_f1_middle_of_ties():
    y = np.array([0, 0, 1, 2])
    t, curve = sweep_threshold(y, PROBA, np.array([0, 1, 2]), 2, NAMES)
    # 0,56–0,80 arasındaki her eşik tek doğru Botnet'i (0,80) ayırır -> F1=1; ortadaki seçilir
    best = curve.loc[np.isclose(curve["f1_Botnet"], 1.0), "esik"]
    assert best.min() == pytest.approx(0.56) and best.max() == pytest.approx(0.80)
    assert t == pytest.approx(0.68)
    assert len(curve) == len(run_followup.THRESHOLDS)


def test_sweep_uses_model_class_order():
    # model.classes_ sırası sınıf indeksinden farklıysa da doğru sütun kullanılmalı
    y = np.array([0, 0, 1, 2])
    t1, _ = sweep_threshold(y, PROBA, np.array([0, 1, 2]), 2, NAMES)
    t2, _ = sweep_threshold(y, PROBA[:, [2, 0, 1]], np.array([2, 0, 1]), 2, NAMES)
    assert t1 == t2


def test_append_report_replaces_old_section(tmp_path):
    md = tmp_path / "r.md"
    md.write_text("# Ana rapor\n", encoding="utf-8")
    append_report(md, run_followup.MARKER + "\nilk")
    append_report(md, run_followup.MARKER + "\nikinci")
    text = md.read_text(encoding="utf-8")
    assert text.startswith("# Ana rapor") and "ikinci" in text and "ilk" not in text
    assert text.count(run_followup.MARKER) == 1


def test_followup_smoke(tmp_path):
    data = make(tmp_path / "veri")
    out = tmp_path / "cikti"
    run_experiments.main(["--data", str(data), "--out", str(out), "--n-iter", "2",
                          "--cv-sample", "3000"])
    R = run_followup.main(["--data", str(data), "--out", str(out)])
    for f in ["ek1_oznitelik.csv", "ek2_adaylar.csv", "ek2_esik_tarama.csv", "ek_final_test.csv",
              "ek_final_karsilastirma.csv", "hata_matrisi_ek_final.png", "ek_sonuclar.json"]:
        assert (out / f).exists(), f
    assert len(R["ek1"]) == 2 and len(R["ek2"]) == 4
    assert R["secim"]["aday"] in {r["aday"] for r in R["ek2"]}
    text = (out / "rapor_tablolari_hafta8.md").read_text(encoding="utf-8")
    assert "## Deney 1" in text and "## Ek 2" in text
