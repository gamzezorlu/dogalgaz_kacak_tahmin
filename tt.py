import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Sayfa konfigürasyonu
st.set_page_config(
    page_title="Doğalgaz Kaçak Kullanım Tespit Sistemi",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 Doğalgaz Kaçak Kullanım Tespit Sistemi")
st.markdown("---")

# Sidebar
st.sidebar.header("📊 Analiz Parametreleri")

# Veri yükleme
uploaded_file = st.sidebar.file_uploader(
    "Excel veya CSV dosyanızı yükleyin",
    type=['xlsx', 'xls', 'csv'],
    help="Belge tarihi, Tüketim noktası, Başlangıç nesnesi, KWH Tüketim Sm3 kolonları içermeli"
)

def load_data(file):
    """Veri yükleme fonksiyonu - Çoklu kodlama desteği ile"""
    try:
        if file.name.endswith(('.xlsx', '.xls')):
            # Excel dosyaları için
            df = pd.read_excel(file, engine='openpyxl')
        else:
            # CSV dosyaları için farklı kodlamaları dene
            encodings = ['utf-8', 'utf-8-sig', 'iso-8859-9', 'windows-1254', 'cp1254', 'latin1']
            
            for encoding in encodings:
                try:
                    file.seek(0)  # Dosya pointer'ını başa al
                    df = pd.read_csv(file, encoding=encoding, sep=None, engine='python')
                    st.success(f"Dosya başarıyla yüklendi (Kodlama: {encoding})")
                    return df
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            
            # Hiçbiri işe yaramazsa son deneme
            file.seek(0)
            df = pd.read_csv(file, encoding='utf-8', errors='ignore', sep=None, engine='python')
            st.warning("Dosya yüklendi ancak bazı karakterler düzgün görüntülenmeyebilir.")
            
        return df
        
    except Exception as e:
        st.error(f"Dosya yüklenirken hata oluştu: {str(e)}")
        st.info("💡 **Çözüm önerileri:**")
        st.info("1. Excel dosyasını CSV olarak kaydedin (UTF-8 kodlaması ile)")
        st.info("2. Dosyada Türkçe karakter varsa, Excel'de 'Farklı Kaydet' > 'CSV UTF-8' seçin")
        st.info("3. Dosya adında Türkçe karakter bulunmamasına dikkat edin")
        return None

def detect_anomalies(df, tesis_id, method='iqr', threshold=2.5):
    """Anomali tespit fonksiyonları"""
    tesis_data = df[df['Tüketim noktası'] == tesis_id]['KWH Tüke Sm3'].values
    
    if len(tesis_data) < 3:
        return []
    
    anomalies = []
    
    if method == 'iqr':
        Q1 = np.percentile(tesis_data, 25)
        Q3 = np.percentile(tesis_data, 75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        
        for i, value in enumerate(tesis_data):
            if value < lower_bound or value > upper_bound:
                anomalies.append(i)
    
    elif method == 'zscore':
        mean = np.mean(tesis_data)
        std = np.std(tesis_data)
        
        for i, value in enumerate(tesis_data):
            z_score = abs((value - mean) / std)
            if z_score > threshold:
                anomalies.append(i)
    
    elif method == 'seasonal':
        # Mevsimsel analiz (basit yaklaşım)
        if len(tesis_data) >= 12:  # En az 1 yıllık veri
            seasonal_avg = {}
            for i, value in enumerate(tesis_data):
                month = (i % 12) + 1  # Ay numarası
                if month not in seasonal_avg:
                    seasonal_avg[month] = []
                seasonal_avg[month].append(value)
            
            # Her ay için ortalama hesapla
            for month in seasonal_avg:
                seasonal_avg[month] = np.mean(seasonal_avg[month])
            
            # Anomalileri tespit et
            for i, value in enumerate(tesis_data):
                month = (i % 12) + 1
                expected = seasonal_avg[month]
                if abs(value - expected) > expected * 0.5:  # %50 sapma
                    anomalies.append(i)
    
    return anomalies

def calculate_risk_score(df, tesis_id):
    """Risk skoru hesaplama"""
    tesis_data = df[df['Tüketim noktası'] == tesis_id].copy()
    
    if len(tesis_data) < 3:
        return 0
    
    tesis_data = tesis_data.sort_values('Belge tarihi')
    consumption = tesis_data['KWH Tüke Sm3'].values
    
    risk_factors = []
    
    # 1. Ani artışlar
    for i in range(1, len(consumption)):
        if consumption[i] > consumption[i-1] * 2:  # %100 artış
            risk_factors.append(3)
        elif consumption[i] > consumption[i-1] * 1.5:  # %50 artış
            risk_factors.append(2)
    
    # 2. Sıfır tüketim sonrası ani artış
    for i in range(1, len(consumption)):
        if consumption[i-1] == 0 and consumption[i] > np.mean(consumption):
            risk_factors.append(4)
    
    # 3. Düzensiz tüketim paterni
    cv = np.std(consumption) / np.mean(consumption) if np.mean(consumption) > 0 else 0
    if cv > 1.0:  # Yüksek varyasyon katsayısı
        risk_factors.append(2)
    
    # 4. Anomali sayısı
    anomalies_iqr = detect_anomalies(df, tesis_id, 'iqr')
    anomalies_zscore = detect_anomalies(df, tesis_id, 'zscore')
    
    total_anomalies = len(set(anomalies_iqr + anomalies_zscore))
    if total_anomalies > len(consumption) * 0.3:  # %30'dan fazla anomali
        risk_factors.append(3)
    elif total_anomalies > len(consumption) * 0.15:  # %15'den fazla anomali
        risk_factors.append(2)
    
    return min(sum(risk_factors), 10)  # Maksimum 10 risk skoru

if uploaded_file is not None:
    df = load_data(uploaded_file)
    
    if df is not None:
        # Kolon adlarını kontrol et ve düzelt
        expected_columns = ['Belge tarihi', 'Tüketim noktası', 'Başlangıç nesnesi', 'KWH Tüke Sm3']
        
        if not all(col in df.columns for col in expected_columns):
            st.error("❌ Dosyada gerekli kolonlar bulunamadı.")
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("🔍 Bulunan Kolonlar:")
                for i, col in enumerate(df.columns.tolist(), 1):
                    st.write(f"{i}. {col}")
            
            with col2:
                st.subheader("✅ Gerekli Kolonlar:")
                for col in expected_columns:
                    st.write(f"• {col}")
            
            st.info("💡 **Çözüm:** Kolon adlarınızı kontrol edin veya Excel'de başlık satırını düzenleyin")
            
            # Kolon eşleştirme seçeneği
            st.subheader("🔄 Manuel Kolon Eşleştirme")
            col_mapping = {}
            
            for req_col in expected_columns:
                selected_col = st.selectbox(
                    f"'{req_col}' için hangi kolonu kullanmak istiyorsunuz?",
                    options=[''] + df.columns.tolist(),
                    key=f"mapping_{req_col}"
                )
                if selected_col:
                    col_mapping[req_col] = selected_col
            
            if len(col_mapping) == len(expected_columns):
                if st.button("Eşleştirmeyi Uygula"):
                    # Kolonları yeniden adlandır
                    df_renamed = df.copy()
                    for new_name, old_name in col_mapping.items():
                        df_renamed = df_renamed.rename(columns={old_name: new_name})
                    df = df_renamed
                    st.success("✅ Kolon eşleştirmesi başarılı!")
                    st.experimental_rerun()
            else:
                st.warning("Tüm gerekli kolonları eşleştirin")
        else:
            # Veri ön işleme - Geliştirilmiş
            try:
                # Tarih kolonunu dönüştür
                if df['Belge tarihi'].dtype == 'object':
                    # Farklı tarih formatlarını dene
                    date_formats = ['%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']
                    
                    for date_format in date_formats:
                        try:
                            df['Belge tarihi'] = pd.to_datetime(df['Belge tarihi'], format=date_format)
                            break
                        except:
                            continue
                    else:
                        # Hiçbiri çalışmazsa otomatik algılama
                        df['Belge tarihi'] = pd.to_datetime(df['Belge tarihi'], infer_datetime_format=True)
                else:
                    df['Belge tarihi'] = pd.to_datetime(df['Belge tarihi'])
                
                # Sayısal sütunu temizle
                df['KWH Tüke Sm3'] = df['KWH Tüke Sm3'].astype(str).str.replace(',', '.')
                df['KWH Tüke Sm3'] = pd.to_numeric(df['KWH Tüke Sm3'], errors='coerce')
                
                # Geçersiz değerleri temizle
                initial_count = len(df)
                df = df.dropna(subset=['KWH Tüke Sm3', 'Belge tarihi'])
                cleaned_count = len(df)
                
                if initial_count - cleaned_count > 0:
                    st.warning(f"⚠️ {initial_count - cleaned_count} geçersiz kayıt temizlendi")
                
                st.success(f"✅ {cleaned_count} kayıt başarıyla işlendi")
                
            except Exception as e:
                st.error(f"Veri ön işleme hatası: {str(e)}")
                st.info("Tarih formatınızın 'GG.AA.YYYY' veya sayısal değerlerin nokta/virgül ile ayrıldığından emin olun")
            
            # Sidebar parametreleri
            anomaly_method = st.sidebar.selectbox(
                "Anomali Tespit Yöntemi",
                ['iqr', 'zscore', 'seasonal'],
                help="IQR: Çeyrekler arası aralık, Z-Score: Standart sapma, Seasonal: Mevsimsel analiz"
            )
            
            risk_threshold = st.sidebar.slider(
                "Risk Skoru Eşiği",
                min_value=1,
                max_value=10,
                value=5,
                help="Bu değerin üzerindeki tesisler yüksek riskli kabul edilir"
            )
            
            # Ana analiz
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Toplam Tesis Sayısı", df['Tüketim noktası'].nunique())
            
            with col2:
                st.metric("Toplam Kayıt Sayısı", len(df))
            
            with col3:
                avg_consumption = df['KWH Tüke Sm3'].mean()
                st.metric("Ortalama Tüketim", f"{avg_consumption:.2f} Sm³")
            
            with col4:
                date_range = df['Belge tarihi'].max() - df['Belge tarihi'].min()
                st.metric("Veri Aralığı", f"{date_range.days} gün")
            
            st.markdown("---")
            
            # Risk analizi
            st.header("📊 Risk Analizi")
            
            # Her tesis için risk skoru hesapla
            tesis_list = df['Tüketim noktası'].unique()
            risk_data = []
            
            progress_bar = st.progress(0)
            for i, tesis_id in enumerate(tesis_list):
                risk_score = calculate_risk_score(df, tesis_id)
                anomalies = detect_anomalies(df, tesis_id, anomaly_method)
                
                tesis_df = df[df['Tüketim noktası'] == tesis_id]
                
                risk_data.append({
                    'Tesis_ID': tesis_id,
                    'Risk_Skoru': risk_score,
                    'Anomali_Sayısı': len(anomalies),
                    'Ortalama_Tüketim': tesis_df['KWH Tüke Sm3'].mean(),
                    'Maksimum_Tüketim': tesis_df['KWH Tüke Sm3'].max(),
                    'Tüketim_Varyasyonu': tesis_df['KWH Tüke Sm3'].std(),
                    'Kayıt_Sayısı': len(tesis_df)
                })
                
                progress_bar.progress((i + 1) / len(tesis_list))
            
            risk_df = pd.DataFrame(risk_data)
            risk_df = risk_df.sort_values('Risk_Skoru', ascending=False)
            
            # Yüksek riskli tesisleri göster
            high_risk = risk_df[risk_df['Risk_Skoru'] >= risk_threshold]
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.subheader(f"🚨 Yüksek Riskli Tesisler (Risk Skoru ≥ {risk_threshold})")
                
                if len(high_risk) > 0:
                    # Risk dağılımı grafiği
                    fig_risk = px.histogram(
                        risk_df, 
                        x='Risk_Skoru', 
                        nbins=10,
                        title="Risk Skoru Dağılımı",
                        labels={'Risk_Skoru': 'Risk Skoru', 'count': 'Tesis Sayısı'}
                    )
                    fig_risk.add_vline(x=risk_threshold, line_dash="dash", line_color="red")
                    st.plotly_chart(fig_risk, use_container_width=True)
                    
                    st.dataframe(high_risk, use_container_width=True)
                else:
                    st.success("Belirlenen risk eşiği üzerinde tesis bulunamadı.")
            
            with col2:
                st.subheader("📈 Risk İstatistikleri")
                st.metric("Yüksek Riskli Tesis", len(high_risk))
                st.metric("Ortalama Risk Skoru", f"{risk_df['Risk_Skoru'].mean():.2f}")
                st.metric("Maksimum Risk Skoru", f"{risk_df['Risk_Skoru'].max()}")
            
            # Detaylı tesis analizi
            st.markdown("---")
            st.header("🔍 Detaylı Tesis Analizi")
            
            selected_tesis = st.selectbox(
                "Analiz edilecek tesisi seçin:",
                options=tesis_list,
                index=0 if len(high_risk) == 0 else list(tesis_list).index(high_risk.iloc[0]['Tesis_ID'])
            )
            
            if selected_tesis:
                tesis_data = df[df['Tüketim noktası'] == selected_tesis].copy()
                tesis_data = tesis_data.sort_values('Belge tarihi')
                
                # Anomalileri tespit et
                anomalies_idx = detect_anomalies(df, selected_tesis, anomaly_method)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # Tüketim zaman serisi
                    fig_ts = go.Figure()
                    
                    fig_ts.add_trace(go.Scatter(
                        x=tesis_data['Belge tarihi'],
                        y=tesis_data['KWH Tüke Sm3'],
                        mode='lines+markers',
                        name='Tüketim',
                        line=dict(color='blue')
                    ))
                    
                    # Anomalileri işaretle
                    if anomalies_idx:
                        anomaly_dates = tesis_data.iloc[anomalies_idx]['Belge tarihi']
                        anomaly_values = tesis_data.iloc[anomalies_idx]['KWH Tüke Sm3']
                        
                        fig_ts.add_trace(go.Scatter(
                            x=anomaly_dates,
                            y=anomaly_values,
                            mode='markers',
                            name='Anomali',
                            marker=dict(color='red', size=10, symbol='x')
                        ))
                    
                    fig_ts.update_layout(
                        title=f"Tesis {selected_tesis} - Tüketim Zaman Serisi",
                        xaxis_title="Tarih",
                        yaxis_title="Tüketim (Sm³)"
                    )
                    
                    st.plotly_chart(fig_ts, use_container_width=True)
                
                with col2:
                    # Tüketim dağılımı
                    fig_hist = px.histogram(
                        tesis_data, 
                        x='KWH Tüke Sm3',
                        nbins=20,
                        title=f"Tesis {selected_tesis} - Tüketim Dağılımı"
                    )
                    st.plotly_chart(fig_hist, use_container_width=True)
                
                # Tesis özet bilgileri
                st.subheader("📋 Tesis Özet Bilgileri")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Risk Skoru", risk_df[risk_df['Tesis_ID'] == selected_tesis]['Risk_Skoru'].iloc[0])
                
                with col2:
                    st.metric("Anomali Sayısı", len(anomalies_idx))
                
                with col3:
                    st.metric("Ortalama Tüketim", f"{tesis_data['KWH Tüke Sm3'].mean():.2f} Sm³")
                
                with col4:
                    st.metric("Maksimum Tüketim", f"{tesis_data['KWH Tüke Sm3'].max():.2f} Sm³")
                
                # Anomali detayları
                if anomalies_idx:
                    st.subheader("🔍 Anomali Detayları")
                    anomaly_details = tesis_data.iloc[anomalies_idx][['Belge tarihi', 'KWH Tüke Sm3']].copy()
                    anomaly_details['Anomali_Tipi'] = anomaly_method.upper()
                    st.dataframe(anomaly_details, use_container_width=True)

else:
    st.info("👆 Lütfen yukarıdan Excel veya CSV dosyanızı yükleyin.")
    
    # Örnek veri formatı göster
    st.subheader("📝 Beklenen Veri Formatı")
    
    sample_data = {
        'Belge tarihi': ['4.01.2018', '4.01.2018', '4.01.2018'],
        'Tüketim noktası': ['10732113', '10732338', '10732355'],
        'Başlangıç nesnesi': ['1000006129', '1000006129', '1000006129'],
        'KWH Tüke Sm3': [288.20, 306.34, 125.02]
    }
    
    st.dataframe(pd.DataFrame(sample_data))
    
    st.markdown("""
    ### 🔧 Kullanım Kılavuzu
    
    1. **Veri Yükleme**: Excel (.xlsx, .xls) veya CSV dosyanızı yükleyin
    2. **Anomali Yöntemi Seçimi**: 
       - **IQR**: Çeyrekler arası aralık yöntemi (genel anomaliler)
       - **Z-Score**: Standart sapma tabanlı (istatistiksel anomaliler)
       - **Seasonal**: Mevsimsel anormallikler
    3. **Risk Eşiği**: Yüksek riskli tesisleri belirlemek için eşik değeri
    4. **Analiz**: Sistem otomatik olarak şüpheli tesisleri tespit eder
    
    ### 🎯 Tespit Edilen Anomali Tipleri
    - Ani tüketim artışları (%50+)
    - Sıfır tüketim sonrası ani yükseliş
    - Düzensiz tüketim paternleri
    - Mevsimsel beklentilerin dışında tüketimler
    """)

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center'>
        <p>🔥 Doğalgaz Kaçak Kullanım Tespit Sistemi | 
        <i>Anomali tespiti için geliştirilmiş analiz aracı</i></p>
    </div>
    """, 
    unsafe_allow_html=True
)
