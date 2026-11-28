"""Streamlit arayüzü: CSV yükle -> analiz et -> sonuçları ve alarmları gör.

Çalıştırma:  streamlit run app.py

Yapı:
* Model `st.cache_resource` ile BİR KEZ yüklenir. Streamlit betiği her tıklamada baştan
  çalıştırır; önbellek olmasa 30 MB'lık model her etkileşimde yeniden okunurdu.
* Asıl iş src/service.py::run_analysis'te (tahmin -> veritabanı -> alarm). Arayüz yalnızca
  sonucu gösterir; böylece aynı akış Streamlit olmadan da test edilebilir.
* Son analizin sonucu `st.session_state`'te tutulur: indirme düğmesine basmak betiği yeniden
  çalıştırır ve sonuç kaybolmasın diye bu gerekir.
* Kullanıcı kaynaklı her sorun InferenceError olarak gelir ve st.warning ile gösterilir;
  beklenmeyen hatalar da yakalanır, uygulama çökmez.
"""
import html
import json
import logging

import altair as alt
import pandas as pd
import streamlit as st

from src import config, database
from src.alarm import alarm_summary, alarm_threshold, card_type, get_security_logger
from src.inference import InferenceError, Predictor
from src.service import run_analysis

st.set_page_config(page_title="Siber Saldırı Sınıflandırma", page_icon="🛡️", layout="wide")


@st.cache_resource(show_spinner="Model yükleniyor...")
def load_predictor():
    # Yollar çağrı anında config'ten okunur (varsayılan argüman içe aktarmada sabitlenirdi);
    # böylece testler config'i geçici klasörlere çevirip gerçek dosyalara yazmadan çalışır.
    return Predictor(config.ARTIFACTS_DIR)


@st.cache_resource
def load_logger():
    return get_security_logger(config.LOG_DIR)


def pct(x):
    return f"%{x * 100:.2f}".replace(".", ",")


def tr_int(n):
    return f"{int(n):,}".replace(",", ".")


def threshold_text(min_flows, n_rows):
    """Bu dosyada uygulanan sınıf bazında eşikler: max(N_min, oran × n)."""
    parts = []
    for c in config.CLASS_ORDER:
        if c in config.ALARM_LEVELS:
            rate = config.ALARM_RATES.get(c, 0.0)
            how = f"max({min_flows}, {fmt_rate(rate)} × {tr_int(n_rows)})" if rate else "sabit"
            parts.append(f"{c} {tr_int(alarm_threshold(c, n_rows, min_flows))} ({how})")
    return f"Alarm eşikleri (bu dosya, {tr_int(n_rows)} akış): " + "; ".join(parts) + "."


def fmt_rate(rate):
    return f"{rate:.5f}".rstrip("0").replace(".", ",")


# ------------------------------------------------------------------ uyarı kartı
# WARNING seviyeli (eşiği geçen) alarmlar için anlaşılır başlıklar
WARNING_TITLES = {"PortScan": "Port taraması tespit edildi"}


def warning_card(title, detail):
    """Turuncu UYARI kartı. Streamlit'te turuncu hazır kutu olmadığı için küçük bir HTML kutusu.

    Zemin yarı saydam turuncu, sol şerit koyu turuncu; metin rengi temadan gelir, böylece açık
    ve koyu temada okunur. Metinler html.escape ile kaçırılır (HTML olarak yorumlanmasın).
    """
    st.markdown(
        '<div role="alert" style="background: rgba(240, 120, 20, 0.16); '
        'border-left: 4px solid #E8710A; border-radius: 0.5rem; padding: 0.75rem 1rem; '
        'margin-bottom: 1rem;">'
        f'<div style="font-weight: 600;">⚠️ {html.escape(title)}</div>'
        f'<div style="opacity: 0.85; font-size: 0.9rem;">{html.escape(detail)}</div></div>',
        unsafe_allow_html=True)


