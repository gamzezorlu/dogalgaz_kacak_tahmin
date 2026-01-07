import pandas as pd
import numpy as np
from datetime import datetime
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from scipy import stats
from scipy.signal import find_peaks
import warnings
warnings.filterwarnings('ignore')

class GazSayacAnalizGelistirilmis:
    def __init__(self):
        self.season_months = {
            'kış': [11, 12, 1, 2, 3],
            'yaz': [6, 7, 8, 9],
            'geçiş': [4, 5, 10]
        }
    
    def detect_manipulation_advanced(self, df, tesisat_no):
        """
        Geliştirilmiş manipülasyon tespiti
        - Rekorun ilk aylarda olması durumunu da yakalar
        - Çoklu rekor analizi yapar
        """
        try:
            tesisat_df = df[df['tesisat_no'] == tesisat_no].copy()
            
            if len(tesisat_df) < 12:  # Minimum 1 yıl veri
                return None
                
            tesisat_df = tesisat_df.sort_values('tarih')
            
            # YIL-AY formatında sütun ekle
            tesisat_df['yil_ay'] = tesisat_df['tarih'].dt.to_period('M')
            
            # 1. Tüm yüksek değerleri bul (peak detection)
            tuketim_array = tesisat_df['tuketim'].values
            
            # Peak'leri bul (threshold = ortalamanın 1.5 katı)
            mean_consumption = np.mean(tuketim_array)
            threshold = mean_consumption * 1.5
            
            peaks, _ = find_peaks(tuketim_array, height=threshold)
            
            if len(peaks) == 0:
                # Hiç peak yoksa, en yüksek değeri al
                peaks = [tesisat_df['tuketim'].idxmax()]
            
            results_list = []
            
            # Her bir peak için analiz yap
            for peak_idx in peaks:
                max_date = tesisat_df.iloc[peak_idx]['tarih']
                max_value = tesisat_df.iloc[peak_idx]['tuketim']
                
                # Bu peak'in anormal olup olmadığını kontrol et
                if self._is_abnormal_peak(tesisat_df, peak_idx):
                    # Analiz yap
                    result = self._analyze_period(tesisat_df, max_date, max_value, tesisat_no)
                    if result:
                        results_list.append(result)
            
            # En şüpheli sonucu döndür
            if results_list:
                # En yüksek şüphe puanlı olanı seç
                return max(results_list, key=lambda x: x['süphe_puani'])
            
            return None
            
        except Exception as e:
            print(f"Hata {tesisat_no}: {str(e)}")
            return None
    
    def _is_abnormal_peak(self, df, peak_idx):
        """Bir peak'in anormal olup olmadığını kontrol et"""
        if peak_idx == 0 or peak_idx == len(df) - 1:
            return False  # İlk veya son ay ise atla
        
        peak_value = df.iloc[peak_idx]['tuketim']
        
        # Önceki 6 ayın ortalaması
        start_idx = max(0, peak_idx - 6)
        before_avg = df.iloc[start_idx:peak_idx]['tuketim'].mean()
        
        # Sonraki 6 ayın ortalaması
        end_idx = min(len(df), peak_idx + 7)
        after_avg = df.iloc[peak_idx+1:end_idx]['tuketim'].mean()
        
        # Peak, ortalamanın en az 2 katı mı?
        if before_avg > 0:
            peak_ratio = peak_value / before_avg
            return peak_ratio > 2.0 and after_avg < (before_avg * 0.7)
        
        return False
    
    def _analyze_period(self, df, max_date, max_value, tesisat_no):
        """Belirli bir rekor tarihi için analiz yap"""
        try:
            # 1. Dönemleri belirle
            before_period = df[df['tarih'] < max_date]
            after_period = df[df['tarih'] > max_date]
            
            # Minimum veri kontrolü - ESNEK
            min_data_needed = 3
            
            # Eğer rekor ilk aylarda ise farklı yaklaşım
            if len(before_period) < min_data_needed:
                # Rekor ilk aylarda, tüm veriyi sonraki dönem olarak kabul et
                # İlk 6 ayı "başlangıç" olarak al
                if len(df) >= 12:
                    # İlk 6 ayı al (rekor dahil)
                    first_half = df.head(6)
                    # Geri kalanı ikinci yarı
                    second_half = df.tail(len(df) - 6)
                    
                    before_avg = first_half['tuketim'].mean()
                    after_avg = second_half['tuketim'].mean()
                    
                    # Mevsimsel düzeltme yap
                    before_seasonal = self._seasonal_adjustment(first_half)
                    after_seasonal = self._seasonal_adjustment(second_half)
                    
                    # Sonuçları hazırla
                    results = {
                        'tesisat_no': tesisat_no,
                        'rekor_tarihi': max_date,
                        'rekor_degeri': max_value,
                        'bina_no': df['bina_no'].iloc[0] if 'bina_no' in df.columns else 'Belirsiz',
                        'süphe_puani': 0,
                        'manipulasyon_olasiligi': 'DÜŞÜK',
                        'ortalama_oncesi': before_avg,
                        'ortalama_sonrasi': after_avg,
                        'degisim_yuzdesi': 0,
                        'analiz_edilen_aylar': len(df),
                        'not': 'REKOR_ILK_AYLARDA'
                    }
                else:
                    return None
            else:
                # Normal analiz
                if len(before_period) < min_data_needed or len(after_period) < min_data_needed:
                    return None
                
                before_avg = before_period['tuketim'].mean()
                after_avg = after_period['tuketim'].mean()
                
                before_seasonal = self._seasonal_adjustment(before_period)
                after_seasonal = self._seasonal_adjustment(after_period)
                
                results = {
                    'tesisat_no': tesisat_no,
                    'rekor_tarihi': max_date,
                    'rekor_degeri': max_value,
                    'bina_no': df['bina_no'].iloc[0] if 'bina_no' in df.columns else 'Belirsiz',
                    'süphe_puani': 0,
                    'manipulasyon_olasiligi': 'DÜŞÜK',
                    'ortalama_oncesi': before_avg,
                    'ortalama_sonrasi': after_avg,
                    'degisim_yuzdesi': 0,
                    'analiz_edilen_aylar': len(df),
                    'not': 'NORMAL_ANALIZ'
                }
            
            # 2. Şüphe puanı hesapla
            suspicion_score = 0
            
            # Değişim oranı
            if results.get('ortalama_oncesi', 0) > 0:
                change_pct = ((results['ortalama_sonrasi'] - results['ortalama_oncesi']) / results['ortalama_oncesi']) * 100
                results['degisim_yuzdesi'] = change_pct
                
                if change_pct < -30:
                    suspicion_score += 30
                elif change_pct < -20:
                    suspicion_score += 20
                elif change_pct < -10:
                    suspicion_score += 10
            
            # İstatistiksel test
            if 'before_seasonal' in locals() and 'after_seasonal' in locals():
                if len(before_seasonal) > 1 and len(after_seasonal) > 1:
                    try:
                        t_stat, p_value = stats.ttest_ind(before_seasonal, after_seasonal)
                        if p_value < 0.05:
                            suspicion_score += 20
                        if p_value < 0.01:
                            suspicion_score += 10
                    except:
                        pass
            
            # Mevsimsel sapma
            if len(after_period) >= 3 and len(before_period) >= 3:
                seasonal_dev = self._check_seasonal_deviation_advanced(after_period, before_period)
                if seasonal_dev > 40:
                    suspicion_score += 15
            
            # Trend değişimi
            if len(after_period) >= 3 and len(before_period) >= 3:
                if self._check_trend_change(before_period, after_period):
                    suspicion_score += 15
            
            # Ani düşüş
            if self._check_sudden_drop_advanced(df, max_date):
                suspicion_score += 10
            
            # Toplam puan
            results['süphe_puani'] = suspicion_score
            
            if suspicion_score >= 40:
                results['manipulasyon_olasiligi'] = 'YÜKSEK'
            elif suspicion_score >= 20:
                results['manipulasyon_olasiligi'] = 'ORTA'
            
            return results
            
        except Exception as e:
            return None
    
    def _seasonal_adjustment(self, df):
        """Mevsimsel düzeltme"""
        adjusted = []
        for _, row in df.iterrows():
            month = row['tarih'].month
            season = self._get_season(month)
            # Daha gerçekçi faktörler
            seasonal_factors = {'kış': 1.3, 'yaz': 0.6, 'geçiş': 0.9}
            adjusted.append(row['tuketim'] / seasonal_factors[season])
        return np.array(adjusted)
    
    def _get_season(self, month):
        for season, months in self.season_months.items():
            if month in months:
                return season
        return 'geçiş'
    
    def _check_seasonal_deviation_advanced(self, after_df, before_df):
        """Gelişmiş mevsimsel sapma kontrolü"""
        if len(after_df) < 3 or len(before_df) < 3:
            return 0
        
        try:
            # Aylık ortalamaları hesapla
            before_monthly = before_df.groupby(before_df['tarih'].dt.month)['tuketim'].mean()
            after_monthly = after_df.groupby(after_df['tarih'].dt.month)['tuketim'].mean()
            
            deviations = []
            for month in before_monthly.index:
                if month in after_monthly.index:
                    before_val = before_monthly[month]
                    after_val = after_monthly[month]
                    if before_val > 0:
                        deviation = ((after_val - before_val) / before_val) * 100
                        deviations.append(deviation)
            
            if deviations:
                # Ortalama negatif sapma
                negative_deviations = [d for d in deviations if d < -20]
                if negative_deviations:
                    return abs(np.mean(negative_deviations))
            
            return 0
        except:
            return 0
    
    def _check_trend_change(self, before_df, after_df):
        """Trend değişimi kontrolü"""
        if len(before_df) < 3 or len(after_df) < 3:
            return False
        
        try:
            # Önceki trend
            before_sorted = before_df.sort_values('tarih')
            x_before = np.arange(len(before_sorted))
            y_before = before_sorted['tuketim'].values
            coeffs_before = np.polyfit(x_before, y_before, 1)
            slope_before = coeffs_before[0]
            
            # Sonraki trend
            after_sorted = after_df.sort_values('tarih')
            x_after = np.arange(len(after_sorted))
            y_after = after_sorted['tuketim'].values
            coeffs_after = np.polyfit(x_after, y_after, 1)
            slope_after = coeffs_after[0]
            
            # Büyük trend değişimi
            return (slope_before > 0 and slope_after < -0.05) or \
                   (slope_before > 0.05 and slope_after < -0.05)
        except:
            return False
    
    def _check_sudden_drop_advanced(self, df, max_date):
        """Gelişmiş ani düşüş kontrolü"""
        try:
            # Rekor sonrası ilk 6 ay
            after_6months = df[df['tarih'] > max_date].head(6)
            
            if len(after_6months) < 3:
                return False
            
            # Rekor değeri
            max_value = df[df['tarih'] == max_date]['tuketim'].iloc[0]
            
            if max_value <= 0:
                return False
            
            # Rekor öncesi 6 ay
            before_6months = df[df['tarih'] < max_date].tail(6)
            if len(before_6months) >= 3:
                avg_before = before_6months['tuketim'].mean()
            else:
                avg_before = max_value
            
            # Sonrası ortalama
            avg_after = after_6months['tuketim'].mean()
            
            # Düşüş oranı
            if avg_before > 0:
                drop_rate = ((avg_after - avg_before) / avg_before) * 100
                return drop_rate < -40
            
            return False
        except:
            return False

