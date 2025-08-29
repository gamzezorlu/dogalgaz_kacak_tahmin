import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from scipy import stats
import io
import warnings
warnings.filterwarnings('ignore')

def load_and_process_data(uploaded_file):
    """Excel veya CSV dosyasını yükle ve işle"""
    try:
        # Dosya uzantısını kontrol et
        file_extension = uploaded_file.name.split('.')[-1].lower()
        
        if file_extension in ['xlsx', 'xls']:
            # Excel dosyasını oku
            df = pd.read_excel(uploaded_file, engine='openpyxl' if file_extension == 'xlsx' else None)
        elif file_extension == 'csv':
            # CSV dosyasını oku
            df = pd.read_csv(uploaded_file, encoding='utf-8')
        else:
            st.error("Desteklenmeyen dosya formatı! Lütfen Excel (.xlsx, .xls) veya CSV (.csv) dosyası yükleyin.")
            return None
        
        # Sütun isimlerini temizle
        df.columns = df.columns.str.strip()
        
        # Tarih sütununu datetime'a çevir
        df['Belge tarihi'] = pd.to_datetime(df['Belge tarihi'], format='%d.%m.%Y', errors='coerce')
        
        # Sm3 sütununu sayısal değere çevir
        if 'Sm3' in df.columns:
            df['Sm3'] = pd.to_numeric(df['Sm3'].astype(str).str.replace(',', '.'), errors='coerce')
        
        # Null değerleri temizle
        df = df.dropna(subset=['Belge tarihi', 'Sm3'])
        
        # Tarihe göre sırala
        df = df.sort_values('Belge tarihi')
        
        return df
    except Exception as e:
        st.error(f"Veri yükleme hatası: {str(e)}")
        return None

def add_seasonal_features(df):
    """Mevsimsel özellikler ekle"""
    df = df.copy()
    df['Ay'] = df['Belge tarihi'].dt.month
    df['Yıl'] = df['Belge tarihi'].dt.year
    df['Gün'] = df['Belge tarihi'].dt.dayofyear
    
    # Mevsim bilgisi ekle
    def get_season(month):
        if month in [12, 1, 2]:
            return 'Kış'
        elif month in [3, 4, 5]:
            return 'İlkbahar'
        elif month in [6, 7, 8]:
            return 'Yaz'
        else:
            return 'Sonbahar'
    
    df['Mevsim'] = df['Ay'].apply(get_season)
    
    # Trigonometrik özellikler (mevsimsellik için)
    df['Sin_Ay'] = np.sin(2 * np.pi * df['Ay'] / 12)
    df['Cos_Ay'] = np.cos(2 * np.pi * df['Ay'] / 12)
    
    return df

def detect_anomalies_isolation_forest(df, contamination=0.1):
    """Isolation Forest ile anomali tespiti"""
    # Özellik matrisini hazırla
    features = ['Sm3', 'Sin_Ay', 'Cos_Ay']
    X = df[features].copy()
    
    # Standardize et
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Isolation Forest modelini eğit
    iso_forest = IsolationForest(contamination=contamination, random_state=42)
    anomalies = iso_forest.fit_predict(X_scaled)
    
    # Anomali skorları
    scores = iso_forest.decision_function(X_scaled)
    
    return anomalies, scores

def detect_anomalies_zscore(df, threshold=3):
    """Z-Score yöntemi ile anomali tespiti (mevsimsel düzeltmeli)"""
    df_copy = df.copy()
    
    # Her mevsim için ayrı z-score hesapla
    anomalies = []
    z_scores = []
    
    for season in df_copy['Mevsim'].unique():
        season_data = df_copy[df_copy['Mevsim'] == season]['Sm3']
        mean_val = season_data.mean()
        std_val = season_data.std()
        
        season_z_scores = np.abs((season_data - mean_val) / std_val)
        season_anomalies = (season_z_scores > threshold).astype(int) * 2 - 1  # -1 normal, 1 anomali
        
        z_scores.extend(season_z_scores.tolist())
        anomalies.extend(season_anomalies.tolist())
    
    return np.array(anomalies), np.array(z_scores)