# ------------------------------------------------------------------ grafik
def class_chart(summary: pd.DataFrame):
    """Sınıf dağılımı: yatay çubuk, sabit sınıf sırası, tek renk, değer etiketi + ipucu."""
    order = [c for c in config.CLASS_ORDER if c in set(summary["sinif"])]
    data = summary.assign(guven_yuzde=summary["ortalama_guven"] * 100)
    base = alt.Chart(data).encode(
        y=alt.Y("sinif:N", sort=order, title=None),
        x=alt.X("adet:Q", title="Akış sayısı",
                axis=alt.Axis(grid=True, tickCount=5, format="d")),
        tooltip=[alt.Tooltip("sinif:N", title="Sınıf"),
                 alt.Tooltip("adet:Q", title="Akış", format=","),
                 alt.Tooltip("guven_yuzde:Q", title="Ortalama güven (%)", format=".1f")])
    bars = base.mark_bar(cornerRadiusEnd=4, height=22, color="#3B6FD4")
    labels = base.mark_text(align="left", dx=6, color="gray").encode(
        text=alt.Text("adet:Q", format="d"))
    return (bars + labels).properties(height=46 * len(order) + 20)


def cm_heatmap(cm: pd.DataFrame):
    """Hata matrisi ısı haritası: renk satıra göre normalize (gerçek sınıfın yüzde kaçı o
    tahmine gitti = köşegende recall), hücrede ham sayı."""
    order_true, order_pred = list(cm.index), list(cm.columns)
    data = cm.rename_axis(index="gercek", columns="tahmin").stack().rename("adet").reset_index()
    row_sum = data.groupby("gercek")["adet"].transform("sum")
    data["oran"] = (data["adet"] / row_sum.where(row_sum > 0)).fillna(0.0)
    data["etiket"] = data["adet"].map(tr_int)                 # Türkçe binlik ayıracı
    base = alt.Chart(data).encode(
        x=alt.X("tahmin:N", sort=order_pred, title="Tahmin", axis=alt.Axis(labelAngle=-30)),
        y=alt.Y("gercek:N", sort=order_true, title="Gerçek"))
    rect = base.mark_rect().encode(
        color=alt.Color("oran:Q", scale=alt.Scale(domain=[0, 1], scheme="blues"),
                        title="Satır oranı"),
        tooltip=[alt.Tooltip("gercek:N", title="Gerçek"), alt.Tooltip("tahmin:N", title="Tahmin"),
                 alt.Tooltip("adet:Q", title="Akış", format=","),
                 alt.Tooltip("oran:Q", title="Satır oranı", format=".2%")])
    text = base.mark_text(fontSize=12).encode(
        text="etiket:N",
        color=alt.condition(alt.datum.oran > 0.5, alt.value("white"), alt.value("black")))
    return (rect + text).properties(height=46 * len(order_true) + 40)


RESULT_TEXT = {"kritik": "KRİTİK alarm", "uyari": "UYARI", "incelenmeli": "İncelenmeli"}


def threshold_table(alarms, class_summary, n_rows, min_flows):
    """Bu dosyadaki her alarm sınıfı için: oran, tespit edilen akış, eşik ve sonuç."""
    found = dict(zip(class_summary["sinif"], class_summary["adet"]))
    result = {a["sinif"]: RESULT_TEXT.get(card_type(a), card_type(a)) for a in alarms}
    rows = []
    for c in config.CLASS_ORDER:
        if c not in config.ALARM_LEVELS:
            continue
        rate = config.ALARM_RATES.get(c, 0.0)
        rows.append({"Sınıf": c, "Oran": fmt_rate(rate) if rate else "0 (oran yok)",
                     "Tespit edilen akış": int(found.get(c, 0)),
                     "Eşik": int(alarm_threshold(c, n_rows, min_flows)),
                     "Sonuç": result.get(c, "Tespit yok")})
    return pd.DataFrame(rows)


def threshold_explainer(state):
    res = state["result"]
    with st.expander("Alarm seviyeleri nasıl belirlenir?"):
        st.markdown(
            f"Her saldırı sınıfı için eşik: **eşik = max({state['min_flows']}, ⌈oran × n⌉)**, "
            f"n = analiz edilen akış sayısı (bu dosyada {tr_int(res.analyzed_rows)}). "
            "Küçük dosyada sabit alt sınır, büyük dosyada oran belirleyicidir.\n\n"
            "- 🚨 **Kırmızı (KRİTİK):** DoS/DDoS, Botnet, Web Attack veya Brute Force eşiği geçti.\n"
            "- ⚠️ **Turuncu (UYARI):** PortScan eşiği geçti.\n"
            "- 🔎 **Gri/mavi (İncelenmeli):** sınıf tespit edildi ama eşiğin altında kaldı. "
            "Alarm değildir, gizlenmez; düşük sayıda şüpheli akış olarak incelenmelidir.\n\n"
            "Eşik yalnızca alarm seviyesini belirler; tahminler, tablo ve grafik değişmez. "
            "Oranlar ve alt sınır doğrulama kümesinde, sonuçlara bakmadan yazılmış bir ölçütle "
            "seçildi (10. hafta).")
        st.dataframe(threshold_table(state["alarms"], res.class_summary, res.analyzed_rows,
                                     state["min_flows"]),
                     hide_index=True, use_container_width=True)