# ==================== STREAMLIT ARAYÜZÜ ====================

st.set_page_config(page_title="Gaz Sayacı Manipülasyon Tespiti", layout="wide", page_icon="🔥")

st.title("🔥 Gaz Sayacı Manipülasyon Tespit Sistemi (Geliştirilmiş)")
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
    
    st.markdown("---")
    st.info("🆕 **Gelişmiş Özellikler:**\n- Rekor ilk aylarda olsa bile tespit\n- Çoklu rekor analizi\n- Peak detection algoritması")

# Ana içerik
if uploaded_file is not None:
    try:
        # Veriyi yükle
        df = pd.read_excel(uploaded_file)
        
        # Kolon kontrolü
        required_columns = ['tesisat_no', 'bina_no', 'tarih', 'tuketim']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            st.error(f"❌ Eksik kolonlar: {', '.join(missing_columns)}")
            st.warning("📋 Excel dosyanızdaki kolonlar:")
            st.code(", ".join(df.columns.tolist()))
            st.info("💡 Lütfen Excel dosyanızdaki kolon isimlerini şu şekilde düzenleyin: tesisat_no, bina_no, tarih, tuketim")
            st.stop()
        
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
        if st.button("🔍 Gelişmiş Manipülasyon Analizi Başlat", type="primary"):
            analyzer = GazSayacAnalizGelistirilmis()
            
            with st.spinner("Gelişmiş analiz yapılıyor..."):
                results = []
                tesisat_list = df['tesisat_no'].unique()
                
                progress_bar = st.progress(0)
                for i, tesisat_no in enumerate(tesisat_list):
                    result = analyzer.detect_manipulation_advanced(df, tesisat_no)
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
                                     'süphe_puani', 'manipulasyon_olasiligi', 'degisim_yuzdesi', 'not']].copy()
            display_df['rekor_tarihi'] = display_df['rekor_tarihi'].dt.strftime('%Y-%m-%d')
            display_df['degisim_yuzdesi'] = display_df['degisim_yuzdesi'].round(2)
            
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
            
            if len(filtered_df) > 0:
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
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Şüphe Puanı", f"{result['süphe_puani']}/100")
                    with col2:
                        st.metric("Değişim", f"{result['degisim_yuzdesi']:.1f}%")
                    with col3:
                        st.metric("Risk Seviyesi", result['manipulasyon_olasiligi'])
                    with col4:
                        st.metric("Analiz Tipi", result['not'])
        
    except Exception as e:
        st.error(f"❌ Hata oluştu: {str(e)}")
        st.info("Lütfen Excel dosyanızın doğru formatta olduğundan emin olun.")

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
    
    3. **Analiz**: "Gelişmiş Manipülasyon Analizi Başlat" butonuna tıklayın
    
    4. **Sonuçlar**: Risk seviyelerine göre filtreleme yapabilir ve Excel olarak indirebilirsiniz
    """)
    
    st.markdown("### 🆕 Gelişmiş Özellikler:")
    st.markdown("""
    - **Rekor ilk aylarda**: Rekor ilk 3 ay içinde bile olsa tespit edilir
    - **Çoklu peak analizi**: Birden fazla şüpheli rekor tespit edilir
    - **Peak detection**: Bilimsel algoritma ile anormal tüketim tespiti
    - **Esnek analiz**: Minimum 12 ay veri ile çalışır
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
