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
import logging

import altair as alt
import pandas as pd
import streamlit as st

from src import config, database
from src.alarm import alarm_threshold, card_type, get_security_logger
from src.inference import InferenceError, Predictor
from src.service import run_analysis

st.set_page_config(page_title="Siber Saldırı Sınıflandırma", page_icon="🛡️", layout="wide")


@st.cache_resource(show_spinner="Model yükleniyor...")
def load_predictor():
    return Predictor()


@st.cache_resource
def load_logger():
    return get_security_logger()


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
    else:
        st.success("Saldırı tespit edilmedi: tüm akışlar Benign olarak sınıflandı.", icon="✅")

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
            st.markdown("**Hata matrisi** (satır: gerçek, sütun: tahmin)")
            st.dataframe(ev["hata_matrisi"], use_container_width=True)
    for note in res.notes:
        st.caption(note)


def page_analysis(predictor, logger, min_flows):
    st.title("Ağ Trafiği Analizi")
    st.caption(f"Model: {predictor.version} · {len(predictor.features)} öznitelik · "
               f"Botnet karar eşiği {predictor.botnet_threshold}")
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


def page_history():
    st.title("Geçmiş Analizler")
    conn = database.connect(config.DB_PATH)
    try:
        analyses = database.list_analyses(conn)
        if analyses.empty:
            st.info("Henüz analiz yapılmadı.")
            return
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
                st.dataframe(al[["sinif", "adet", "seviye", "dusuk_sayi", "esik", "zaman"]],
                             hide_index=True,
                             use_container_width=True, column_config=labels)
        st.markdown("**Tüm alarmlar (son 500)**")
        st.dataframe(database.list_alarms(conn), hide_index=True, use_container_width=True,
                     column_config=labels)
    finally:
        conn.close()


def main():
    page = st.sidebar.radio("Sayfa", ["Analiz", "Geçmiş Analizler"])
    min_flows = st.sidebar.number_input(
        "Alarm eşiği N_min (en az kaç akış)", min_value=1, max_value=100_000,
        value=config.ALARM_MIN_FLOWS, step=1,
        help="Bir saldırı sınıfından eşikten az akış bulunursa kritik alarm yerine "
             "'düşük sayıda şüpheli akış, incelenmeli' uyarısı verilir. Eşik = max(N_min, "
             "oran × analiz edilen akış); büyük dosyalarda oran devreye girer. Tahminleri "
             "değiştirmez. Değerler doğrulama kümesinde seçildi.")
    st.sidebar.caption("Oranlar (sabit): " + ", ".join(
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
    else:
        page_history()


main()