# ------------------------------------------------------------------ sayfalar
def show_result(state):
    res, alarms = state["result"], state["alarms"]
    st.subheader(f"Sonuç: {state['file_name']}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Analiz edilen akış", tr_int(res.analyzed_rows))
    c2.metric("Saldırı tahmini", tr_int(res.attack_rows),
              help="Benign dışındaki bir sınıfa atanan akış sayısı")
    c2.caption(f"Oran: {pct(res.attack_rows / res.analyzed_rows)}")
    c3.metric("Atlanan satır", tr_int(res.skipped_rows))
    c4.metric("Analiz süresi", f"{res.duration_s:.2f} sn".replace(".", ","))
    if res.skipped_rows:
        reasons = ", ".join(f"{k}: {tr_int(v)}" for k, v in res.skipped_reasons.items())
        st.info(f"{tr_int(res.skipped_rows)} satır bozuk olduğu için analiz dışı bırakıldı "
                f"({reasons}).", icon="ℹ️")

    # Üç ayrı görünüm, üç ayrı anlam:
    #   kırmızı st.error  -> KRİTİK alarm (eşiği geçen DoS/DDoS, Botnet, Web Attack, Brute Force)
    #   turuncu kart      -> UYARI (eşiği geçen WARNING seviyeli sınıf, ör. PortScan)
    #   gri/mavi st.info  -> eşiğin altında kalan "incelenmeli" bilgisi (alarm değil)
    # Eşik yalnızca alarm seviyesini etkiler: tablo ve grafik her akışı olduğu gibi gösterir.
    if alarms:
        for a in alarms:
            count, conf = tr_int(a["adet"]), pct(a["ortalama_guven"])
            kind = card_type(a)
            if kind == "kritik":
                st.error(f"KRİTİK SALDIRI: **{a['sinif']}** — {count} akış "
                         f"(ortalama güven {conf})", icon="🚨")
            elif kind == "incelenmeli":
                st.info(f"İncelenmeli: **{a['sinif']}** — {count} akış (ortalama güven {conf}). "
                        f"Alarm eşiği {a['esik']} akış; bu sayı eşiğin altında olduğu için alarm "
                        "verilmedi, düşük sayıda şüpheli akış olarak gösteriliyor.", icon="🔎")
            else:
                warning_card(f"UYARI: {WARNING_TITLES.get(a['sinif'], a['sinif'] + ' tespit edildi')}"
                             f" ({count} akış)", f"Ortalama güven {conf}")
        st.caption(threshold_text(state["min_flows"], res.analyzed_rows)
                   + f" Alarmlar logs/security.log dosyasına ve veritabanına (analiz "
                   f"#{state['id']}) kaydedildi.")
        st.download_button(
            "Alarm özetini indir (CSV)",
            alarm_summary(alarms, state["file_name"], state["id"])
            .to_csv(index=False).encode("utf-8-sig"),
            file_name=f"alarm_ozeti_{state['id']}_{state['file_name']}", mime="text/csv")
    else:
        st.success("Saldırı tespit edilmedi: tüm akışlar Benign olarak sınıflandı.", icon="✅")
    if state["min_flows"] != config.ALARM_MIN_FLOWS:
        st.warning(f"Bu analizde alarm eşiği alt sınırı N_min = {state['min_flows']} kullanıldı "
                   f"(varsayılan {config.ALARM_MIN_FLOWS}, doğrulamada seçilen değer). Alarm "
                   "seviyeleri varsayılan ayarla karşılaştırılamaz.", icon="⚙️")
    threshold_explainer(state)

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Sınıf dağılımı**")
        st.altair_chart(class_chart(res.class_summary), use_container_width=True)
    with right:
        st.markdown("**Sınıf özeti**")
        st.dataframe(res.class_summary, hide_index=True, use_container_width=True,
                     column_config={
                         "sinif": "Sınıf", "adet": st.column_config.NumberColumn("Akış"),
                         "ortalama_guven": st.column_config.NumberColumn(
                             "Ort. güven", format="%.3f")})

    st.markdown("**İlk 100 tahmin**")
    st.dataframe(res.predictions.head(100), hide_index=True, use_container_width=True,
                 column_config={
                     "satir_no": st.column_config.NumberColumn("Satır", format="%d"),
                     "tahmin": "Tahmin", "gercek": "Gerçek etiket",
                     "guven": st.column_config.ProgressColumn(
                         "Güven", min_value=0.0, max_value=1.0, format="%.3f")})
    st.download_button("Tüm tahminleri CSV olarak indir",
                       res.predictions.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"tahminler_{state['file_name']}", mime="text/csv")

    ev = res.evaluation
    if ev:
        st.divider()
        st.subheader("Gerçek etiketlerle karşılaştırma")
        st.caption("Dosyada Label sütunu bulunduğu için tahminler gerçek etiketlerle "
                   "karşılaştırıldı (demo amaçlı).")
        d1, d2, d3 = st.columns(3)
        d1.metric("Doğruluk", pct(ev["accuracy"]))
        d2.metric("Macro F1", pct(ev["macro_f1"]),
                  help="Dosyada gerçekte bulunan sınıfların F1 ortalaması: "
                       + ", ".join(ev["macro_f1_siniflari"]))
        d3.metric("Karşılaştırılan akış", tr_int(ev["karsilastirilan"]))
        if ev["kapsam_disi_etiket"]:
            st.caption(f"{tr_int(ev['kapsam_disi_etiket'])} satırın etiketi proje sınıfları "
                       "dışında (ör. Infiltration) olduğu için karşılaştırmaya alınmadı.")
        a, b = st.columns(2)
        with a:
            st.markdown("**Sınıf bazında sonuç**")
            st.dataframe(ev["rapor"], hide_index=True, use_container_width=True,
                         column_config={k: st.column_config.NumberColumn(k.title(), format="%.4f")
                                        for k in ("precision", "recall", "f1")})
        with b:
            st.markdown("**Hata matrisi** (hücrede akış sayısı; renk: gerçek sınıfın yüzde "
                        "kaçının o tahmine gittiği)")
            st.altair_chart(cm_heatmap(ev["hata_matrisi"]), use_container_width=True)
    for note in res.notes:
        st.caption(note)


