"""
================================================================================
DOĞALGAZ SAYAÇ MÜDAHALESİ TESPİT SİSTEMİ
Versiyon: 2.0 - OPTIMIZE EDİLMİŞ
Geliştirilme Tarihi: 2025
================================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
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

st.sidebar.markdown("### ⚡ Performans Modu")
HIZLI_MOD = st.sidebar.checkbox(
    "Hızlı Mod (Önerilen)",
    value=True,
    help="Sadece çeyrek dönem başlarını kontrol et (4x daha hızlı)"
)

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
# ANA ANALİZ FONKSİYONU - OPTİMİZE EDİLMİŞ
# ============================================================================

@st.cache_data(show_spinner=False)
def tespit_et_sayac_mudehalesi_bina_bazli(df, params):
    """Ana tespit fonksiyonu - Optimize Edilmiş Versiyon"""
    
    df = df.copy()
    df['tarih_dt'] = pd.to_datetime(df['tarih'])
    df['yil'] = df['tarih_dt'].dt.year
    df['ay'] = df['tarih_dt'].dt.month
    df['mevsim'] = df['ay'].apply(mevsim_bul)
    df['yil_ay'] = df['tarih_dt'].dt.to_period('M')
    
    # Önce filtreleme yap - gereksiz veriyi eleme
    tesisat_ay_sayisi = df.groupby('tesisat').size()
    gecerli_tesisatlar = tesisat_ay_sayisi[tesisat_ay_sayisi >= 18].index
    df = df[df['tesisat'].isin(gecerli_tesisatlar)]
    
    bina_daire_sayisi = df.groupby('bina_numarasi')['tesisat'].nunique()
    gecerli_binalar = bina_daire_sayisi[bina_daire_sayisi >= params['min_bina_daire']].index
    df = df[df['bina_numarasi'].isin(gecerli_binalar)]
    
    st.info(f"📊 Filtreleme sonrası: {len(df):,} kayıt, {df['tesisat'].nunique():,} tesisat, {df['bina_numarasi'].nunique():,} bina")
    
    supheliler = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    binalar = df['bina_numarasi'].unique()
    total_binalar = len(binalar)
    
    # Kırılma aylarını belirle
    kirilma_aylari = [1, 4, 7, 10] if params['hizli_mod'] else list(range(1, 13))
    
    for bina_idx, bina_no in enumerate(binalar):
        if bina_idx % 10 == 0:  # Her 10 binada bir güncelle
            status_text.text(f"📊 Analiz ediliyor: Bina {bina_no} ({bina_idx+1}/{total_binalar})")
            progress_bar.progress((bina_idx + 1) / total_binalar)
        
        bina_df = df[df['bina_numarasi'] == bina_no].copy()
        daireler = bina_df['tesisat'].unique()
        
        for tesisat_id in daireler:
            tesisat_df = bina_df[bina_df['tesisat'] == tesisat_id].sort_values('tarih_dt').copy()
            
            # Diğer dairelerin ortalamasını hesapla (bu tesisatı hariç tut)
            diger_daireler = bina_df[bina_df['tesisat'] != tesisat_id]
            
            if len(diger_daireler) == 0:
                continue
            
            # Bina ortalaması (bu tesisat hariç) - grup bazlı hızlı hesaplama
            bina_ort_diger = diger_daireler.groupby('yil_ay').agg({
                'tuketim': ['mean', 'std']
            }).reset_index()
            bina_ort_diger.columns = ['yil_ay', 'bina_ort', 'bina_std']
            
            # Merge ile birleştir
            tesisat_df = tesisat_df.merge(bina_ort_diger, on='yil_ay', how='left')
            tesisat_df['z_score'] = (tesisat_df['tuketim'] - tesisat_df['bina_ort']) / (tesisat_df['bina_std'] + 1)
            
            yillar = sorted(tesisat_df['yil'].unique())
            
            if len(yillar) < 3:
                continue
            
            tesisat_supheleri = []
            
            # Kırılma noktalarını kontrol et
            for kirilma_yil in yillar[1:-1]:
                for kirilma_ay in kirilma_aylari:
                    
                    kirilma_tarihi = f"{kirilma_yil}-{kirilma_ay:02d}"
                    
                    if kirilma_tarihi not in tesisat_df['tarih'].values:
                        continue
                    
                    onceki_yil_start = pd.to_datetime(f"{kirilma_yil-1}-{kirilma_ay:02d}-01")
                    kirilma_dt = pd.to_datetime(f"{kirilma_yil}-{kirilma_ay:02d}-01")
                    
                    # Vektörizasyon ile dönem seçimi
                    onceki_mask = (tesisat_df['tarih_dt'] >= onceki_yil_start) & (tesisat_df['tarih_dt'] < kirilma_dt)
                    onceki_donem = tesisat_df[onceki_mask].copy()
                    
                    if len(onceki_donem) < 6:
                        continue
                    
                    onceki_ort_tuketim = onceki_donem['tuketim'].mean()
                    if onceki_ort_tuketim < params['min_onceki_tuketim']:
                        continue
                    
                    sonraki_donem_end = kirilma_dt + pd.DateOffset(months=12)
                    sonraki_mask = (tesisat_df['tarih_dt'] >= kirilma_dt) & (tesisat_df['tarih_dt'] < sonraki_donem_end)
                    sonraki_donem = tesisat_df[sonraki_mask].copy()
                    
                    if len(sonraki_donem) < 6:
                        continue
                    
                    # Mevsimsel analiz - vektörizasyon
                    onceki_ay_medyan = tesisat_df[tesisat_df['tarih_dt'] < kirilma_dt].groupby('ay')['tuketim'].median()
                    sonraki_donem['beklenen'] = sonraki_donem['ay'].map(onceki_ay_medyan)
                    
                    sonraki_donem['dusus_orani'] = (sonraki_donem['beklenen'] - sonraki_donem['tuketim']) / sonraki_donem['beklenen']
                    
                    # Sadece geçerli değerleri al
                    mevsimsel_dusus = sonraki_donem[sonraki_donem['beklenen'] > 10]['dusus_orani'].dropna()
                    
                    if len(mevsimsel_dusus) < 6:
                        continue
                    
                    dusuk_ay_sayisi = (mevsimsel_dusus >= params['min_dusus']).sum()
                    
                    if dusuk_ay_sayisi < params['min_sureklilik']:
                        continue
                    
                    ort_dusus = mevsimsel_dusus.mean()
                    std_dusus = mevsimsel_dusus.std()
                    
                    # Z-score hesaplamaları
                    onceki_z_ort = onceki_donem['z_score'].dropna().mean()
                    sonraki_z_ort = sonraki_donem['z_score'].dropna().mean()
                    z_kayma = onceki_z_ort - sonraki_z_ort
                    
                    # Bina trendi
                    bina_onceki_mask = (bina_ort_diger['yil_ay'] >= onceki_yil_start.to_period('M')) & \
                                       (bina_ort_diger['yil_ay'] < kirilma_dt.to_period('M'))
                    bina_onceki = bina_ort_diger[bina_onceki_mask]['bina_ort'].mean()
                    
                    bina_sonraki_mask = (bina_ort_diger['yil_ay'] >= kirilma_dt.to_period('M')) & \
                                        (bina_ort_diger['yil_ay'] < sonraki_donem_end.to_period('M'))
                    bina_sonraki = bina_ort_diger[bina_sonraki_mask]['bina_ort'].mean()
                    
                    bina_degisim = 0
                    if bina_onceki > 0:
                        bina_degisim = (bina_sonraki - bina_onceki) / bina_onceki
                    
                    # Hızlı filtreler
                    if not (params['min_dusus'] <= ort_dusus <= params['max_dusus']):
                        continue
                    
                    if std_dusus > 0.20:
                        continue
                    
                    if z_kayma < params['z_esik']:
                        continue
                    
                    ters_yonlu_hareket = (bina_degisim > 0.05 and ort_dusus > 0.15)
                    
                    if params['sadece_ters_yonlu'] and not ters_yonlu_hareket:
                        continue
                    
                    # Toparlanma kontrolü
                    toparlanma_var = False
                    if kirilma_yil + 2 in yillar:
                        gelecek_mask = tesisat_df['yil'] == kirilma_yil + 2
                        gelecek_yil_df = tesisat_df[gelecek_mask]
                        
                        if len(gelecek_yil_df) >= 6:
                            gelecek_z = gelecek_yil_df['z_score'].mean()
                            gelecek_tuketim = gelecek_yil_df['tuketim'].mean()
                            
                            if (abs(gelecek_z - onceki_z_ort) < 0.5 and
                                gelecek_tuketim > 0.9 * onceki_ort_tuketim):
                                toparlanma_var = True
                                continue
                    
                    # Mevsimsel düşüş detayları
                    kis_mask = sonraki_donem['mevsim'] == 'kis'
                    yaz_mask = sonraki_donem['mevsim'] == 'yaz'
                    
                    kis_dusus = sonraki_donem[kis_mask]['dusus_orani'].dropna()
                    yaz_dusus = sonraki_donem[yaz_mask]['dusus_orani'].dropna()
                    
                    kis_ort = kis_dusus.mean() * 100 if len(kis_dusus) > 0 else 0
                    yaz_ort = yaz_dusus.mean() * 100 if len(yaz_dusus) > 0 else 0
                    
                    if len(kis_dusus) > 0 and len(yaz_dusus) > 0:
                        if kis_ort < 15 or yaz_ort < 15:
                            continue
                    
                    # Şüphe skoru
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
                        'surekli_dusuk_ay_sayisi': int(dusuk_ay_sayisi),
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