def detect_anomalies_iqr(df):
    """IQR yöntemi ile anomali tespiti (mevsimsel düzeltmeli)"""
    df_copy = df.copy()
    anomalies = []
    
    for season in df_copy['Mevsim'].unique():
        season_data = df_copy[df_copy['Mevsim'] == season]['Sm3']
        Q1 = season_data.quantile(0.25)
        Q3 = season_data.quantile(0.75)
        IQR = Q3 - Q1
        
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        
        season_anomalies = ((season_data < lower_bound) | (season_data > upper_bound)).astype(int) * 2 - 1
        anomalies.extend(season_anomalies.tolist())
    
    return np.array(anomalies)

def create_time_series_plot(df, anomalies_col):
    """Zaman serisi grafiği oluştur"""
    fig = make_subplots(rows=2, cols=1, 
                       subplot_titles=('Doğalgaz Tüketimi ve Anomaliler', 'Mevsimsel Dağılım'),
                       vertical_spacing=0.1)
    
    # Normal tüketim
    normal_data = df[df[anomalies_col] == -1]
    fig.add_trace(
        go.Scatter(x=normal_data['Belge tarihi'], 
                  y=normal_data['Sm3'],
                  mode='markers',
                  name='Normal Tüketim',
                  marker=dict(color='blue', size=6)),
        row=1, col=1
    )
    
    # Anomali tüketim
    anomaly_data = df[df[anomalies_col] == 1]
    if not anomaly_data.empty:
        fig.add_trace(
            go.Scatter(x=anomaly_data['Belge tarihi'], 
                      y=anomaly_data['Sm3'],
                      mode='markers',
                      name='Anomali',
                      marker=dict(color='red', size=8, symbol='diamond')),
            row=1, col=1
        )
    
    # Mevsimsel box plot
    fig.add_trace(
        go.Box(x=df['Mevsim'], y=df['Sm3'], name='Mevsimsel Dağılım'),
        row=2, col=1
    )
    
    fig.update_layout(height=800, showlegend=True, title_text="Doğalgaz Tüketim Analizi")
    fig.update_xaxes(title_text="Tarih", row=1, col=1)
    fig.update_yaxes(title_text="Tüketim (Sm3)", row=1, col=1)
    fig.update_xaxes(title_text="Mevsim", row=2, col=1)
    fig.update_yaxes(title_text="Tüketim (Sm3)", row=2, col=1)
    
    return fig