def fmt_threshold(t):
    return f"{float(t):.2f}".replace(".", ",")


# Demo dosyalarının ne göstermek için hazırlandığı (sayılar demo/demo_icerik.json'dan okunur)
DEMO_NOTES = {
    "demo_normal.csv": "yalnızca normal trafik",
    "demo_ddos.csv": "ağırlıklı DoS/DDoS",
    "demo_portscan.csv": "normal trafik + port taraması (turuncu UYARI kartı)",
    "demo_karma.csv": "altı sınıfın karışımı (kırmızı KRİTİK kartlar)",
    "demo_10000_satir.csv": "10.000 satırlık doğal dağılım (N2 başvuru boyutu)",
    "demo_bozuk.csv": "bozuk hücreler: metin, Inf, boş (atlanan satır bilgisi)",
    "demo_eksik_sutun.csv": "eksik sütunlar (Türkçe hata mesajı)",
}


def demo_table(path):
    """demo/demo_icerik.json -> dosya, amaç, içerik tablosu. Dosya yoksa None."""
    info = load_json(path)
    if not info:
        return None
    rows = []
    for name, content in info.items():
        if "satir" in content:
            detail = f"{tr_int(content['satir'])} satır"
        else:
            detail = ", ".join(f"{c} {tr_int(n)}" for c, n in content.items())
        rows.append({"Dosya": name, "Ne gösterir": DEMO_NOTES.get(name, ""),
                     "İçerik (gerçek etiket)": detail})
    return pd.DataFrame(rows)


