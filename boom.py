"""
================================================================================
DOĞALGAZ SAYAÇ MÜDAHALESİ TESPİT SİSTEMİ
Versiyon: 1.0
Geliştirilme Tarihi: 2025
================================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
from io import BytesIO
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# SAYFA YAPILANDIRMASI
# ============================================================================
st.set_page_config(
    page_title="Doğalgaz Sayaç Müdahale Tespit Sistemi",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS Stilleri
st.markdown("""
    <style>
    .big-font {
        font-size:20px !important;
        font-weight: bold;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #ff4b4b;
    }
    .stAlert {
        padding: 1rem;
        border-radius: 0.5rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 28px;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# ============================================================================
# BAŞLIK VE AÇIKLAMA
# ============================================================================
st.title("🔍 Doğalgaz Sayaç Müdahale Tespit Sistemi")
st.markdown("""
Bu sistem, doğalgaz tesisatlarında olası sayaç müdahalelerini tespit etmek için:
- **Bina içi karşılaştırma** (komşularla kıyaslama)
- **Mevsimsel normalizasyon** (kış-yaz ayırımı)
- **Z-score analizi** (istatistiksel sapma)
- **Süreklilik kontrolü** (kalıcı düşüşler)

yöntemlerini kullanır.
""")
st.markdown("---")

# ============================================================================
# SIDEBAR - PARAMETRELER
# ============================================================================
st.sidebar.header("⚙️ Analiz Parametreleri")

st.sidebar.markdown("### 📉 Düşüş Oranı Kriterleri")
MIN_DUSUS_ORANI = st.sidebar.slider(
    "Minimum Düşüş Oranı (%)", 
    min_value=10, max_value=40, value=20, step=5,
    help="Tüketimde en az bu kadar düşüş olmalı"
) / 100

MAX_DUSUS_ORANI = st.sidebar.slider(
    "Maximum Düşüş Oranı (%)", 
    min_value=50, max_value=90, value=70, step=5,
    help="Bu değerin üzerindeki düşüşler de şüpheli (çok aşırı)"
) / 100

st.sidebar.markdown("### ⏱️ Süreklilik Kriterleri")
MIN_SUREKLILIK_AY = st.sidebar.slider(
    "Minimum Süreklilik (Ay)", 
    min_value=3, max_value=12, value=6, step=1,
    help="Düşüş en az bu kadar ay sürmeli"
)

st.sidebar.markdown("### 🏢 Bina Kriterleri")
MIN_BINA_DAIRE_SAYISI = st.sidebar.slider(
    "Min. Bina Daire Sayısı", 
    min_value=2, max_value=10, value=3, step=1,
    help="Karşılaştırma için binada en az bu kadar daire olmalı"
)

BINA_SAPMA_ESIGI = st.sidebar.slider(
    "Z-Score Kayma Eşiği", 
    min_value=0.3, max_value=2.0, value=0.5, step=0.1,
    help="Bina ortalamasından ne kadar sapma olmalı"
)

st.sidebar.markdown("### 🎯 Ek Filtreler")
SADECE_TERS_YONLU = st.sidebar.checkbox(
    "Sadece Ters Yönlü Hareketler",
    value=False,
    help="Bina artarken daire düşenler (en şüpheli)"
)

MIN_ONCEKI_TUKETIM = st.sidebar.number_input(
    "Min. Önceki Ortalama Tüketim (m³)",
    min_value=0,
    value=50,
    step=10,
    help="Çok düşük tüketimli daireleri filtrele"
)

st.sidebar.markdown("---")
st.sidebar.info("💡 **İpucu:** Parametreleri ayarlayarak hassasiyeti değiştirebilirsiniz.")

# ============================================================================
# YARDIMCI FONKSİYONLAR
# ============================================================================

# Mevsim tanımları
KIS_AYLARI = [12, 1, 2, 3]
BAHAR_AYLARI = [4, 5]
YAZ_AYLARI = [6, 7, 8, 9]
SONBAHAR_AYLARI = [10, 11]

def mevsim_bul(ay):
    """Ayın hangi mevside olduğunu döndürür"""
    if ay in KIS_AYLARI:
        return 'kis'
    elif ay in BAHAR_AYLARI:
        return 'bahar'
    elif ay in YAZ_AYLARI:
        return 'yaz'
    else:
        return 'sonbahar'

def validate_dataframe(df):
    """Veri çerçevesini doğrular"""
    required_columns = ['tarih', 'tesisat', 'bina_numarasi', 'tuketim']
    
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        return False, f"Eksik kolonlar: {', '.join(missing)}"
    
    # Tarih formatı kontrolü
    try:
        pd.to_datetime(df['tarih'])
    except:
        return False, "Tarih kolonu geçerli bir tarih formatında değil (YYYY-MM bekleniyor)"
    
    # Sayısal değer kontrolü
    if not pd.api.types.is_numeric_dtype(df['tuketim']):
        try:
            df['tuketim'] = pd.to_numeric(df['tuketim'])
        except:
            return False, "Tüketim kolonu sayısal değerler içermiyor"
    
    # Negatif değer kontrolü
    if (df['tuketim'] < 0).any():
        return False, "Tüketim kolonu negatif değerler içeriyor"
    
    return True, "Veri doğrulandı"

# ============================================================================
# ANA ANALİZ FONKSİYONU
# ============================================================================

@st.cache_data(show_spinner=False)
def tespit_et_sayac_mudehalesi_bina_bazli(df, params):
    """Ana tespit fonksiyonu"""
    
    df = df.copy()
    df['tarih_dt'] = pd.to_datetime(df['tarih'])
    df['yil'] = df['tarih_dt'].dt.year
    df['ay'] = df['tarih_dt'].dt.month
    df['mevsim'] = df['ay'].apply(mevsim_bul)
    df['yil_ay'] = df['tarih_dt'].dt.to_period('M')
    
    supheliler = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    binalar = df['bina_numarasi'].unique()
    total_binalar = len(binalar)
    
    for bina_idx, bina_no in enumerate(binalar):
        status_text.text(f"📊 Analiz ediliyor: Bina {bina_no} ({bina_idx+1}/{total_binalar})")
        progress_bar.progress((bina_idx + 1) / total_binalar)
        
        bina_df = df[df['bina_numarasi'] == bina_no].copy()
        daireler = bina_df['tesisat'].unique()
        
        if len(daireler) < params['min_bina_daire']:
            continue
        
        for tesisat_id in daireler:
            tesisat_df = bina_df[bina_df['tesisat'] == tesisat_id].sort_values('tarih_dt').copy()
            
            if len(tesisat_df) < 18:
                continue
            
            diger_daireler = bina_df[bina_df['tesisat'] != tesisat_id].copy()
            
            if len(diger_daireler) == 0:
                continue
                
            bina_ortalamalar = diger_daireler.groupby('yil_ay')['tuketim'].agg(['mean', 'std']).reset_index()
            bina_ortalamalar.columns = ['yil_ay', 'bina_ort', 'bina_std']
            
            tesisat_df = tesisat_df.merge(bina_ortalamalar, on='yil_ay', how='left')
            tesisat_df['z_score'] = (tesisat_df['tuketim'] - tesisat_df['bina_ort']) / (tesisat_df['bina_std'] + 1)
            
            yillar = sorted(tesisat_df['yil'].unique())
            
            if len(yillar) < 3:
                continue
            
            tesisat_supheleri = []
            
            for kirilma_yil in yillar[1:-1]:
                for kirilma_ay in range(1, 13):
                    
                    kirilma_tarihi = f"{kirilma_yil}-{kirilma_ay:02d}"
                    
                    if kirilma_tarihi not in tesisat_df['tarih'].values:
                        continue
                    
                    onceki_yil_start = pd.to_datetime(f"{kirilma_yil-1}-{kirilma_ay:02d}-01")
                    kirilma_dt = pd.to_datetime(f"{kirilma_yil}-{kirilma_ay:02d}-01")
                    
                    onceki_donem = tesisat_df[
                        (tesisat_df['tarih_dt'] >= onceki_yil_start) & 
                        (tesisat_df['tarih_dt'] < kirilma_dt)
                    ].copy()
                    
                    if len(onceki_donem) < 6:
                        continue
                    
                    onceki_ort_tuketim = onceki_donem['tuketim'].mean()
                    if onceki_ort_tuketim < params['min_onceki_tuketim']:
                        continue
                    
                    sonraki_donem_end = kirilma_dt + pd.DateOffset(months=12)
                    sonraki_donem = tesisat_df[
                        (tesisat_df['tarih_dt'] >= kirilma_dt) & 
                        (tesisat_df['tarih_dt'] < sonraki_donem_end)
                    ].copy()
                    
                    if len(sonraki_donem) < 6:
                        continue
                    
                    mevsimsel_dusus = []
                    ay_detaylari = []
                    
                    for _, row in sonraki_donem.iterrows():
                        ay = row['ay']
                        tuketim = row['tuketim']
                        mevsim = row['mevsim']
                        
                        ayni_ay_onceki = tesisat_df[
                            (tesisat_df['ay'] == ay) & 
                            (tesisat_df['tarih_dt'] < kirilma_dt)
                        ]['tuketim']
                        
                        if len(ayni_ay_onceki) > 0:
                            beklenen = np.median(ayni_ay_onceki)
                            
                            if beklenen > 10:
                                dusus_orani = (beklenen - tuketim) / beklenen
                                mevsimsel_dusus.append(dusus_orani)
                                
                                ay_detaylari.append({
                                    'tarih': row['tarih'],
                                    'ay': ay,
                                    'mevsim': mevsim,
                                    'beklenen': round(beklenen, 2),
                                    'gerceklesen': round(tuketim, 2),
                                    'dusus': round(dusus_orani * 100, 1)
                                })
                    
                    if len(mevsimsel_dusus) < 6:
                        continue
                    
                    dusuk_ay_sayisi = sum(1 for d in mevsimsel_dusus if d >= params['min_dusus'])
                    
                    if dusuk_ay_sayisi < params['min_sureklilik']:
                        continue
                    
                    ort_dusus = np.mean(mevsimsel_dusus)
                    std_dusus = np.std(mevsimsel_dusus)
                    
                    onceki_z_scores = onceki_donem['z_score'].dropna()
                    onceki_z_ort = onceki_z_scores.mean() if len(onceki_z_scores) > 0 else 0
                    
                    sonraki_z_scores = sonraki_donem['z_score'].dropna()
                    sonraki_z_ort = sonraki_z_scores.mean() if len(sonraki_z_scores) > 0 else 0
                    
                    z_kayma = onceki_z_ort - sonraki_z_ort
                    
                    bina_onceki = bina_ortalamalar[
                        (bina_ortalamalar['yil_ay'] >= onceki_yil_start.to_period('M')) &
                        (bina_ortalamalar['yil_ay'] < kirilma_dt.to_period('M'))
                    ]['bina_ort'].mean()
                    
                    bina_sonraki = bina_ortalamalar[
                        (bina_ortalamalar['yil_ay'] >= kirilma_dt.to_period('M')) &
                        (bina_ortalamalar['yil_ay'] < sonraki_donem_end.to_period('M'))
                    ]['bina_ort'].mean()
                    
                    bina_degisim = 0
                    if bina_onceki > 0:
                        bina_degisim = (bina_sonraki - bina_onceki) / bina_onceki
                    
                    if not (params['min_dusus'] <= ort_dusus <= params['max_dusus']):
                        continue
                    
                    if std_dusus > 0.20:
                        continue
                    
                    if z_kayma < params['z_esik']:
                        continue
                    
                    ters_yonlu_hareket = (bina_degisim > 0.05 and ort_dusus > 0.15)
                    
                    if params['sadece_ters_yonlu'] and not ters_yonlu_hareket:
                        continue
                    
                    toparlanma_var = False
                    
                    if kirilma_yil + 2 in yillar:
                        gelecek_yil_df = tesisat_df[tesisat_df['yil'] == kirilma_yil + 2]
                        
                        if len(gelecek_yil_df) >= 6:
                            gelecek_z = gelecek_yil_df['z_score'].mean()
                            gelecek_tuketim = gelecek_yil_df['tuketim'].mean()
                            
                            if (abs(gelecek_z - onceki_z_ort) < 0.5 and
                                gelecek_tuketim > 0.9 * onceki_ort_tuketim):
                                toparlanma_var = True
                                continue
                    
                    kis_detay = [d for d in ay_detaylari if d['mevsim'] == 'kis']
                    yaz_detay = [d for d in ay_detaylari if d['mevsim'] == 'yaz']
                    
                    kis_ort = np.mean([d['dusus'] for d in kis_detay]) if len(kis_detay) > 0 else 0
                    yaz_ort = np.mean([d['dusus'] for d in yaz_detay]) if len(yaz_detay) > 0 else 0
                    
                    if len(kis_detay) > 0 and len(yaz_detay) > 0:
                        if kis_ort < 15 or yaz_ort < 15:
                            continue
                    
                    suphe_skoru = (
                        ort_dusus * 40 +
                        z_kayma * 15 +
                        (1 - std_dusus) * 20 +
                        (30 if ters_yonlu_hareket else 0) +
                        (dusuk_ay_sayisi / 12) * 10
                    )
                    
                    tesisat_supheleri.append({
                        'tesisat': tesisat_id,
                        'bina_numarasi': bina_no,
                        'bina_daire_sayisi': len(daireler),
                        'kirilma_tarihi': kirilma_tarihi,
                        'onceki_ort_tuketim': round(onceki_ort_tuketim, 2),
                        'sonraki_ort_tuketim': round(sonraki_donem['tuketim'].mean(), 2),
                        'genel_dusus_orani': round(ort_dusus * 100, 1),
                        'kis_dusus': round(kis_ort, 1),
                        'yaz_dusus': round(yaz_ort, 1),
                        'tutarlilik': round((1 - std_dusus) * 100, 1),
                        'onceki_z_score': round(onceki_z_ort, 2),
                        'sonraki_z_score': round(sonraki_z_ort, 2),
                        'z_kayma': round(z_kayma, 2),
                        'bina_trend': round(bina_degisim * 100, 1),
                        'ters_yonlu': 'EVET' if ters_yonlu_hareket else 'Hayır',
                        'toparlanma': toparlanma_var,
                        'suphe_skoru': round(suphe_skoru, 1),
                        'surekli_dusuk_ay_sayisi': dusuk_ay_sayisi,
                        'yillik_tasarruf_tahmini': round((onceki_ort_tuketim - sonraki_donem['tuketim'].mean()) * 12, 2)
                    })
            
            if tesisat_supheleri:
                en_supheli = max(tesisat_supheleri, key=lambda x: x['suphe_skoru'])
                supheliler.append(en_supheli)
    
    progress_bar.empty()
    status_text.empty()
    
    result_df = pd.DataFrame(supheliler)
    if len(result_df) > 0:
        result_df = result_df.sort_values('suphe_skoru', ascending=False)
    
    return result_df

# ============================================================================
# GÖRSELLEŞTİRME FONKSİYONLARI
# ============================================================================

def plot_bina_karsilastirma(df, tesisat_id, kirilma_tarihi):
    """Plotly ile interaktif bina karşılaştırma grafikleri"""
    
    tesisat_df = df[df['tesisat'] == tesisat_id].copy()
    if len(tesisat_df) == 0:
        return None, None
    
    bina_no = tesisat_df['bina_numarasi'].iloc[0]
    bina_df = df[df['bina_numarasi'] == bina_no].copy()
    
    bina_df['tarih_dt'] = pd.to_datetime(bina_df['tarih'])
    kirilma_dt = pd.to_datetime(kirilma_tarihi)
    
    # Grafik 1: Tüm daireler
    fig1 = go.Figure()
    
    for t in bina_df['tesisat'].unique():
        t_data = bina_df[bina_df['tesisat'] == t].sort_values('tarih_dt')
        if t == tesisat_id:
            fig1.add_trace(go.Scatter(
                x=t_data['tarih_dt'], 
                y=t_data['tuketim'],
                mode='lines+markers',
                name=f'Tesisat {t} (ŞÜPHELİ)',
                line=dict(color='red', width=3)
            ))
        else:
            fig1.add_trace(go.Scatter(
                x=t_data['tarih_dt'], 
                y=t_data['tuketim'],
                mode='lines+markers',
                name=f'Tesisat {t}',
                line=dict(width=1),
                opacity=0.3
            ))
    
    fig1.add_vline(x=kirilma_dt, line_dash="dash", line_color="black", 
                   annotation_text="Kırılma Noktası", annotation_position="top")
    fig1.update_layout(
        title=f'Bina {bina_no} - Tüm Daireler Zaman Serisi',
        xaxis_title='Tarih',
        yaxis_title='Tüketim (m³)',
        hovermode='closest',
        height=450
    )
    
    # Grafik 2: Şüpheli vs Bina Ortalaması
    fig2 = go.Figure()
    
    tesisat_data = bina_df[bina_df['tesisat'] == tesisat_id].sort_values('tarih_dt')
    diger_data = bina_df[bina_df['tesisat'] != tesisat_id].groupby('tarih_dt')['tuketim'].mean().reset_index()
    
    fig2.add_trace(go.Scatter(
        x=tesisat_data['tarih_dt'], 
        y=tesisat_data['tuketim'],
        mode='lines+markers',
        name='Şüpheli Tesisat',
        line=dict(color='red', width=2),
        fill='tozeroy',
        fillcolor='rgba(255,0,0,0.1)'
    ))
    
    fig2.add_trace(go.Scatter(
        x=diger_data['tarih_dt'], 
        y=diger_data['tuketim'],
        mode='lines+markers',
        name='Bina Ortalaması',
        line=dict(color='blue', width=2),
        fill='tozeroy',
        fillcolor='rgba(0,0,255,0.1)'
    ))
    
    fig2.add_vline(x=kirilma_dt, line_dash="dash", line_color="black",
                   annotation_text="Kırılma", annotation_position="top")
    fig2.update_layout(
        title='Şüpheli Daire vs Bina Ortalaması',
        xaxis_title='Tarih',
        yaxis_title='Tüketim (m³)',
        hovermode='x unified',
        height=450
    )
    
    return fig1, fig2

def create_summary_charts(supheliler_df):
    """Özet grafikler oluştur"""
    
    if len(supheliler_df) == 0:
        return None, None, None
    
    # Grafik 1: Şüphe Skoru Dağılımı
    fig1 = px.histogram(
        supheliler_df, 
        x='suphe_skoru',
        nbins=20,
        title='Şüphe Skoru Dağılımı',
        labels={'suphe_skoru': 'Şüphe Skoru', 'count': 'Tesisat Sayısı'},
        color_discrete_sequence=['#ff4b4b']
    )
    fig1.add_vline(x=70, line_dash="dash", line_color="red", 
                   annotation_text="Yüksek Risk", annotation_position="top right")
    fig1.add_vline(x=50, line_dash="dash", line_color="orange",
                   annotation_text="Orta Risk", annotation_position="top right")
    
    # Grafik 2: Düşüş Oranı vs Z-Score Kayma
    fig2 = px.scatter(
        supheliler_df,
        x='genel_dusus_orani',
        y='z_kayma',
        size='suphe_skoru',
        color='ters_yonlu',
        hover_data=['tesisat', 'bina_numarasi'],
        title='Düşüş Oranı vs Bina İçi Sapma',
        labels={
            'genel_dusus_orani': 'Genel Düşüş Oranı (%)',
            'z_kayma': 'Z-Score Kayma',
            'ters_yonlu': 'Ters Yönlü Hareket'
        },
        color_discrete_map={'EVET': 'red', 'Hayır': 'blue'}
    )
    
    # Grafik 3: Bina bazlı özet
    bina_stats = supheliler_df.groupby('bina_numarasi').agg({
        'tesisat': 'count',
        'suphe_skoru': 'mean',
        'yillik_tasarruf_tahmini': 'sum'
    }).reset_index()
    bina_stats.columns = ['Bina', 'Şüpheli Sayısı', 'Ort. Şüphe Skoru', 'Toplam Tahmini Tasarruf']
    
    fig3 = px.bar(
        bina_stats.sort_values('Şüpheli Sayısı', ascending=False).head(15),
        x='Bina',
        y='Şüpheli Sayısı',
        title='En Fazla Şüpheli İçeren 15 Bina',
        labels={'Şüpheli Sayısı': 'Tespit Sayısı'},
        color='Ort. Şüphe Skoru',
        color_continuous_scale='Reds'
    )
    
    return fig1, fig2, fig3

# ============================================================================
# VERİ YÜKLEME
# ============================================================================

st.header("📂 Veri Yükleme")

uploaded_file = st.file_uploader(
    "Excel veya CSV dosyası yükleyin",
    type=['xlsx', 'xls', 'csv'],
    help="Dosya şu kolonları içermelidir: tarih, tesisat, bina_numarasi, tuketim"
)

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        # Veri doğrulama
        valid, message = validate_dataframe(df)
        
        if not valid:
            st.error(f"❌ Veri hatası: {message}")
            st.stop()
        
        st.success(f"✅ {message}")
    
    except Exception as e:
        st.error(f"❌ Dosya okuma hatası: {str(e)}")
        st.stop()
    
    # Veri önizleme
    with st.expander("🔍 Veri Önizleme", expanded=False):
        st.dataframe(df.head(20), use_container_width=True)
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Kayıt", len(df))
        col2.metric("Tesisat Sayısı", df['tesisat'].nunique())
        col3.metric("Bina Sayısı", df['bina_numarasi'].nunique())
        col4.metric("Tarih Aralığı", f"{df['tarih'].min()} - {df['tarih'].max()}")
    
    st.markdown("---")
    
    # ============================================================================
    # ANALİZ
    # ============================================================================
    
    if st.button("🚀 Analizi Başlat", type="primary", use_container_width=True):
        
        params = {
            'min_dusus': MIN_DUSUS_ORANI,
            'max_dusus': MAX_DUSUS_ORANI,
            'min_sureklilik': MIN_SUREKLILIK_AY,
            'min_bina_daire': MIN_BINA_DAIRE_SAYISI,
            'z_esik': BINA_SAPMA_ESIGI,
            'sadece_ters_yonlu': SADECE_TERS_YONLU,
            'min_onceki_tuketim': MIN_ONCEKI_TUKETIM
        }
        
        with st.spinner("🔍 Analiz yapılıyor..."):
            supheliler_df = tespit_et_sayac_mudehalesi_bina_bazli(df, params)
            
            if len(supheliler_df) == 0:
                st.warning("⚠️ Belirlenen kriterlere göre şüpheli durum tespit edilemedi.")
                st.info("💡 Parametreleri gevşeterek tekrar deneyebilirsiniz.")
            else:
                st.success(f"✅ **{len(supheliler_df)} adet şüpheli tesisat tespit edildi!**")
                
                # ============================================================================
                # ÖZET İSTATİSTİKLER
                # ============================================================================
                
                st.header("📊 Özet İstatistikler")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        "Toplam Şüpheli",
                        len(supheliler_df),
                        delta=f"{len(supheliler_df)/df['tesisat'].nunique()*100:.1f}%",
                        delta_color="inverse"
                    )
                
                with col2:
                    yuksek_risk = len(supheliler_df[supheliler_df['suphe_skoru'] >= 70])
                    st.metric(
                        "Yüksek Risk (≥70)",
                        yuksek_risk,
                        delta=f"{yuksek_risk/len(supheliler_df)*100:.0f}%" if len(supheliler_df) > 0 else "0%"
                    )
                
                with col3:
                    ters_yonlu_sayisi = len(supheliler_df[supheliler_df['ters_yonlu'] == 'EVET'])
                    st.metric(
                        "Ters Yönlü Hareket",
                        ters_yonlu_sayisi,
                        delta=f"{ters_yonlu_sayisi/len(supheliler_df)*100:.0f}%" if len(supheliler_df) > 0 else "0%"
                    )
                
                with col4:
                    toplam_tasarruf = supheliler_df['yillik_tasarruf_tahmini'].sum()
                    st.metric(
                        "Toplam Tahmini Tasarruf",
                        f"{toplam_tasarruf:,.0f} m³",
                        delta="Yıllık"
                    )
                
                st.markdown("---")
                
                # ============================================================================
                # ÖZET GRAFİKLER
                # ============================================================================
                
                st.header("📈 Genel Analizler")
                
                fig1, fig2, fig3 = create_summary_charts(supheliler_df)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.plotly_chart(fig1, use_container_width=True)
                with col2:
                    st.plotly_chart(fig2, use_container_width=True)
                
                st.plotly_chart(fig3, use_container_width=True)
                
                st.markdown("---")
                
                # ============================================================================
                # DETAYLI SONUÇLAR
                # ============================================================================
                
                st.header("🔍 Detaylı Sonuçlar")
                
                # Risk seviyesi filtreleme
                risk_filter = st.selectbox(
                    "Risk Seviyesi Filtresi",
                    ["Tümü", "Yüksek Risk (≥70)", "Orta Risk (50-70)", "Düşük Risk (<50)"]
                )
                
                filtered_df = supheliler_df.copy()
                if risk_filter == "Yüksek Risk (≥70)":
                    filtered_df = filtered_df[filtered_df['suphe_skoru'] >= 70]
                elif risk_filter == "Orta Risk (50-70)":
                    filtered_df = filtered_df[(filtered_df['suphe_skoru'] >= 50) & (filtered_df['suphe_skoru'] < 70)]
                elif risk_filter == "Düşük Risk (<50)":
                    filtered_df = filtered_df[filtered_df['suphe_skoru'] < 50]
                
                # Renklendirme fonksiyonu
                def color_risk(val):
                    if val >= 70:
                        return 'background-color: #ff4b4b; color: white; font-weight: bold'
                    elif val >= 50:
                        return 'background-color: #ffa500; color: white'
                    else:
                        return 'background-color: #90ee90'
                
                # Tablo gösterimi
                display_df = filtered_df[[
                    'tesisat', 'bina_numarasi', 'suphe_skoru', 'kirilma_tarihi',
                    'genel_dusus_orani', 'kis_dusus', 'yaz_dusus', 'z_kayma',
                    'ters_yonlu', 'yillik_tasarruf_tahmini'
                ]].copy()
                
                display_df.columns = [
                    'Tesisat', 'Bina', 'Şüphe Skoru', 'Kırılma Tarihi',
                    'Düşüş (%)', 'Kış Düşüş (%)', 'Yaz Düşüş (%)', 'Z-Kayma',
                    'Ters Yönlü', 'Yıllık Tasarruf (m³)'
                ]
                
                st.dataframe(
                    display_df.style.applymap(color_risk, subset=['Şüphe Skoru']),
                    use_container_width=True,
                    height=400
                )
                
                # ============================================================================
                # TEK TEK GRAFİKLER
                # ============================================================================
                
                st.markdown("---")
                st.header("🔬 Tesisat Bazlı Detaylı Analiz")
                
                selected_tesisat = st.selectbox(
                    "İncelemek istediğiniz tesisatı seçin:",
                    filtered_df['tesisat'].tolist(),
                    format_func=lambda x: f"Tesisat {x} (Şüphe: {filtered_df[filtered_df['tesisat']==x]['suphe_skoru'].iloc[0]})"
                )
                
                if selected_tesisat:
                    tesisat_row = filtered_df[filtered_df['tesisat'] == selected_tesisat].iloc[0]
                    
                    # Bilgi kartları
                    st.subheader(f"📋 Tesisat {selected_tesisat} - Detay Bilgiler")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Bina Numarası", tesisat_row['bina_numarasi'])
                        st.metric("Kırılma Tarihi", tesisat_row['kirilma_tarihi'])
                    
                    with col2:
                        st.metric("Şüphe Skoru", f"{tesisat_row['suphe_skoru']:.1f}")
                        st.metric("Genel Düşüş", f"{tesisat_row['genel_dusus_orani']:.1f}%")
                    
                    with col3:
                        st.metric("Kış Düşüş", f"{tesisat_row['kis_dusus']:.1f}%")
                        st.metric("Yaz Düşüş", f"{tesisat_row['yaz_dusus']:.1f}%")
                    
                    with col4:
                        st.metric("Z-Score Kayma", f"{tesisat_row['z_kayma']:.2f}")
                        st.metric("Ters Yönlü", tesisat_row['ters_yonlu'])
                    
                    # Grafikler
                    fig1, fig2 = plot_bina_karsilastirma(
                        df, 
                        selected_tesisat, 
                        tesisat_row['kirilma_tarihi']
                    )
                    
                    if fig1 and fig2:
                        st.plotly_chart(fig1, use_container_width=True)
                        st.plotly_chart(fig2, use_container_width=True)
                    
                    # Ek bilgiler
                    with st.expander("📊 Ek Detaylar"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write("**Tüketim Bilgileri:**")
                            st.write(f"- Önceki Ort. Tüketim: {tesisat_row['onceki_ort_tuketim']:.2f} m³")
                            st.write(f"- Sonraki Ort. Tüketim: {tesisat_row['sonraki_ort_tuketim']:.2f} m³")
                            st.write(f"- Yıllık Tasarruf: {tesisat_row['yillik_tasarruf_tahmini']:.2f} m³")
                        
                        with col2:
                            st.write("**Z-Score Analizi:**")
                            st.write(f"- Önceki Z-Score: {tesisat_row['onceki_z_score']:.2f}")
                            st.write(f"- Sonraki Z-Score: {tesisat_row['sonraki_z_score']:.2f}")
                            st.write(f"- Bina Trend: {tesisat_row['bina_trend']:.1f}%")
                            st.write(f"- Sürekli Düşük Ay: {tesisat_row['surekli_dusuk_ay_sayisi']}")
                
                # ============================================================================
                # EXCEL EXPORT
                # ============================================================================
                
                st.markdown("---")
                st.header("💾 Rapor İndirme")
                
                # Excel'e yazma
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    supheliler_df.to_excel(writer, sheet_name='Tüm Sonuçlar', index=False)
                    
                    if len(supheliler_df[supheliler_df['suphe_skoru'] >= 70]) > 0:
                        supheliler_df[supheliler_df['suphe_skoru'] >= 70].to_excel(
                            writer, sheet_name='Yüksek Risk', index=False
                        )
                    
                    # Özet istatistikler
                    summary = pd.DataFrame({
                        'Metrik': [
                            'Toplam Şüpheli',
                            'Yüksek Risk (≥70)',
                            'Orta Risk (50-70)',
                            'Düşük Risk (<50)',
                            'Ters Yönlü Hareket',
                            'Toplam Tahmini Tasarruf (m³/yıl)'
                        ],
                        'Değer': [
                            len(supheliler_df),
                            len(supheliler_df[supheliler_df['suphe_skoru'] >= 70]),
                            len(supheliler_df[(supheliler_df['suphe_skoru'] >= 50) & (supheliler_df['suphe_skoru'] < 70)]),
                            len(supheliler_df[supheliler_df['suphe_skoru'] < 50]),
                            len(supheliler_df[supheliler_df['ters_yonlu'] == 'EVET']),
                            round(supheliler_df['yillik_tasarruf_tahmini'].sum(), 2)
                        ]
                    })
                    summary.to_excel(writer, sheet_name='Özet', index=False)
                
                excel_data = output.getvalue()
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.download_button(
                        label="📥 Detaylı Rapor İndir (Excel)",
                        data=excel_data,
                        file_name=f"sayac_mudahale_raporu_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                
                with col2:
                    csv_data = supheliler_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📥 Sonuçları İndir (CSV)",
                        data=csv_data,
                        file_name=f"sayac_mudahale_sonuclar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
else:
    st.info("👆 Lütfen analiz için bir veri dosyası yükleyin.")
    
    st.markdown("### 📋 Veri Formatı")
    st.markdown("""
    Yüklediğiniz dosya şu kolonları içermelidir:
    
    | Kolon | Açıklama | Örnek |
    |-------|----------|-------|
    | `tarih` | Tüketim tarihi (YYYY-MM formatında) | 2023-01 |
    | `tesisat` | Tesisat numarası | 12345 |
    | `bina_numarasi` | Bina numarası | 100 |
    | `tuketim` | Tüketim miktarı (m³) | 150.5 |
    """)
    
    # Örnek veri göster
    st.markdown("### 📊 Örnek Veri")
    example_data = pd.DataFrame({
        'tarih': ['2023-01', '2023-02', '2023-03', '2023-04'],
        'tesisat': [12345, 12345, 12345, 12345],
        'bina_numarasi': [100, 100, 100, 100],
        'tuketim': [150.5, 145.2, 140.8, 135.3]
    })
    st.dataframe(example_data, use_container_width=True)

# ============================================================================
# FOOTER
# ============================================================================
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p><strong>Doğalgaz Sayaç Müdahale Tespit Sistemi v1.0</strong></p>
    <p>Geliştirilme Tarihi: 2025 | Powered by Streamlit</p>
</div>
""", unsafe_allow_html=True)
