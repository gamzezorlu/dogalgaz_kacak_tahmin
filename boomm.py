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
    
    st.info(f"📊 Filtreleme sonrası: {len(df)} kayıt, {df['tesisat'].nunique()} tesisat, {df['bina_numarasi'].nunique()} bina")
    
    supheliler = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    binalar = df['bina_numarasi'].unique()
    total_binalar = len(binalar)