def empty_state_guide():
    """Dosya yüklenmeden önce gösterilen kısa kullanım rehberi."""
    st.info("**Nasıl kullanılır?**\n\n"
            "1. CICFlowMeter veya CICIDS2017 biçiminde, virgülle ayrılmış bir CSV dosyası seçin "
            "(en fazla 500 MB).\n"
            "2. **Analiz et** düğmesine basın.\n"
            "3. Sonuçta özet kartlarını, alarm kartlarını (kırmızı: KRİTİK, turuncu: UYARI, "
            "gri/mavi: incelenmeli), sınıf dağılımını ve tahmin tablosunu görürsünüz. Dosyada "
            "`Label` sütunu varsa tahminler gerçek etiketlerle de karşılaştırılır.",
            icon="📄")
    table = demo_table(config.DEMO_DIR / "demo_icerik.json")
    if table is not None:
        st.markdown("**Denemek için demo dosyaları** (`demo/` klasörü; test kümesinden "
                    "üretildi, model eğitimde görmedi)")
        st.dataframe(table, hide_index=True, use_container_width=True)


def page_analysis(predictor, logger, min_flows):
    st.title("Ağ Trafiği Analizi")
    st.caption(f"Model: {predictor.version} · {len(predictor.features)} öznitelik · "
               f"Botnet karar eşiği {fmt_threshold(predictor.botnet_threshold)}")
    up = st.file_uploader("CICFlowMeter / CICIDS2017 biçiminde CSV dosyası", type=["csv"])
    if st.button("Analiz et", type="primary", disabled=up is None):
        with st.spinner("Analiz ediliyor..."):
            try:
                res, aid, alarms = run_analysis(predictor, up, up.name, config.DB_PATH, logger,
                                                min_flows=min_flows)
                st.session_state["son"] = {"result": res, "id": aid, "alarms": alarms,
                                           "file_name": up.name, "min_flows": min_flows}
            except InferenceError as e:
                st.session_state.pop("son", None)
                st.warning(f"Dosya analiz edilemedi: {e}", icon="⚠️")
            except Exception:
                logging.getLogger(__name__).exception("Beklenmeyen hata")
                st.session_state.pop("son", None)
                st.error("Beklenmeyen bir hata oluştu; ayrıntılar terminal çıktısında.")
    if "son" in st.session_state:
        show_result(st.session_state["son"])
    elif up is None:
        empty_state_guide()


def tr_datetime(s: pd.Series) -> pd.Series:
    """Veritabanındaki ISO metni (eski kayıtlarda '2026-11-26T17:38:12', yenilerde
    '2026-11-26 17:38:12'; ikisi de yerel saat) yalnızca gösterimde tek biçime çevirir."""
    return pd.to_datetime(s, format="ISO8601").dt.strftime("%d.%m.%Y %H:%M:%S")