def create_excel_report(df, anomaly_df):
    """Excel raporu oluştur"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Anomali tesisatları (ana rapor)
        anomaly_summary = anomaly_df.groupby('Tüketim noktası').agg({
            'Sm3': ['count', 'mean', 'min', 'max'],
            'Belge tarihi': ['min', 'max']
        }).round(2)
        
        anomaly_summary.columns = ['Anomali Sayısı', 'Ortalama Tüketim', 'Min Tüketim', 'Max Tüketim', 'İlk Anomali', 'Son Anomali']
        anomaly_summary = anomaly_summary.sort_values('Anomali Sayısı', ascending=False)
        anomaly_summary.to_excel(writer, sheet_name='Anomali Tesisatları', index=True)
        
        # Detaylı anomali listesi
        detail_cols = ['Belge tarihi', 'Tüketim noktası', 'Bağlantı nesnesi', 'Sm3', 'Mevsim']
        if 'Anomali_Skoru' in anomaly_df.columns:
            detail_cols.append('Anomali_Skoru')
        if 'Z_Score' in anomaly_df.columns:
            detail_cols.append('Z_Score')
            
        anomaly_detail = anomaly_df[detail_cols].copy()
        anomaly_detail = anomaly_detail.sort_values(['Tüketim noktası', 'Belge tarihi'])
        anomaly_detail.to_excel(writer, sheet_name='Detaylı Anomali Listesi', index=False)
        
        # Mevsimsel istatistikler
        seasonal_stats = df.groupby(['Tüketim noktası', 'Mevsim']).agg({
            'Sm3': ['mean', 'std', 'count'],
            'Anomali': lambda x: (x == 1).sum()
        }).round(2)
        seasonal_stats.columns = ['Ortalama', 'Std Sapma', 'Kayıt Sayısı', 'Anomali Sayısı']
        seasonal_stats['Anomali Oranı (%)'] = (seasonal_stats['Anomali Sayısı'] / seasonal_stats['Kayıt Sayısı'] * 100).round(1)
        seasonal_stats.to_excel(writer, sheet_name='Mevsimsel İstatistikler', index=True)
        
        # Genel özet
        summary_data = {
            'Metrik': [
                'Toplam Kayıt Sayısı',
                'Toplam Tesisat Sayısı', 
                'Anomali Kayıt Sayısı',
                'Anomalili Tesisat Sayısı',
                'Genel Anomali Oranı (%)',
                'Analiz Tarihi'
            ],
            'Değer': [
                len(df),
                df['Tüketim noktası'].nunique(),
                len(anomaly_df),
                anomaly_df['Tüketim noktası'].nunique(),
                round((len(anomaly_df) / len(df)) * 100, 2),
                datetime.now().strftime('%d.%m.%Y %H:%M')
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Genel Özet', index=False)
    
    output.seek(0)
    return output

def main():
    st.set_page_config(page_title="Doğalgaz Anomali Tespit Sistemi", layout="wide")
    
    st.title("🔥 Doğalgaz Tüketim Anomali Tespit Sistemi")
    st.markdown("Bu uygulama doğalgaz tüketim verilerinizi analiz ederek anormal tüketimleri tespit eder.")
    
    # Sidebar - Parametreler
    st.sidebar.header("⚙️ Analiz Parametreleri")
    
    # Dosya yükleme
    uploaded_file = st.file_uploader("Excel veya CSV dosyasını yükleyin", type=['xlsx', 'xls', 'csv'])
    
    if uploaded_file is not None:
        # Veriyi yükle ve işle
        df = load_and_process_data(uploaded_file)
        
        if df is not None and not df.empty:
            st.success(f"✅ {len(df)} adet kayıt başarıyla yüklendi!")
            
            # Mevsimsel özellikler ekle
            df = add_seasonal_features(df)
            
            # Sidebar parametreleri
            method = st.sidebar.selectbox(
                "Anomali Tespit Yöntemi",
                ["Isolation Forest", "Z-Score (Mevsimsel)", "IQR (Mevsimsel)"]
            )
            
            if method == "Isolation Forest":
                contamination = st.sidebar.slider("Anomali Oranı", 0.01, 0.3, 0.1, 0.01)
            elif method == "Z-Score (Mevsimsel)":
                threshold = st.sidebar.slider("Z-Score Eşiği", 1.5, 5.0, 3.0, 0.1)
            
            # Tesis seçimi
            if 'Tüketim noktası' in df.columns:
                facilities = df['Tüketim noktası'].unique()
                selected_facility = st.sidebar.selectbox("Tesis Seçimi (Opsiyonel)", 
                                                        ["Tümü"] + list(facilities))
                if selected_facility != "Tümü":
                    df = df[df['Tüketim noktası'] == selected_facility]
            
            # Anomali tespiti yap
            if method == "Isolation Forest":
                anomalies, scores = detect_anomalies_isolation_forest(df, contamination)
                df['Anomali'] = anomalies
                df['Anomali_Skoru'] = scores
            elif method == "Z-Score (Mevsimsel)":
                anomalies, z_scores = detect_anomalies_zscore(df, threshold)
                df['Anomali'] = anomalies
                df['Z_Score'] = z_scores
            else:  # IQR
                anomalies = detect_anomalies_iqr(df)
                df['Anomali'] = anomalies
            
            # Sonuçları göster
            col1, col2, col3, col4 = st.columns(4)
            
            total_records = len(df)
            anomaly_count = len(df[df['Anomali'] == 1])
            normal_count = total_records - anomaly_count
            anomaly_rate = (anomaly_count / total_records) * 100
            
            with col1:
                st.metric("Toplam Kayıt", total_records)
            with col2:
                st.metric("Normal Tüketim", normal_count)
            with col3:
                st.metric("Anomali Sayısı", anomaly_count)
            with col4:
                st.metric("Anomali Oranı", f"{anomaly_rate:.1f}%")
            
            # Grafik gösterimi
            st.subheader("📊 Görselleştirme")
            fig = create_time_series_plot(df, 'Anomali')
            st.plotly_chart(fig, use_container_width=True)
            
            # Anomali detayları
            if anomaly_count > 0:
                st.subheader("🚨 Tespit Edilen Anomaliler")
                
                anomaly_df = df[df['Anomali'] == 1].copy()
                anomaly_df = anomaly_df.sort_values('Belge tarihi', ascending=False)
                
                # Görüntülenecek sütunları seç
                display_cols = ['Belge tarihi', 'Sm3', 'Mevsim']
                if 'Tüketim noktası' in anomaly_df.columns:
                    display_cols.insert(1, 'Tüketim noktası')
                if 'Bağlantı nesnesi' in anomaly_df.columns:
                    display_cols.insert(-1, 'Bağlantı nesnesi')
                
                if method == "Isolation Forest":
                    display_cols.append('Anomali_Skoru')
                elif method == "Z-Score (Mevsimsel)":
                    display_cols.append('Z_Score')
                
                st.dataframe(anomaly_df[display_cols], use_container_width=True)
                
                # Excel raporu indirme
                excel_data = create_excel_report(df, anomaly_df)
                st.download_button(
                    label="📊 Detaylı Excel Raporu İndir",
                    data=excel_data,
                    file_name=f"dogalgaz_anomali_raporu_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            # Mevsimsel analiz
            st.subheader("📈 Mevsimsel Analiz")
            seasonal_stats = df.groupby('Mevsim').agg({
                'Sm3': ['mean', 'std', 'count'],
                'Anomali': lambda x: (x == 1).sum()
            }).round(2)
            
            seasonal_stats.columns = ['Ortalama Tüketim', 'Standart Sapma', 'Kayıt Sayısı', 'Anomali Sayısı']
            seasonal_stats['Anomali Oranı (%)'] = (seasonal_stats['Anomali Sayısı'] / seasonal_stats['Kayıt Sayısı'] * 100).round(1)
            
            st.dataframe(seasonal_stats, use_container_width=True)
            
            # Metodoloji açıklaması
            with st.expander("ℹ️ Metodoloji Hakkında"):
                if method == "Isolation Forest":
                    st.write("""
                    **Isolation Forest**: Makine öğrenmesi tabanlı anomali tespit yöntemi.
                    - Mevsimsel değişiklikleri trigonometrik özellikler ile modeller
                    - Anomali oranı parametresi ile hassaslık ayarlanabilir
                    - Çok boyutlu anomalileri tespit edebilir
                    """)
                elif method == "Z-Score (Mevsimsel)":
                    st.write("""
                    **Z-Score (Mevsimsel)**: İstatistiksel anomali tespit yöntemi.
                    - Her mevsim için ayrı ortalama ve standart sapma hesaplar
                    - Z-Score eşiği ile hassaslık ayarlanabilir
                    - Mevsimsel değişiklikleri dikkate alır
                    """)
                else:
                    st.write("""
                    **IQR (Mevsimsel)**: Çeyrekler arası mesafe tabanlı anomali tespit.
                    - Her mevsim için ayrı IQR hesaplar
                    - Q1 - 1.5*IQR ve Q3 + 1.5*IQR sınırları kullanır
                    - Robust ve anlaşılır yöntem
                    """)
        else:
            st.error("Veri yüklenirken bir hata oluştu. Lütfen dosya formatını kontrol edin.")
    
    else:
        st.info("👆 Lütfen Excel veya CSV dosyanızı yükleyin.")
        st.markdown("""
        ### 📋 Beklenen Dosya Formatı:
        - **Dosya Türü**: Excel (.xlsx, .xls) veya CSV (.csv)
        - **Belge tarihi**: DD.MM.YYYY formatında tarih
        - **Tüketim noktası**: Tesis/tesisat bilgisi
        - **Bağlantı nesnesi**: Bina numarası
        - **Sm3**: Tüketim miktarı (sayısal değer)
        
        ### ⚡ Özellikler:
        - Excel ve CSV dosya desteği
        - Mevsimsel değişiklikleri dikkate alan akıllı anomali tespiti
        - Üç farklı anomali tespit yöntemi
        - İnteraktif görselleştirme
        - **Detaylı Excel raporu** - Anomali tesisatları listesi ve istatistikler
        
        ### 📊 Excel Raporu İçeriği:
        - **Anomali Tesisatları**: Tesisat bazında anomali sayıları ve özeti
        - **Detaylı Anomali Listesi**: Tüm anomaliler kronolojik sırayla
        - **Mevsimsel İstatistikler**: Tesisat ve mevsim bazında analiz
        - **Genel Özet**: Toplam istatistikler ve analiz bilgileri
        """)

if __name__ == "__main__":
    main()
