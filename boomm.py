import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.set_page_config(layout="wide")
st.title("🔍 Doğalgaz Sayaç Müdahalesi (Rekor Delme) Tespit Sistemi")

# -----------------------------
# DOSYA YÜKLEME
# -----------------------------
uploaded_file = st.file_uploader("Excel dosyasını yükleyin", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)

    # Kolon kontrolü
    required_cols = ["tarih", "tesisat", "bina_numarasi", "tuketim"]
    if not all(col in df.columns for col in required_cols):
        st.error("Excel dosyası gerekli kolonları içermiyor.")
        st.stop()

    # -----------------------------
    # VERİ HAZIRLIK
    # -----------------------------
    df["tarih"] = pd.to_datetime(df["tarih"])
    df["ay"] = df["tarih"].dt.month
    df = df.sort_values(["tesisat", "tarih"])

    st.success("Veri başarıyla yüklendi")

    # -----------------------------
    # PARAMETRELER
    # -----------------------------
    st.sidebar.header("⚙️ Analiz Parametreleri")

    once_ay = st.sidebar.slider("Öncesi ay sayısı", 12, 36, 24)
    sonra_ay = st.sidebar.slider("Sonrası ay sayısı", 12, 36, 24)
    dusus_esigi = st.sidebar.slider("Düşüş oranı eşiği", 0.4, 0.8, 0.7)
    kalicilik_orani = st.sidebar.slider("Kalıcılık oranı (%)", 50, 90, 70)

    # -----------------------------
    # MEVSİMSELLİK NORMALİZASYONU
    # -----------------------------
    aylik_median = (
        df.groupby(["tesisat", "ay"])["tuketim"]
        .median()
        .reset_index(name="aylik_median")
    )

    df = df.merge(aylik_median, on=["tesisat", "ay"], how="left")
    df["norm_tuketim"] = df["tuketim"] / df["aylik_median"]

    # -----------------------------
    # REKOR DELME TESPİT FONKSİYONU
    # -----------------------------
    def tespit_et(grup):
        sonuc = []

        if len(grup) < once_ay + sonra_ay + 6:
            return pd.DataFrame()

        for i in range(once_ay, len(grup) - sonra_ay):
            once = grup.iloc[i - once_ay:i]["norm_tuketim"]
            sonra = grup.iloc[i:i + sonra_ay]["norm_tuketim"]

            if once.median() == 0:
                continue

            oran = sonra.median() / once.median()
            kalici = (sonra < dusus_esigi * once.median()).mean()

            # Geri dönüş kontrolü (son 12 ay)
            son12 = grup.iloc[-12:]["norm_tuketim"].median()
            geri_donus = son12 >= 0.8 * once.median()

            if oran < dusus_esigi and kalici >= kalicilik_orani / 100 and not geri_donus:
                sonuc.append({
                    "tesisat": grup.iloc[i]["tesisat"],
                    "bina_numarasi": grup.iloc[i]["bina_numarasi"],
                    "olasi_mudahale_tarihi": grup.iloc[i]["tarih"],
                    "once_medyan": once.median(),
                    "sonra_medyan": sonra.median(),
                    "dusme_orani": round(oran, 2),
                    "kalicilik_orani": round(kalici * 100, 1),
                    "suphe_seviyesi": "Yüksek" if oran < 0.6 else "Orta"
                })

        return pd.DataFrame(sonuc)

    # -----------------------------
    # ANALİZİ ÇALIŞTIR
    # -----------------------------
    with st.spinner("Analiz yapılıyor..."):
        rapor = (
            df.groupby("tesisat", group_keys=False)
            .apply(tespit_et)
            .reset_index(drop=True)
        )

    # -----------------------------
    # SONUÇ GÖSTERİM
    # -----------------------------
    st.subheader("🚨 Şüpheli Tesisatlar")

    if rapor.empty:
        st.info("Şüpheli tesisat bulunamadı.")
    else:
        st.dataframe(rapor)

        # -----------------------------
        # EXCEL İNDİRME
        # -----------------------------
        excel_bytes = rapor.to_excel(index=False, engine="openpyxl")
        st.download_button(
            "📥 Excel Raporunu İndir",
            data=excel_bytes,
            file_name="rekor_delik_supheli_tesisatlar.xlsx"
        )

        # -----------------------------
        # GRAFİK
        # -----------------------------
        st.subheader("📊 Tesisat Bazlı Grafik")

        secilen = st.selectbox(
            "Tesisat seç",
            rapor["tesisat"].unique()
        )

        gdf = df[df["tesisat"] == secilen]
        kirmalar = rapor[rapor["tesisat"] == secilen]

        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(gdf["tarih"], gdf["norm_tuketim"], label="Normalize Tüketim")

        for _, r in kirmalar.iterrows():
            ax.axvline(r["olasi_mudahale_tarihi"], color="red", linestyle="--")

        ax.set_title(f"Tesisat {secilen} – Normalize Tüketim")
        ax.legend()
        st.pyplot(fig)