def page_history():
    st.title("Geçmiş Analizler")
    conn = database.connect(config.DB_PATH)
    try:
        analyses = database.list_analyses(conn)
        if analyses.empty:
            st.info("Henüz analiz yapılmadı.")
            return
        analyses = analyses.assign(tarih=tr_datetime(analyses["tarih"]))
        st.dataframe(analyses, hide_index=True, use_container_width=True,
                     column_config={"id": "No", "dosya_adi": "Dosya", "tarih": "Tarih",
                                    "toplam_satir": "Toplam satır", "atlanan_satir": "Atlanan",
                                    "sure_sn": st.column_config.NumberColumn("Süre (sn)",
                                                                             format="%.2f"),
                                    "model_surumu": "Model", "alarm_sayisi": "Alarm",
                                    "kritik_alarm": "Kritik alarm",
                                    "saldiri_akisi": "Saldırı akışı"})
        choice = st.selectbox("Ayrıntısı gösterilecek analiz", analyses["id"],
                              format_func=lambda i: f"#{i} — " + analyses.set_index("id")
                              .loc[i, "dosya_adi"])
        labels = {"sinif": "Sınıf", "adet": "Akış", "seviye": "Seviye", "zaman": "Zaman",
                  "dosya_adi": "Dosya", "analiz_id": "Analiz", "id": "No",
                  "dusuk_sayi": st.column_config.CheckboxColumn("Eşik altı"), "esik": "Eşik",
                  "ortalama_guven": st.column_config.NumberColumn("Ort. güven", format="%.3f")}
        a, b = st.columns(2)
        with a:
            st.markdown("**Sınıf dağılımı**")
            st.dataframe(database.class_summaries(conn, choice), hide_index=True,
                         use_container_width=True, column_config=labels)
        with b:
            st.markdown("**Alarmlar**")
            al = database.list_alarms(conn, choice)
            if al.empty:
                st.caption("Bu analizde alarm yok.")
            else:
                al = al.assign(zaman=tr_datetime(al["zaman"]))
                st.dataframe(al[["sinif", "adet", "seviye", "dusuk_sayi", "esik", "zaman"]],
                             hide_index=True,
                             use_container_width=True, column_config=labels)
        st.markdown("**Tüm alarmlar (son 500)**")
        all_alarms = database.list_alarms(conn)
        if not all_alarms.empty:
            all_alarms = all_alarms.assign(zaman=tr_datetime(all_alarms["zaman"]))
        st.dataframe(all_alarms, hide_index=True, use_container_width=True,
                     column_config=labels)
    finally:
        conn.close()


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def page_about(predictor):
    """Model Hakkında: sayılar reports/ dosyalarından okunur, elle yazılmaz."""
    st.title("Model Hakkında")
    st.markdown(
        "Random Forest (100 ağaç, en fazla derinlik 20), CICIDS2017 akış kayıtlarıyla eğitildi. "
        "Altı sınıf: Benign, DoS/DDoS, PortScan, Brute Force, Web Attack, Botnet. "
        f"Model {len(predictor.features)} öznitelik kullanır; `Destination Port` port ezberini "
        "önlemek için kullanılmaz. Botnet olasılığı "
        f"{str(predictor.botnet_threshold).replace('.', ',')} veya üzerindeyse akış Botnet sayılır.")

    m = load_json(config.REPORTS_DIR / "metrics.json")
    st.subheader("Test kümesinde başarım")
    if not m or "Random Forest" not in m.get("modeller", {}):
        st.info("Başarım dosyası (reports/metrics.json) bulunamadı. Önce "
                "`python run_pipeline.py` çalıştırın.")
    else:
        rf = m["modeller"]["Random Forest"]
        st.caption(f"Küme: **test** ({tr_int(m['test_satir'])} akış; eğitimde ve ayar seçiminde "
                   f"kullanılmadı). Model {m['model_surumu']}, ölçüm {m['zaman']}. "
                   "Kaynak: reports/metrics.json")
        if m["model_surumu"] != predictor.version:
            st.warning(f"Bu sonuçlar {m['model_surumu']} modeline ait; uygulamadaki model "
                       f"{predictor.version}.", icon="⚠️")
        c1, c2, c3 = st.columns(3)
        c1.metric("Doğruluk", pct(rf["accuracy"]))
        c2.metric("Macro F1", pct(rf["macro_f1"]))
        c3.metric("Tek kayıt gecikmesi (medyan)",
                  f"{rf['single_latency_median_ms']:.2f} ms".replace(".", ","))
        per = pd.DataFrame([{"Sınıf": c, "Precision": v["precision"], "Recall": v["recall"],
                             "F1": v["f1-score"], "Test akışı": int(v["support"])}
                            for c, v in rf["per_class"].items()])
        a, b = st.columns([2, 3])
        with a:
            st.markdown("**Sınıf bazında sonuç** (küme: test)")
            st.dataframe(per, hide_index=True, use_container_width=True,
                         column_config={k: st.column_config.NumberColumn(k, format="%.4f")
                                        for k in ("Precision", "Recall", "F1")})
        with b:
            st.markdown("**Hata matrisi** (küme: test; hücrede akış sayısı, renk: satır oranı)")
            names = m["sinif_adlari"]
            cm = pd.DataFrame(rf["confusion_matrix"], index=pd.Index(names, name="Gerçek"),
                              columns=pd.Index(names, name="Tahmin"))
            st.altair_chart(cm_heatmap(cm), use_container_width=True)

    st.subheader("Öznitelik önemi")
    imp_path = config.REPORTS_DIR / "hafta11" / "onem_tablosu.csv"
    try:
        imp = pd.read_csv(imp_path)
    except (OSError, ValueError):
        imp = None
    if imp is None or imp.empty:
        st.info("Öznitelik önem tablosu (reports/hafta11/onem_tablosu.csv) bulunamadı. "
                "`python experiments/botnet_importance.py` ile üretilir.")
    else:
        st.caption("Küme: **doğrulama**. Model uygulamadakiyle aynı ayarlarla yalnızca "
                   "alt-eğitim kümesinde eğitildi (doğrulama satırlarını görmedi). "
                   "Kaynak: reports/hafta11/onem_tablosu.csv")
        method = st.radio("Yöntem", ["Permutation — Botnet F1 düşüşü",
                                     "Permutation — Macro F1 düşüşü",
                                     "Impurity (RF'nin kendi önemi)"], horizontal=True)
        col = {"Permutation — Botnet F1 düşüşü": "perm_botnet_f1",
               "Permutation — Macro F1 düşüşü": "perm_macro_f1",
               "Impurity (RF'nin kendi önemi)": "impurity"}[method]
        top = imp.nlargest(15, col)
        title = (f"{method} · küme: doğrulama" if col != "impurity" else
                 f"{method} · eğitimden hesaplanır (alt-eğitim, SMOTE sonrası)")
        chart = alt.Chart(top).mark_bar(color="#3B6FD4").encode(
            x=alt.X(f"{col}:Q", title=title),
            y=alt.Y("oznitelik:N", sort="-x", title=None, axis=alt.Axis(labelLimit=300)),
            tooltip=[alt.Tooltip("oznitelik:N", title="Öznitelik"),
                     alt.Tooltip(f"{col}:Q", title="Önem", format=".4f")])
        st.altair_chart(chart.properties(height=15 * 26), use_container_width=True)
        st.caption("Impurity önemi eğitim sırasında ağaçların bölmelerinden hesaplanır; ilişkili "
                   "öznitelikler önemi paylaşır. Permutation önemi, bir sütun karıştırıldığında "
                   "doğrulama puanının ne kadar düştüğüdür; ilintili bir ikizi olan sütun düşük "
                   "çıkabilir.")

    st.subheader("Bilinen sınırlar")
    lines = []
    if m and "Random Forest" in m.get("modeller", {}):
        bot = m["modeller"]["Random Forest"]["per_class"].get("Botnet")
        if bot:
            lines.append(f"- **Botnet** en zayıf sınıf (test F1 {pct(bot['f1-score'])}, "
                         f"precision {pct(bot['precision'])}): bazı normal akışlar akış "
                         "düzeyinde Botnet akışlarından ayırt edilemiyor.")
    lines += ["- **Alarm eşiği** büyük dosyalarda yükselir; az sayıda gerçek saldırı akışı "
              "'incelenmeli' olarak gösterilebilir.",
              "- Model aynı veri setinin (CICIDS2017) ayrılmış test kümesiyle ölçüldü; farklı ağda "
              "veya farklı CICFlowMeter sürümüyle çıkarılan akışlarda başarı düşebilir."]
    st.markdown("\n".join(lines))


