import pandas as pd
import numpy as np
from datetime import datetime
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from sklearn.preprocessing import StandardScaler
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

class GazSayacAnaliz:
    def __init__(self):
        self.season_months = {
            'kış': [11, 12, 1, 2, 3],
            'yaz': [6, 7, 8, 9],
            'geçiş': [4, 5, 10]
        }
    
    def detect_manipulation(self, df, tesisat_no):
        """
        Her tesisat için manipülasyon şüphesi analizi
        """
        tesisat_df = df[df['tesisat_no'] == tesisat_no].copy()
        tesisat_df = tesisat_df.sort_values('tarih')
        
        # 1. Rekor kırılma tespiti
        max_consumption_idx = tesisat_df['tuketim'].idxmax()
        max_date = tesisat_df.loc[max_consumption_idx, 'tarih']
        
        # 2. Öncesi ve sonrası dönemler
        before_period = tesisat_df[tesisat_df['tarih'] < max_date]
        after_period = tesisat_df[tesisat_df['tarih'] > max_date]
        
        if len(before_period) < 6 or len(after_period) < 6:
            return None
        
        # 3. Mevsimsel düzeltme
        before_seasonal = self._seasonal_adjustment(before_period)
        after_seasonal = self._seasonal_adjustment(after_period)
        
        # 4. İstatistiksel testler
        results = {
            'tesisat_no': tesisat_no,
            'rekor_tarihi': max_date,
            'rekor_degeri': tesisat_df.loc[max_consumption_idx, 'tuketim'],
            'bina_no': tesisat_df['bina_no'].iloc[0],
            'süphe_puani': 0,
            'manipulasyon_olasiligi': 'DÜŞÜK'
        }
        
        # Test 1: Ortalama değişim
        mean_before = before_seasonal.mean()
        mean_after = after_seasonal.mean()
        mean_change = ((mean_after - mean_before) / mean_before) * 100
        
        # Test 2: T-test (istatistiksel anlamlılık)
        if len(before_seasonal) > 1 and len(after_seasonal) > 1:
            t_stat, p_value = stats.ttest_ind(before_seasonal, after_seasonal)
            results['t_test_p_value'] = p_value
            
            if p_value < 0.05 and mean_change < -30:
                results['süphe_puani'] += 30
        
        # Test 3: Sürekli düşüş analizi
        if self._check_continuous_decline(after_period):
            results['süphe_puani'] += 40
        
        # Test 4: Mevsim normallerine göre analiz
        seasonal_deviation = self._check_seasonal_deviation(after_period)
        if seasonal_deviation > 50:
            results['süphe_puani'] += 20
        
        # Test 5: Ani düşüş tespiti
        if self._check_sudden_drop(tesisat_df, max_date):
            results['süphe_puani'] += 10
        
        # Toplam puan değerlendirmesi
        if results['süphe_puani'] >= 70:
            results['manipulasyon_olasiligi'] = 'YÜKSEK'
        elif results['süphe_puani'] >= 40:
            results['manipulasyon_olasiligi'] = 'ORTA'
        
        results['ortalama_degisim'] = mean_change
        results['analiz_edilen_aylar'] = len(tesisat_df)
        
        return results
    
    def _seasonal_adjustment(self, df):
        """Mevsimsel etkileri düzelt"""
        adjusted = []
        for _, row in df.iterrows():
            month = row['tarih'].month
            season = self._get_season(month)
            seasonal_factors = {'kış': 1.2, 'yaz': 0.7, 'geçiş': 1.0}
            adjusted.append(row['tuketim'] / seasonal_factors[season])
        return np.array(adjusted)
    
    def _get_season(self, month):
        for season, months in self.season_months.items():
            if month in months:
                return season
        return 'geçiş'
    
    def _check_continuous_decline(self, df):
        """Sürekli düşüş kontrolü"""
        if len(df) < 3:
            return False
        df['rolling_avg'] = df['tuketim'].rolling(window=3, min_periods=1).mean()
        trend = np.polyfit(range(len(df)), df['rolling_avg'].values, 1)[0]
        return trend < -0.1
    
    def _check_seasonal_deviation(self, df):
        """Mevsim normallerinden sapma kontrolü"""
        if len(df) < 12:
            return 0
        monthly_avg = df.groupby(df['tarih'].dt.month)['tuketim'].mean()
        historical_norms = {
            1: 150, 2: 140, 3: 120, 4: 80, 5: 60,
            6: 40, 7: 35, 8: 38, 9: 55, 10: 70,
            11: 100, 12: 130
        }
        deviations = []
        for month, avg in monthly_avg.items():
            if month in historical_norms:
                deviation = abs(avg - historical_norms[month]) / historical_norms[month] * 100
                deviations.append(deviation)
        return np.mean(deviations) if deviations else 0
    
    def _check_sudden_drop(self, df, max_date):
        """Ani düşüş kontrolü"""
        after_months = df[df['tarih'] > max_date].head(3)
        if len(after_months) < 3:
            return False
        drop_rate = ((after_months['tuketim'].mean() - df[df['tarih'] == max_date]['tuketim'].iloc[0]) / 
                    df[df['tarih'] == max_date]['tuketim'].iloc[0]) * 100
        return drop_rate < -50

