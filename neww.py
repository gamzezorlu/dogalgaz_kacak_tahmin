import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

# Sayfa konfigürasyonu
st.set_page_config(
    page_title="Doğalgaz Tüketim Anomali Tespit",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 Doğalgaz Tüketim Anomali Tespit Sistemi")
st.markdown("---")

# Yan panel - Dosya yükleme
st.sidebar.header("📁 Dosya Yükleme")
uploaded_file = st.sidebar.file_uploader(
    "CSV veya Excel dosyası seçin",
    type=['csv', 'xlsx', 'xls'],
    help="Tesisat numarası, bina numarası ve aylık tüketim verilerini içeren dosya"
)

# Parametreler
st.sidebar.header("⚙️ Analiz Parametreleri")
kis_tuketim_esigi = st.sidebar.slider(
    "Kış ayı düşük tüketim eşiği (m³/ay)",
    min_value=10, max_value=100, value=50,
    help="Kış aylarında bu değerin altındaki tüketim şüpheli kabul edilir"
)

bina_ort_dusuk_oran = st.sidebar.slider(
    "Bina ortalamasından düşük olma oranı (%)",
    min_value=30, max_value=90, value=60,
    help="Bina ortalamasından bu oranda düşük tüketim şüpheli kabul edilir"
)

ani_dusus_orani = st.sidebar.slider(
    "Ani düşüş oranı (%)",
    min_value=40, max_value=90, value=70,
    help="Önceki kış aylarına göre bu oranda düşüş şüpheli kabul edilir"
)

min_onceki_kis_tuketim = st.sidebar.slider(
    "Minimum önceki kış tüketimi (m³)",
    min_value=50, max_value=200, value=80,
    help="Ani düşüş tespiti için önceki kış aylarında minimum tüketim"
)

def load_data(file):
    """Dosyayı yükle ve virgüllü formatı düzelt"""
    try:
        if file.name.endswith('.csv'):
            # CSV için önce virgüllü format dene
            try:
                df = pd.read_csv(file, sep='\t', decimal=',', thousands='.')
            except:
                try:
                    df = pd.read_csv(file, decimal=',')
                except:
                    df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # Kolon isimlerini temizle
        df.columns = df.columns.str.strip()
        
        # Tarih kolonlarını tespit et ve virgüllü değerleri düzelt
        date_cols, _ = parse_date_columns(df)
        
        for col in date_cols:
            if df[col].dtype == 'object':
                # Virgüllü string değerleri noktalıya çevir
                df[col] = df[col].astype(str).str.replace(',', '.').str.strip()
                # Boş string ve 'nan' değerlerini NaN yap
                df[col] = df[col].replace(['', 'nan', 'None'], np.nan)
                # Numeric'e çevir
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    except Exception as e:
        st.error(f"Dosya yükleme hatası: {str(e)}")
        return None

def parse_date_columns(df):
    """Tarih sütunlarını parse et"""
    date_columns = []
    other_columns = []
    
    for col in df.columns:
        if isinstance(col, str) and '/' in col:
            try:
                parts = col.split('/')
                if len(parts) == 2:
                    year, month = parts
                    if len(year) == 4 and len(month) <= 2 and year.isdigit() and month.isdigit():
                        date_columns.append(col)
                    else:
                        other_columns.append(col)
                else:
                    other_columns.append(col)
            except:
                other_columns.append(col)
        else:
            other_columns.append(col)
    
    return date_columns, other_columns

def get_season(month):
    """Ayı mevsime göre kategorize et"""
    if month in [12, 1, 2]:
        return "Kış"
    elif month in [3, 4, 5]:
        return "İlkbahar"
    elif month in [6, 7, 8]:
        return "Yaz"
    else:
        return "Sonbahar"

def analyze_consumption_patterns(df, date_columns, tesisat_col, bina_col):
    """Tüketim paternlerini analiz et - İYİLEŞTİRİLMİŞ"""
    results = []
    
    for idx, row in df.iterrows():
        tesisat_no = row[tesisat_col]
        bina_no = row[bina_col]
        
        # Aylık tüketim verilerini al
        consumption_data = []
        for date_col in date_columns:
            try:
                value = row[date_col]
                if pd.notna(value) and value != '':
                    year, month = date_col.split('/')
                    cons_value = float(value) if float(value) > 0 else 0
                    consumption_data.append({
                        'year': int(year),
                        'month': int(month),
                        'consumption': cons_value,
                        'season': get_season(int(month)),
                        'date_str': date_col
                    })
            except Exception as e:
                continue
        
        if len(consumption_data) < 6:  # En az 6 ay veri olmalı
            continue
        
        # DataFrame'e çevir ve tarihine göre sırala
        cons_df = pd.DataFrame(consumption_data)
        cons_df = cons_df.sort_values(['year', 'month'])
        
        # Mevsimsel ortalamalar (sıfır olmayan değerler için)
        seasonal_avg = cons_df[cons_df['consumption'] > 0].groupby('season')['consumption'].mean()
        
        # Kış ayı tüketimi kontrolü
        kis_tuketim = seasonal_avg.get('Kış', 0)
        yaz_tuketim = seasonal_avg.get('Yaz', 0)
        
        # Anomali tespiti
        anomalies = []
        
        # 1. Kış ayı düşük tüketim
        if 0 < kis_tuketim < kis_tuketim_esigi:
            anomalies.append(f"Kış ayı düşük tüketim: {kis_tuketim:.1f} m³/ay")
        
        # 2. Kış-yaz tüketim farkı normal değil
        if kis_tuketim > 0 and yaz_tuketim > 0:
            if abs(kis_tuketim - yaz_tuketim) < 10:
                anomalies.append(f"Kış-yaz tüketim farkı az: Kış {kis_tuketim:.1f}, Yaz {yaz_tuketim:.1f}")
        
        # 3. Toplam tüketim çok düşük
        total_consumption = cons_df['consumption'].sum()
        avg_monthly = total_consumption / len(cons_df) if len(cons_df) > 0 else 0
        
        if 0 < total_consumption < 500:  # Çok düşük toplam tüketim
            anomalies.append(f"Toplam tüketim çok düşük: {total_consumption:.1f} m³")
        
        # 4. Düzenli sıfır tüketim
        zero_months = len(cons_df[cons_df['consumption'] == 0])
        if zero_months > 6:
            anomalies.append(f"Çok fazla sıfır tüketim: {zero_months} ay")
        
        # 5. ANI DÜŞÜŞ TESPİTİ - GELİŞTİRİLMİŞ MANTIK
        kis_aylari = cons_df[cons_df['season'] == 'Kış'].copy()
        
        if len(kis_aylari) >= 3:
            # Kış sezonunu düzgün grupla: Aralık ayını bir sonraki yıla ata
            kis_aylari['kis_yili'] = kis_aylari.apply(
                lambda row: row['year'] if row['month'] in [1, 2] else row['year'] + 1, 
                axis=1
            )
            
            # Yıllara göre kış aylarını grupla ve ortalama al
            kis_yillik = kis_aylari.groupby('kis_yili').agg({
                'consumption': ['mean', 'count']
            })
            kis_yillik.columns = ['ort_tuketim', 'ay_sayisi']
            
            # En az 2 ay verisi olan kış sezonlarını al
            kis_yillik = kis_yillik[kis_yillik['ay_sayisi'] >= 2]
            
            # Sıfır olmayan ortalamaları al
            yillik_ortalamalar = kis_yillik[kis_yillik['ort_tuketim'] > 0]['ort_tuketim']
            
            if len(yillik_ortalamalar) >= 2:
                yillar = sorted(yillik_ortalamalar.index)
                
                # TÜM yıllar arası düşüşleri kontrol et
                for i in range(1, len(yillar)):
                    onceki_yil = yillar[i-1]
                    mevcut_yil = yillar[i]
                    
                    onceki_tuketim = yillik_ortalamalar[onceki_yil]
                    mevcut_tuketim = yillik_ortalamalar[mevcut_yil]
                    
                    # Önceki kış yüksek tüketim ve ani düşüş kontrolü
                    if onceki_tuketim >= min_onceki_kis_tuketim:
                        dusus_orani = ((onceki_tuketim - mevcut_tuketim) / onceki_tuketim) * 100
                        
                        if dusus_orani >= ani_dusus_orani:
                            anomalies.append(
                                f"🚨 ANI KIŞ DÜŞÜŞÜ: {onceki_yil-1}/{onceki_yil} kışı "
                                f"({onceki_tuketim:.1f} m³) → {mevcut_yil-1}/{mevcut_yil} kışı "
                                f"({mevcut_tuketim:.1f} m³), %{dusus_orani:.0f} DÜŞÜŞ"
                            )
        
        # 6. Bina ortalaması kontrolü
        bina_tesisatlari = df[df[bina_col] == bina_no]
        if len(bina_tesisatlari) > 1:
            bina_tuketimleri = []
            for _, bina_row in bina_tesisatlari.iterrows():
                bina_toplam = 0
                bina_ay_sayisi = 0
                for date_col in date_columns:
                    try:
                        val = bina_row[date_col]
                        if pd.notna(val) and val != '' and float(val) > 0:
                            bina_toplam += float(val)
                            bina_ay_sayisi += 1
                    except:
                        continue
                
                if bina_ay_sayisi > 0:
                    bina_tuketimleri.append(bina_toplam / bina_ay_sayisi)
            
            if len(bina_tuketimleri) > 1:
                bina_ortalaması = np.mean(bina_tuketimleri)
                mevcut_ortalama = avg_monthly
                
                if mevcut_ortalama > 0 and mevcut_ortalama < bina_ortalaması * (1 - bina_ort_dusuk_oran/100):
                    fark_orani = ((bina_ortalaması - mevcut_ortalama) / bina_ortalaması) * 100
                    anomalies.append(f"Bina ortalamasından %{fark_orani:.0f} düşük: {mevcut_ortalama:.1f} vs {bina_ortalaması:.1f}")
        
        # Kış trendi analizi
        kis_trend = "Stabil"
        if len(kis_aylari) >= 3 and 'kis_yili' in kis_aylari.columns:
            kis_yillik_trend = kis_aylari.groupby('kis_yili')['consumption'].mean()
            yillik_ort_trend = kis_yillik_trend[kis_yillik_trend > 0]
            
            if len(yillik_ort_trend) >= 2:
                yillar_trend = sorted(yillik_ort_trend.index)
                ilk_yil = yillik_ort_trend[yillar_trend[0]]
                son_yil = yillik_ort_trend[yillar_trend[-1]]
                
                dusus_yuzdesi = ((ilk_yil - son_yil) / ilk_yil) * 100
                
                if son_yil < ilk_yil * 0.3:  # %70+ düşüş
                    kis_trend = "Şiddetli Düşüş"
                elif son_yil < ilk_yil * 0.5:  # %50+ düşüş
                    kis_trend = "Orta Düşüş"
                elif son_yil < ilk_yil * 0.7:  # %30+ düşüş
                    kis_trend = "Hafif Düşüş"
                elif son_yil > ilk_yil * 1.5:  # %50+ artış
                    kis_trend = "Artış"
        
        # Sonuçları kaydet
        results.append({
            'tesisat_no': tesisat_no,
            'bina_no': bina_no,
            'kis_tuketim': kis_tuketim,
            'yaz_tuketim': yaz_tuketim,
            'toplam_tuketim': total_consumption,
            'ortalama_tuketim': avg_monthly,
            'kis_trend': kis_trend,
            'anomali_sayisi': len(anomalies),
            'anomaliler': '; '.join(anomalies) if anomalies else 'Normal',
            'suspicion_level': 'Şüpheli' if anomalies else 'Normal'
        })
    
    return pd.DataFrame(results)

def create_visualizations(results_df, original_df, date_columns):
    """Görselleştirmeler oluştur"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        # 1. Anomali dağılımı
        fig1 = px.histogram(
            results_df, 
            x='anomali_sayisi',
            title="Anomali Sayısı Dağılımı",
            color_discrete_sequence=['#FF6B6B'],
            labels={'anomali_sayisi': 'Anomali Sayısı', 'count': 'Tesisat Sayısı'}
        )
        st.plotly_chart(fig1, use_container_width=True)
    
    with col2:
        # 2. Şüpheli vs Normal dağılımı
        suspicion_counts = results_df['suspicion_level'].value_counts()
        fig2 = px.pie(
            values=suspicion_counts.values,
            names=suspicion_counts.index,
            title="Şüpheli vs Normal Tesisatlar",
            color_discrete_map={'Şüpheli': '#FF6B6B', 'Normal': '#4ECDC4'}
        )
        st.plotly_chart(fig2, use_container_width=True)
    
    # 3. Kış Trend Analizi
    trend_counts = results_df['kis_trend'].value_counts()
    fig3 = px.bar(
        x=trend_counts.index,
        y=trend_counts.values,
        title="Kış Ayı Tüketim Trend Analizi",
        color=trend_counts.values,
        color_continuous_scale='Reds',
        labels={'x': 'Trend', 'y': 'Tesisat Sayısı'}
    )
    fig3.update_layout(showlegend=False)
    st.plotly_chart(fig3, use_container_width=True)
    
    # 4. Kış vs Yaz tüketim karşılaştırması
    fig4 = px.scatter(
        results_df,
        x='yaz_tuketim',
        y='kis_tuketim',
        color='suspicion_level',
        size='anomali_sayisi',
        title="Kış vs Yaz Tüketim Karşılaştırması",
        labels={'yaz_tuketim': 'Yaz Tüketimi (m³)', 'kis_tuketim': 'Kış Tüketimi (m³)'},
        color_discrete_map={'Şüpheli': '#FF6B6B', 'Normal': '#4ECDC4'},
        hover_data=['tesisat_no', 'kis_trend']
    )
    
    # Normal pattern çizgisi
    max_val = max(results_df['yaz_tuketim'].max(), results_df['kis_tuketim'].max())
    fig4.add_trace(go.Scatter(
        x=[0, max_val],
        y=[0, max_val],
        mode='lines',
        name='Eşit Tüketim Çizgisi',
        line=dict(dash='dash', color='gray')
    ))
    
    st.plotly_chart(fig4, use_container_width=True)
    
    # 5. Trend bazında anomali dağılımı
    trend_anomali = results_df.groupby(['kis_trend', 'suspicion_level']).size().reset_index(name='count')
    fig5 = px.bar(
        trend_anomali,
        x='kis_trend',
        y='count',
        color='suspicion_level',
        title="Trend Bazında Anomali Dağılımı",
        color_discrete_map={'Şüpheli': '#FF6B6B', 'Normal': '#4ECDC4'},
        labels={'kis_trend': 'Kış Trendi', 'count': 'Tesisat Sayısı'}
    )
    st.plotly_chart(fig5, use_container_width=True)

# Ana uygulama
if uploaded_file is not None:
    df = load_data(uploaded_file)
    
    if df is not None:
        st.success("✅ Dosya başarıyla yüklendi!")
        
        # Veri önizleme
        with st.expander("📊 Veri Önizleme"):
            st.dataframe(df.head(10))
        
        # Sütun seçimi
        st.subheader("🔧 Sütun Seçimi")
        
        date_columns, other_columns = parse_date_columns(df)
        
        col1, col2 = st.columns(2)
        
        with col1:
            tesisat_col = st.selectbox(
                "Tesisat Numarası Sütunu",
                options=other_columns,
                index=0 if len(other_columns) > 0 else None,
                help="Tesisat numarasını içeren sütunu seçin"
            )
        
        with col2:
            bina_col = st.selectbox(
                "Bina Numarası Sütunu",
                options=other_columns,
                index=1 if len(other_columns) > 1 else 0,
                help="Bina numarasını içeren sütunu seçin"
            )
        
        # Tarih sütunlarını göster
        st.info(f"✅ Tespit edilen tarih sütunları: **{len(date_columns)}** adet | "
                f"Tarih aralığı: **{min(date_columns)}** - **{max(date_columns)}**")
        
        # Analiz butonu
        if st.button("🔍 Anomali Analizini Başlat", type="primary", use_container_width=True):
            with st.spinner("Analiz yapılıyor..."):
                
                results_df = analyze_consumption_patterns(df, date_columns, tesisat_col, bina_col)
                
                if len(results_df) == 0:
                    st.error("❌ Analiz edilebilecek tesisat bulunamadı. Lütfen veri formatını kontrol edin.")
                else:
                    # Sonuçları göster
                    st.markdown("---")
                    st.subheader("📈 Analiz Sonuçları")
                    
                    # Özet istatistikler
                    col1, col2, col3, col4 = st.columns(4)
                    
                    suspicious_count = len(results_df[results_df['suspicion_level'] == 'Şüpheli'])
                    suspicious_rate = (suspicious_count / len(results_df)) * 100 if len(results_df) > 0 else 0
                    total_anomalies = results_df['anomali_sayisi'].sum()
                    
                    with col1:
                        st.metric("Toplam Tesisat", len(results_df))
                    
                    with col2:
                        st.metric("Şüpheli Tesisat", suspicious_count, 
                                 delta=f"%{suspicious_rate:.1f}" if suspicious_count > 0 else None,
                                 delta_color="inverse")
                    
                    with col3:
                        st.metric("Şüpheli Oran", f"{suspicious_rate:.1f}%")
                    
                    with col4:
                        st.metric("Toplam Anomali", int(total_anomalies))
                    
                    # Görselleştirmeler
                    st.markdown("---")
                    st.subheader("📊 Görselleştirmeler")
                    create_visualizations(results_df, df, date_columns)
                    
                    # Şüpheli tesisatlar
                    st.markdown("---")
                    st.subheader("🚨 Şüpheli Tesisatlar")
                    suspicious_df = results_df[results_df['suspicion_level'] == 'Şüpheli'].copy()
                    
                    if not suspicious_df.empty:
                        # Anomali sayısına göre sırala
                        suspicious_df = suspicious_df.sort_values('anomali_sayisi', ascending=False)
                        
                        display_cols = ['tesisat_no', 'bina_no', 'kis_tuketim', 'yaz_tuketim', 
                                       'ortalama_tuketim', 'kis_trend', 'anomali_sayisi', 'anomaliler']
                        
                        suspicious_display = suspicious_df[display_cols].copy()
                        suspicious_display.columns = ['Tesisat No', 'Bina No', 'Kış Tüketim', 
                                                    'Yaz Tüketim', 'Ortalama', 'Kış Trend',
                                                    'Anomali', 'Detaylar']
                        
                        # Formatting
                        for col in ['Kış Tüketim', 'Yaz Tüketim', 'Ortalama']:
                            suspicious_display[col] = suspicious_display[col].round(1)
                        
                        st.dataframe(
                            suspicious_display,
                            use_container_width=True,
                            hide_index=True,
                            height=400
                        )
                        
                        # Excel indirme
                        import io
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                            suspicious_display.to_excel(writer, index=False, sheet_name="Şüpheli Tesisatlar")
                        output.seek(0)
                        
                        st.download_button(
                            label="📥 Şüpheli Tesisatları İndir (EXCEL)",
                            data=output,
                            file_name="supheli_tesisatlar.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    else:
                        st.success("🎉 Şüpheli tesisat bulunamadı!")
                    
                    # Tüm sonuçlar
                    with st.expander("📋 Tüm Sonuçlar"):
                        filter_col1, filter_col2 = st.columns(2)
                        
                        with filter_col1:
                            suspicion_filter = st.selectbox(
                                "Şüpheli Durumu",
                                options=['Tümü', 'Şüpheli', 'Normal'],
                                index=0
                            )
                        
                        with filter_col2:
                            bina_list = ['Tümü'] + sorted([str(x) for x in results_df['bina_no'].unique()])
                            bina_filter = st.selectbox("Bina Numarası", options=bina_list, index=0)
                        
                        filtered_df = results_df.copy()
                        
                        if suspicion_filter != 'Tümü':
                            filtered_df = filtered_df[filtered_df['suspicion_level'] == suspicion_filter]
                        
                        if bina_filter != 'Tümü':
                            filtered_df = filtered_df[filtered_df['bina_no'].astype(str) == bina_filter]
                        
                        if not filtered_df.empty:
                            display_cols = ['tesisat_no', 'bina_no', 'kis_tuketim', 'yaz_tuketim', 
                                           'ortalama_tuketim', 'kis_trend', 'suspicion_level', 'anomaliler']
                            
                            filtered_display = filtered_df[display_cols].copy()
                            filtered_display.columns = ['Tesisat No', 'Bina No', 'Kış', 'Yaz', 
                                                       'Ortalama', 'Trend', 'Durum', 'Detaylar']
                            
                            for col in ['Kış', 'Yaz', 'Ortalama']:
                                filtered_display[col] = filtered_display[col].round(1)
                            
                            st.dataframe(filtered_display, use_container_width=True, hide_index=True)
                        else:
                            st.warning("Filtreye uygun veri bulunamadı.")

else:
    st.info("👈 Lütfen sol panelden bir dosya yükleyin")
    
    st.subheader("📄 Dosya Formatı")
    st.markdown("""
    **Gerekli Sütunlar:**
    - **Tesisat Numarası** (TN): Her tesisatın benzersiz kodu
    - **Bina Numarası** (BN): Binanın kimlik numarası  
    - **Tarih Sütunları**: `YYYY/M` veya `YYYY/MM` formatında (örn: `2024/1`, `2024/12`)
    - **Tüketim Değerleri**: Aylık doğalgaz tüketimi (m³) - Virgüllü veya noktalı format desteklenir
    
    **Desteklenen Formatlar:** CSV (Tab veya virgül ayraçlı), Excel (XLSX, XLS)
    """)

# Bilgi paneli
st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 Tespit Kriterleri")
st.sidebar.markdown(f"""
- 🔥 **Kış Düşük Tüketim**: < {kis_tuketim_esigi} m³/ay
- 📊 **Bina Ortalaması**: %{bina_ort_dusuk_oran} düşük
- 📉 **Ani Düşüş**: %{ani_dusus_orani}+ düşüş
- 🌡️ **Kış-Yaz Farkı**: < 10 m³ fark
- ⚠️ **Toplam Tüketim**: < 500 m³
- 🚫 **Sıfır Tüketim**: 6+ ay sıfır
""")