def main():
    page = st.sidebar.radio("Sayfa", ["Analiz", "Geçmiş Analizler", "Model Hakkında"])
    with st.sidebar.expander("Gelişmiş ayarlar"):
        min_flows = st.number_input(
            "Alarm eşiği N_min (en az kaç akış)", min_value=1, max_value=100_000,
            value=config.ALARM_MIN_FLOWS, step=1,
            help="Bir saldırı sınıfından eşikten az akış bulunursa kritik alarm yerine "
                 "'düşük sayıda şüpheli akış, incelenmeli' uyarısı verilir. Eşik = max(N_min, "
                 "oran × analiz edilen akış); büyük dosyalarda oran devreye girer. Tahminleri "
                 "değiştirmez. Değerler doğrulama kümesinde seçildi.")
        st.caption("Oranlar (sabit): " + ", ".join(
            f"{c} {fmt_rate(r)}" if r else f"{c} yok"
            for c, r in config.ALARM_RATES.items()))
    # "23." satır başında Markdown'da numaralı liste sanılır; ters bölü ile kaçırılır
    st.sidebar.caption("23\\. Grup · Fırat Üniversitesi Mühendislik Tasarımı")
    try:
        predictor = load_predictor()
    except InferenceError as e:
        st.error(str(e))
        st.stop()
    if page == "Analiz":
        page_analysis(predictor, load_logger(), int(min_flows))
    elif page == "Model Hakkında":
        page_about(predictor)
    else:
        page_history()


main()