# ==================== STREAMLIT ARAYÜZÜ ====================

st.set_page_config(page_title="Gaz Sayacı Manipülasyon Tespiti", layout="wide", page_icon="🔥")

st.title("🔥 Gaz Sayacı Manipülasyon Tespit Sistemi")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("📊 Veri Yükleme")
    uploaded_file = st.file_uploader("Excel dosyanızı yükleyin", type=['xlsx', 'xls'])
    
    st.markdown("---")
    st.markdown("### 📋 Gerekli Kolonlar:")
    st.code("""
    - tesisat_no
    - bina_no
    - tarih (YYYY-MM-DD)
    - tuketim
    """)

# Ana içerik
if uploaded_file is not None:
    try:
        # Veriyi yükle
        df = pd.read_excel(uploaded_file)
        df['tarih'] = pd.to_datetime(df['tarih'])
        
        st.success(f"✅ Veri başarıyla yüklendi! Toplam {len(df)} kayıt")
        
        # Genel istatistikler
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Toplam Tesisat", df['tesisat_no'].nunique())
        with col2:
            st.metric("Toplam Bina", df['bina_no'].nunique())
        with col3:
            st.metric("Ortalama Tüketim", f"{df['tuketim'].mean():.1f}")
        with col4:
            st.metric("Veri Aralığı", f"{(df['tarih'].max() - df['tarih'].min()).days} gün")
        
        st.markdown("---")
        
        # Analiz butonu
        if st.button("🔍 Manipülasyon Analizi Başlat", type="primary"):
            analyzer = GazSayacAnaliz()
            
            with st.spinner("Analiz yapılıyor..."):
                results = []
                tesisat_list = df['tesisat_no'].unique()
                
                progress_bar = st.progress(0)
                for i, tesisat_no in enumerate(tesisat_list):
                    result = analyzer.detect_manipulation(df, tesisat_no)
                    if result:
                        results.append(result)
                    progress_bar.progress((i + 1) / len(tesisat_list))
                
                results_df = pd.DataFrame(results)
            
            st.success(f"✅ Analiz tamamlandı! {len(results_df)} tesisat analiz edildi.")
            
            # Sonuçlar
            st.markdown("---")
            st.header("📈 Analiz Sonuçları")
            
            # Özet kartlar
            col1, col2, col3 = st.columns(3)
            with col1:
                yuksek = len(results_df[results_df['manipulasyon_olasiligi'] == 'YÜKSEK'])
                st.metric("🔴 Yüksek Risk", yuksek, 
                         delta=f"%{(yuksek/len(results_df)*100):.1f}" if len(results_df) > 0 else "0%")
            with col2:
                orta = len(results_df[results_df['manipulasyon_olasiligi'] == 'ORTA'])
                st.metric("🟡 Orta Risk", orta,
                         delta=f"%{(orta/len(results_df)*100):.1f}" if len(results_df) > 0 else "0%")
            with col3:
                dusuk = len(results_df[results_df['manipulasyon_olasiligi'] == 'DÜŞÜK'])
                st.metric("🟢 Düşük Risk", dusuk,
                         delta=f"%{(dusuk/len(results_df)*100):.1f}" if len(results_df) > 0 else "0%")
            
            # Grafikler
            col1, col2 = st.columns(2)
            
            with col1:
                # Risk dağılımı
                fig1 = px.pie(results_df, names='manipulasyon_olasiligi', 
                             title='Risk Dağılımı',
                             color='manipulasyon_olasiligi',
                             color_discrete_map={'YÜKSEK': '#ff4444', 'ORTA': '#ffaa00', 'DÜŞÜK': '#44ff44'})
                st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                # Şüphe puanı dağılımı
                fig2 = px.histogram(results_df, x='süphe_puani', 
                                   title='Şüphe Puanı Dağılımı',
                                   nbins=20,
                                   color='manipulasyon_olasiligi',
                                   color_discrete_map={'YÜKSEK': '#ff4444', 'ORTA': '#ffaa00', 'DÜŞÜK': '#44ff44'})
                st.plotly_chart(fig2, use_container_width=True)
            
            # Detaylı sonuçlar tablosu
            st.markdown("---")
            st.subheader("🔍 Detaylı Sonuçlar")
            
            # Filtreleme
            risk_filter = st.multiselect("Risk Seviyesi Filtrele:", 
                                        ['YÜKSEK', 'ORTA', 'DÜŞÜK'],
                                        default=['YÜKSEK', 'ORTA'])
            
            filtered_df = results_df[results_df['manipulasyon_olasiligi'].isin(risk_filter)]
            filtered_df = filtered_df.sort_values('süphe_puani', ascending=False)
            
            # Tabloyu göster
            display_df = filtered_df[['tesisat_no', 'bina_no', 'rekor_tarihi', 'rekor_degeri', 
                                     'süphe_puani', 'manipulasyon_olasiligi', 'ortalama_degisim']].copy()
            display_df['rekor_tarihi'] = display_df['rekor_tarihi'].dt.strftime('%Y-%m-%d')
            display_df['ortalama_degisim'] = display_df['ortalama_degisim'].round(2)
            
            st.dataframe(display_df, use_container_width=True, height=400)
            
            # İndirme butonu - Excel formatında
            from io import BytesIO
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                filtered_df.to_excel(writer, index=False, sheet_name='Analiz Sonuçları')
            buffer.seek(0)
            
            st.download_button(
                label="📥 Sonuçları İndir (Excel)",
                data=buffer,
                file_name=f"manipulasyon_analizi_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            # Detaylı tesisat analizi
            st.markdown("---")
            st.subheader("🔬 Tesisat Detay Analizi")
            
            selected_tesisat = st.selectbox("Detay görmek için tesisat seçin:", 
                                           filtered_df['tesisat_no'].tolist())
            
            if selected_tesisat:
                tesisat_data = df[df['tesisat_no'] == selected_tesisat].sort_values('tarih')
                
                # Tüketim grafiği
                fig3 = go.Figure()
                fig3.add_trace(go.Scatter(x=tesisat_data['tarih'], y=tesisat_data['tuketim'],
                                         mode='lines+markers', name='Tüketim',
                                         line=dict(color='blue', width=2)))
                
                # Rekor noktası
                result = filtered_df[filtered_df['tesisat_no'] == selected_tesisat].iloc[0]
                fig3.add_vline(x=result['rekor_tarihi'], line_dash="dash", 
                              line_color="red", annotation_text="Rekor Tarih")
                
                fig3.update_layout(title=f"Tesisat {selected_tesisat} - Tüketim Grafiği",
                                  xaxis_title="Tarih", yaxis_title="Tüketim (m³)")
                st.plotly_chart(fig3, use_container_width=True)
                
                # Detay bilgiler
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Şüphe Puanı", f"{result['süphe_puani']}/100")
                with col2:
                    st.metric("Ortalama Değişim", f"{result['ortalama_degisim']:.1f}%")
                with col3:
                    st.metric("Risk Seviyesi", result['manipulasyon_olasiligi'])
        
    except Exception as e:
        st.error(f"❌ Hata oluştu: {str(e)}")
        st.info("Lütfen CSV dosyanızın doğru formatta olduğundan emin olun.")

else:
    # Başlangıç ekranı
    st.info("👈 Lütfen soldaki menüden Excel dosyanızı yükleyin")
    
    st.markdown("### 📖 Kullanım Talimatları:")
    st.markdown("""
    1. **Veri Hazırlığı**: Excel dosyanız şu kolonları içermeli:
       - `tesisat_no`: Tesisat numarası
       - `bina_no`: Bina numarası
       - `tarih`: Tarih (YYYY-MM-DD formatında)
       - `tuketim`: Tüketim değeri (m³)
    
    2. **Yükleme**: Sol menüden "Browse files" butonuna tıklayıp Excel dosyanızı seçin
    
    3. **Analiz**: "Manipülasyon Analizi Başlat" butonuna tıklayın
    
    4. **Sonuçlar**: Risk seviyelerine göre filtreleme yapabilir ve Excel olarak indirebilirsiniz
    """)
    
    # Örnek veri formatı
    st.markdown("### 📊 Örnek Veri Formatı:")
    example_data = pd.DataFrame({
        'tesisat_no': ['T001', 'T001', 'T001', 'T002', 'T002'],
        'bina_no': ['B001', 'B001', 'B001', 'B002', 'B002'],
        'tarih': ['2023-01-15', '2023-02-15', '2023-03-15', '2023-01-15', '2023-02-15'],
        'tuketim': [120, 135, 98, 145, 150]
    })
    st.dataframe(example_data, use_container_width=True)
