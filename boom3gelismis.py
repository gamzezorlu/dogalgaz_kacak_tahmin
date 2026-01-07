import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from sklearn.ensemble import IsolationForest
from scipy import stats
import warnings
warnings.filterwarnings("ignore")

# ======================================================
# STREAMLIT AYAR
# ======================================================
st.set_page_config(
    page_title="Gaz Sayacı Manipülasyon Tespiti",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 Gaz Sayacı Manipülasyon Tespit Sistemi (Optimize Hibrit)")

# ======================================================
# CACHE – VERİ HAZIRLIK
# ======================================================
@st.cache_data(show_spinner=False)
def preprocess(df):
    df = df.copy()
    df["tarih"] = pd.to_datetime(df["tarih"])
    df = df.sort_values(["tesisat_no", "tarih"])

    df["ay"] = df["tarih"].dt.month
    df["prev_3_avg"] = (
        df.groupby("tesisat_no")["tuketim"]
        .transform(lambda x: x.rolling(3, min_periods=1).mean())
    )
    return df

# ======================================================
# CACHE – GLOBAL ML (TEK SEFER)
# ======================================================
@st.cache_resource(show_spinner=False)
def train_global_iforest(df):
    features = np.column_stack([
        df["tuketim"].values,
        df["ay"].values,
        df["prev_3_avg"].values,
        np.abs(df["tuketim"] - df["prev_3_avg"]).values
    ])

    model = IsolationForest(
        n_estimators=150,
        contamination=0.05,
        random_state=42,
        n_jobs=-1
    )
    model.fit(features)

    scores = model.decision_function(features)
    df["ml_score"] = 1 - (scores - scores.min()) / (scores.max() - scores.min())
    return df

# ======================================================
# ANALİZ SINIFI
# ======================================================
class GazSayacAnaliz:

    def find_candidates(self, df):
        tuketim = df["tuketim"].values
        if len(tuketim) < 12:
            return []

        threshold = np.percentile(tuketim, 95)
        idx = np.where(tuketim >= threshold)[0]
        return idx

    def seasonal_adjust(self, df):
        m = df["ay"]
        factor = np.where(m.isin([11,12,1,2,3]), 1.4,
                 np.where(m.isin([6,7,8,9]), 0.6, 0.95))
        return df["tuketim"].values / factor

    def analyze_tesisat(self, df):
        results = []
        candidates = self.find_candidates(df)

        for idx in candidates:
            if idx < 3 or idx > len(df) - 4:
                continue

            before = df.iloc[:idx]
            after = df.iloc[idx+1:]

            if len(before) < 3 or len(after) < 3:
                continue

            before_mean = before["tuketim"].mean()
            after_mean = after["tuketim"].mean()

            score = 0
            details = {}

            # 1️⃣ Rekor oranı
            rekor_orani = df.iloc[idx]["tuketim"] / before_mean if before_mean > 0 else 0
            details["rekor_orani"] = round(rekor_orani, 2)
            if rekor_orani >= 3: score += 25
            elif rekor_orani >= 2.5: score += 20
            elif rekor_orani >= 2: score += 12

            # 2️⃣ Ani düşüş
            ilk3 = after.head(3)["tuketim"].mean()
            dusus = ((ilk3 - before_mean) / before_mean) * 100
            details["ilk_3_ay_dusus"] = round(dusus, 1)
            if dusus < -60: score += 30
            elif dusus < -50: score += 24
            elif dusus < -40: score += 18

            # 3️⃣ Mevsimsellik
            before_adj = self.seasonal_adjust(before)
            after_adj = self.seasonal_adjust(after)
            try:
                _, p = stats.ttest_ind(before_adj, after_adj)
                details["p_value"] = round(p, 4)
                if p < 0.01 and dusus < -20:
                    score += 10
            except:
                pass

            # 4️⃣ Trend
            try:
                sb = np.polyfit(np.arange(len(before)), before["tuketim"], 1)[0]
                sa = np.polyfit(np.arange(len(after)), after["tuketim"], 1)[0]
                if sb > -0.5 and sa < -2:
                    score += 10
                    details["trend"] = "VAR"
                else:
                    details["trend"] = "YOK"
            except:
                pass

            # 5️⃣ Varyans
            var_change = ((after["tuketim"].std() - before["tuketim"].std()) /
                          before["tuketim"].std()) * 100
            details["varyans_degisim"] = round(var_change, 1)
            if var_change < -40: score += 10

            # 6️⃣ ML skor
            ml_score = df.iloc[idx]["ml_score"]
            details["ml_skor"] = round(ml_score, 2)
            if ml_score > 0.7: score += 5

            score = min(100, round(score))

            risk = "DÜŞÜK"
            if score >= 60: risk = "YÜKSEK"
            elif score >= 35: risk = "ORTA"

            results.append({
                "tesisat_no": df.iloc[0]["tesisat_no"],
                "bina_no": df.iloc[0]["bina_no"],
                "rekor_tarihi": df.iloc[idx]["tarih"],
                "rekor_degeri": df.iloc[idx]["tuketim"],
                "ortalama_oncesi": round(before_mean,1),
                "ortalama_sonrasi": round(after_mean,1),
                "süphe_puani": score,
                "manipulasyon_olasiligi": risk,
                "detay": details
            })

        if results:
            return max(results, key=lambda x: x["süphe_puani"])
        return None

# ======================================================
# STREAMLIT ARAYÜZ
# ======================================================
with st.sidebar:
    uploaded = st.file_uploader("Excel yükle", type=["xlsx","xls"])
    st.markdown("Gerekli kolonlar:")
    st.code("tesisat_no\nbina_no\ntarih\ntuketim")

if uploaded:
    df = pd.read_excel(uploaded)
    df = preprocess(df)
    df = train_global_iforest(df)

    st.success(f"Veri yüklendi: {df['tesisat_no'].nunique()} tesisat")

    if st.button("🚀 Analizi Başlat", type="primary"):
        analyzer = GazSayacAnaliz()
        results = []

        tesisatlar = df["tesisat_no"].unique()
        bar = st.progress(0)

        for i, t in enumerate(tesisatlar):
            tdf = df[df["tesisat_no"] == t]
            r = analyzer.analyze_tesisat(tdf)
            if r:
                results.append(r)
            bar.progress((i+1)/len(tesisatlar))

        res = pd.DataFrame(results)

        st.success(f"Analiz tamamlandı: {len(res)} şüpheli tesisat")

        st.dataframe(res[[
            "tesisat_no","bina_no","rekor_tarihi",
            "rekor_degeri","süphe_puani","manipulasyon_olasiligi"
        ]], use_container_width=True)

        # Grafik
        fig = px.histogram(res, x="süphe_puani", color="manipulasyon_olasiligi",
                           title="Şüphe Puanı Dağılımı")
        st.plotly_chart(fig, use_container_width=True)

        # Excel
        from io import BytesIO
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            res.to_excel(writer, index=False)
        st.download_button(
            "📥 Excel indir",
            buffer.getvalue(),
            file_name=f"gaz_sayac_analiz_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )

else:
    st.info("Sol menüden Excel yükleyin")
