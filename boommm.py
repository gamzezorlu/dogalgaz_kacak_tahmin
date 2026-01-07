import pandas as pd
import numpy as np
from datetime import datetime
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from scipy import stats
from scipy.signal import find_peaks
from sklearn.ensemble import IsolationForest
import warnings
warnings.filterwarnings('ignore')

class GazSayacHibritAnaliz:
    """Hibrit Manipülasyon Tespit Sistemi"""
    
    def __init__(self):
        self.season_months = {
            'kış': [11, 12, 1, 2, 3],
            'yaz': [6, 7, 8, 9],
            'geçiş': [4, 5, 10]
        }
        
        self.weights = {
            'rekor_orani': 25,
            'dusus_hizi': 30,
            'mevsimsel_uyumsuzluk': 15,
            'trend_degisimi': 15,
            'varyans_degisimi': 10,
            'ml_anomali': 5
        }
    
    def detect_manipulation_hybrid(self, df, tesisat_no):
        """Hibrit manipülasyon tespiti"""
        try:
            tesisat_df = df[df['tesisat_no'] == tesisat_no].copy()
            
            if len(tesisat_df) < 12:
                return None
            
            tesisat_df = tesisat_df.sort_values('tarih').reset_index(drop=True)
            candidate_points = self._find_manipulation_candidates(tesisat_df)
            
            if not candidate_points:
                return None
            
            results = []
            for point_idx, point_value in candidate_points:
                point_date = tesisat_df.iloc[point_idx]['tarih']
                result = self._analyze_manipulation_point(
                    tesisat_df, point_idx, point_date, point_value, tesisat_no
                )
                if result:
                    results.append(result)
            
            if results:
                return max(results, key=lambda x: x['süphe_puani'])
            
            return None
            
        except Exception as e:
            return None
    
    def _find_manipulation_candidates(self, df):
        """Potansiyel manipülasyon noktalarını tespit et"""
        candidates = []
        tuketim = df['tuketim'].values
        
        if len(tuketim) < 12:
            return candidates
        
        max_idx = np.argmax(tuketim)
        max_val = tuketim[max_idx]
        candidates.append((max_idx, max_val))
        
        mean = np.mean(tuketim)
        std = np.std(tuketim)
        threshold = mean + 1.5 * std
        
        peaks, _ = find_peaks(tuketim, height=threshold, distance=3)
        for peak_idx in peaks:
            if peak_idx != max_idx:
                candidates.append((peak_idx, tuketim[peak_idx]))
        
        window = min(6, len(tuketim) // 3)
        rolling_mean = pd.Series(tuketim).rolling(window=window, center=True).mean()
        
        for i in range(window, len(tuketim) - window):
            if pd.notna(rolling_mean.iloc[i]):
                deviation_ratio = tuketim[i] / rolling_mean.iloc[i]
                if deviation_ratio > 2.0 and tuketim[i] > threshold:
                    if i not in [c[0] for c in candidates]:
                        candidates.append((i, tuketim[i]))
        
        return candidates
    
    def _analyze_manipulation_point(self, df, point_idx, point_date, point_value, tesisat_no):
        """Belirli bir nokta için detaylı analiz"""
        try:
            if point_idx < 3 or point_idx >= len(df) - 3:
                return None
            
            before_period = df.iloc[:point_idx]
            after_period = df.iloc[point_idx+1:]
            
            if len(before_period) < 3 or len(after_period) < 3:
                return None
            
            results = {
                'tesisat_no': tesisat_no,
                'rekor_tarihi': point_date,
                'rekor_degeri': point_value,
                'bina_no': df['bina_no'].iloc[0] if 'bina_no' in df.columns else 'N/A',
                'süphe_puani': 0,
                'manipulasyon_olasiligi': 'DÜŞÜK',
                'analiz_detaylari': {}
            }
            
            suspicion_score = 0
            before_mean = before_period['tuketim'].mean()
            after_mean = after_period['tuketim'].mean()
            
            # KRİTER 1: REKOR ORANI
            if before_mean > 0:
                rekor_orani = point_value / before_mean
                if rekor_orani >= 3.0:
                    suspicion_score += self.weights['rekor_orani']
                elif rekor_orani >= 2.5:
                    suspicion_score += self.weights['rekor_orani'] * 0.8
                elif rekor_orani >= 2.0:
                    suspicion_score += self.weights['rekor_orani'] * 0.5
                results['analiz_detaylari']['rekor_orani'] = round(rekor_orani, 2)
            
            # KRİTER 2: DÜŞÜŞ HIZI
            if before_mean > 0:
                dusus_orani = ((after_mean - before_mean) / before_mean) * 100
                first_3_after = after_period.head(3)['tuketim'].mean()
                ilk_dusus = ((first_3_after - before_mean) / before_mean) * 100
                
                if ilk_dusus < -60:
                    suspicion_score += self.weights['dusus_hizi']
                elif ilk_dusus < -50:
                    suspicion_score += self.weights['dusus_hizi'] * 0.8
                elif ilk_dusus < -40:
                    suspicion_score += self.weights['dusus_hizi'] * 0.6
                elif ilk_dusus < -30:
                    suspicion_score += self.weights['dusus_hizi'] * 0.4
                
                results['analiz_detaylari']['dusus_orani'] = round(dusus_orani, 1)
                results['analiz_detaylari']['ilk_3_ay_dusus'] = round(ilk_dusus, 1)
            
            # KRİTER 3: MEVSİMSEL UYUMSUZLUK
            seasonal_score = self._check_seasonal_mismatch(before_period, after_period)
            suspicion_score += seasonal_score * self.weights['mevsimsel_uyumsuzluk'] / 100
            results['analiz_detaylari']['mevsimsel_uyumsuzluk'] = round(seasonal_score, 1)
            
            # KRİTER 4: TREND DEĞİŞİMİ
            trend_change = self._analyze_trend_change(before_period, after_period)
            if trend_change:
                suspicion_score += self.weights['trend_degisimi']
                results['analiz_detaylari']['trend_degisimi'] = 'VAR'
            else:
                results['analiz_detaylari']['trend_degisimi'] = 'YOK'
            
            # KRİTER 5: VARYANS DEĞİŞİMİ
            before_std = before_period['tuketim'].std()
            after_std = after_period['tuketim'].std()
            
            if before_std > 0:
                varyans_degisimi = ((after_std - before_std) / before_std) * 100
                if varyans_degisimi < -40:
                    suspicion_score += self.weights['varyans_degisimi']
                elif varyans_degisimi < -30:
                    suspicion_score += self.weights['varyans_degisimi'] * 0.7
                results['analiz_detaylari']['varyans_degisimi'] = round(varyans_degisimi, 1)
            
            # KRİTER 6: ML ANOMALİ
            ml_score = self._ml_anomaly_detection(df, point_idx)
            if ml_score > 0.7:
                suspicion_score += self.weights['ml_anomali']
            elif ml_score > 0.5:
                suspicion_score += self.weights['ml_anomali'] * 0.6
            results['analiz_detaylari']['ml_anomali_skoru'] = round(ml_score, 2)
            
            # İSTATİSTİKSEL TEST
            if len(before_period) > 1 and len(after_period) > 1:
                before_seasonal = self._seasonal_adjustment(before_period)
                after_seasonal = self._seasonal_adjustment(after_period)
                
                try:
                    t_stat, p_value = stats.ttest_ind(before_seasonal, after_seasonal)
                    results['analiz_detaylari']['p_value'] = round(p_value, 4)
                    if p_value < 0.01 and dusus_orani < -20:
                        suspicion_score += 5
                except:
                    pass
            
            # SÜREKLİ DÜŞÜŞ
            if self._check_continuous_decline(after_period):
                suspicion_score += 5
                results['analiz_detaylari']['surekli_dusus'] = 'VAR'
            else:
                results['analiz_detaylari']['surekli_dusus'] = 'YOK'
            
            results['süphe_puani'] = min(100, round(suspicion_score))
            
            if results['süphe_puani'] >= 60:
                results['manipulasyon_olasiligi'] = 'YÜKSEK'
            elif results['süphe_puani'] >= 35:
                results['manipulasyon_olasiligi'] = 'ORTA'
            
            results['ortalama_oncesi'] = round(before_mean, 1)
            results['ortalama_sonrasi'] = round(after_mean, 1)
            results['analiz_edilen_aylar'] = len(df)
            
            return results
            
        except Exception as e:
            return None
    
    def _seasonal_adjustment(self, df):
        adjusted = []
        for _, row in df.iterrows():
            month = row['tarih'].month
            season = self._get_season(month)
            seasonal_factors = {'kış': 1.4, 'yaz': 0.6, 'geçiş': 0.95}
            adjusted.append(row['tuketim'] / seasonal_factors[season])
        return np.array(adjusted)
    
    def _get_season(self, month):
        for season, months in self.season_months.items():
            if month in months:
                return season
        return 'geçiş'
    
    def _check_seasonal_mismatch(self, before_df, after_df):
        try:
            before_monthly = before_df.groupby(before_df['tarih'].dt.month)['tuketim'].mean()
            after_monthly = after_df.groupby(after_df['tarih'].dt.month)['tuketim'].mean()
            common_months = set(before_monthly.index) & set(after_monthly.index)
            
            if len(common_months) < 3:
                return 0
            
            deviations = []
            for month in common_months:
                before_val = before_monthly[month]
                after_val = after_monthly[month]
                if before_val > 0:
                    deviation = ((before_val - after_val) / before_val) * 100
                    if deviation > 0:
                        deviations.append(deviation)
            
            return np.mean(deviations) if deviations else 0
        except:
            return 0
    
    def _analyze_trend_change(self, before_df, after_df):
        try:
            if len(before_df) < 3 or len(after_df) < 3:
                return False
            
            x_before = np.arange(len(before_df))
            y_before = before_df['tuketim'].values
            slope_before = np.polyfit(x_before, y_before, 1)[0]
            
            x_after = np.arange(len(after_df))
            y_after = after_df['tuketim'].values
            slope_after = np.polyfit(x_after, y_after, 1)[0]
            
            return slope_before >= -0.5 and slope_after < -2.0
        except:
            return False
    
    def _check_continuous_decline(self, df):
        if len(df) < 4:
            return False
        try:
            first_months = df.head(min(6, len(df)))
            values = first_months['tuketim'].values
            decreasing_count = sum(1 for i in range(1, len(values)) if values[i] < values[i-1])
            return decreasing_count / (len(values) - 1) >= 0.7
        except:
            return False
    
    def _ml_anomaly_detection(self, df, point_idx):
        try:
            if len(df) < 12:
                return 0
            
            features = []
            for i in range(len(df)):
                tuketim = df.iloc[i]['tuketim']
                month = df.iloc[i]['tarih'].month
                
                if i >= 3:
                    prev_3_avg = df.iloc[i-3:i]['tuketim'].mean()
                else:
                    prev_3_avg = tuketim
                
                features.append([tuketim, month, prev_3_avg, abs(tuketim - prev_3_avg)])
            
            features = np.array(features)
            clf = IsolationForest(contamination=0.1, random_state=42)
            clf.fit(features)
            scores = clf.decision_function(features)
            
            min_score = scores.min()
            max_score = scores.max()
            
            if max_score > min_score:
                normalized_score = (scores[point_idx] - min_score) / (max_score - min_score)
                return 1 - normalized_score
            
            return 0
        except:
            return 0

# STREAMLIT ARAYÜZÜ
st.set_page_config(page_title="Gaz Sayacı Manipülasyon Tespiti", layout="wide", page_icon="🔥")
st.title("🔥 Gaz Sayacı Manipülasyon Tespit Sistemi - Hibrit")
st.markdown("---")

with st.sidebar:
    st.header("📊 Veri Yükleme")
    uploaded_file = st.file_uploader("Excel dosyanızı yükleyin", type=['xlsx', 'xls'])
    
    st.markdown("---")
    st.markdown("### 📋 Gerekli Kolonlar:")
    st.code("tesisat_no\nbina_no\ntarih\ntuketim")
    
    st.markdown("---")
    st.info("🆕 **Hibrit Özellikler:**\n- 6 kriter analizi\n- ML anomali tespiti\n- Dinamik puanlama")
    
    st.markdown("---")
    st.markdown("### ⚙️ Ayarlar")
    min_suspicion = st.slider("Yüksek Risk Eşiği", 50, 80, 60)
    min_suspicion_medium = st.slider("Orta Risk Eşiği", 20, 50, 35)

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        
        required_columns = ['tesisat_no', 'bina_no', 'tarih', 'tuketim']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            st.error(f"❌ Eksik kolonlar: {', '.join(missing_columns)}")
            st.stop()
        
        df['tarih'] = pd.to_datetime(df['tarih'])
        st.success(f"✅ Veri yüklendi! {len(df)} kayıt")
        
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
        
        if st.button("🔍 Hibrit Analiz Başlat", type="primary"):
            analyzer = GazSayacHibritAnaliz()
            
            with st.spinner("Analiz yapılıyor..."):
                results = []
                tesisat_list = df['tesisat_no'].unique()
                progress_bar = st.progress(0)
                
                for i, tesisat_no in enumerate(tesisat_list):
                    result = analyzer.detect_manipulation_hybrid(df, tesisat_no)
                    if result:
                        if result['süphe_puani'] >= min_suspicion:
                            result['manipulasyon_olasiligi'] = 'YÜKSEK'
                        elif result['süphe_puani'] >= min_suspicion_medium:
                            result['manipulasyon_olasiligi'] = 'ORTA'
                        else:
                            result['manipulasyon_olasiligi'] = 'DÜŞÜK'
                        results.append(result)
                    progress_bar.progress((i + 1) / len(tesisat_list))
                
                results_df = pd.DataFrame(results)
            
            st.success(f"✅ Analiz tamamlandı! {len(results_df)} tesisat")
            
            st.markdown("---")
            st.header("📈 Sonuçlar")
            
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
            
            col1, col2 = st.columns(2)
            
            with col1:
                fig1 = px.pie(results_df, names='manipulasyon_olasiligi', 
                             title='Risk Dağılımı',
                             color='manipulasyon_olasiligi',
                             color_discrete_map={'YÜKSEK': '#ff4444', 'ORTA': '#ffaa00', 'DÜŞÜK': '#44ff44'})
                st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                fig2 = px.histogram(results_df, x='süphe_puani', 
                                   title='Şüphe Puanı Dağılımı', nbins=20,
                                   color='manipulasyon_olasiligi',
                                   color_discrete_map={'YÜKSEK': '#ff4444', 'ORTA': '#ffaa00', 'DÜŞÜK': '#44ff44'})
                st.plotly_chart(fig2, use_container_width=True)
            
            st.markdown("---")
            st.subheader("🔍 Detaylı Sonuçlar")
            
            risk_filter = st.multiselect("Risk Filtrele:", 
                                        ['YÜKSEK', 'ORTA', 'DÜŞÜK'],
                                        default=['YÜKSEK', 'ORTA'])
            
            filtered_df = results_df[results_df['manipulasyon_olasiligi'].isin(risk_filter)]
            filtered_df = filtered_df.sort_values('süphe_puani', ascending=False)
            
            display_df = filtered_df[['tesisat_no', 'bina_no', 'rekor_tarihi', 'rekor_degeri', 
                                     'süphe_puani', 'manipulasyon_olasiligi', 
                                     'ortalama_oncesi', 'ortalama_sonrasi']].copy()
            display_df['rekor_tarihi'] = display_df['rekor_tarihi'].dt.strftime('%Y-%m-%d')
            
            st.dataframe(display_df, use_container_width=True, height=400)
            
            from io import BytesIO
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                filtered_df.to_excel(writer, index=False, sheet_name='Sonuçlar')
            buffer.seek(0)
            
            st.download_button(
                label="📥 Excel İndir",
                data=buffer,
                file_name=f"hibrit_analiz_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            if len(filtered_df) > 0:
                st.markdown("---")
                st.subheader("🔬 Tesisat Detayı")
                
                selected_tesisat = st.selectbox("Tesisat Seçin:", filtered_df['tesisat_no'].tolist())
                
                if selected_tesisat:
                    tesisat_data = df[df['tesisat_no'] == selected_tesisat].sort_values('tarih')
                    result = filtered_df[filtered_df['tesisat_no'] == selected_tesisat].iloc[0]
                    
                    fig3 = go.Figure()
                    fig3.add_trace(go.Scatter(
                        x=tesisat_data['tarih'], 
                        y=tesisat_data['tuketim'],
                        mode='lines+markers', 
                        name='Tüketim',
                        line=dict(color='blue', width=2)
                    ))
                    
                    fig3.add_vline(x=result['rekor_tarihi'], line_dash="dash", 
                                  line_color="red", annotation_text="Rekor")
                    
                    fig3.update_layout(
                        title=f"Tesisat {selected_tesisat}",
                        xaxis_title="Tarih", 
                        yaxis_title="Tüketim"
                    )
                    st.plotly_chart(fig3, use_container_width=True)
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Şüphe Puanı", f"{result['süphe_puani']}/100")
                    with col2:
                        st.metric("Risk", result['manipulasyon_olasiligi'])
                    with col3:
                        degisim = ((result['ortalama_sonrasi'] - result['ortalama_oncesi']) / 
                                  result['ortalama_oncesi'] * 100) if result['ortalama_oncesi'] > 0 else 0
                        st.metric("Değişim", f"{degisim:.1f}%")
                    with col4:
                        st.metric("Analiz Ayları", result['analiz_edilen_aylar'])
                    
                    if 'analiz_detaylari' in result:
                        st.markdown("### 📊 Kriter Detayları")
                        detaylar = result['analiz_detaylari']
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            if 'rekor_orani' in detaylar:
                                st.metric("Rekor Oranı", f"{detaylar['rekor_orani']}x")
                            if 'ilk_3_ay_dusus' in detaylar:
                                st.metric("İlk 3 Ay Düşüş", f"{detaylar['ilk_3_ay_dusus']:.1f}%")
                        
                        with col2:
                            if 'mevsimsel_uyumsuzluk' in detaylar:
                                st.metric("Mevsimsel Uyumsuzluk", f"{detaylar['mevsimsel_uyumsuzluk']:.1f}%")
                            if 'trend_degisimi' in detaylar:
                                st.metric("Trend Değişimi", detaylar['trend_degisimi'])
                        
                        with col3:
                            if 'varyans_degisimi' in detaylar:
                                st.metric("Varyans Değişimi", f"{detaylar['varyans_degisimi']:.1f}%")
                            if 'ml_anomali_skoru' in detaylar:
                                st.metric("ML Anomali", f"{detaylar['ml_anomali_skoru']:.2f}")
        
    except Exception as e:
        st.error(f"❌ Hata: {str(e)}")
        st.info("Excel dosyanızın formatını kontrol edin.")

else:
    st.info("👈 Sol menüden Excel dosyanızı yükleyin")
    
    st.markdown("### 📖 Kullanım")
    st.markdown("""
    1. Excel dosyanız şu kolonları içermeli: `tesisat_no`, `bina_no`, `tarih`, `tuketim`
    2. Sol menüden dosyayı yükleyin
    3. "Hibrit Analiz Başlat" butonuna tıklayın
    4. Sonuçları Excel olarak indirin
    """)
    
    st.markdown("### 📊 Örnek Format")
    example_data = pd.DataFrame({
        'tesisat_no': ['T001', 'T001', 'T001'],
        'bina_no': ['B001', 'B001', 'B001'],
        'tarih': ['2023-01-15', '2023-02-15', '2023-03-15'],
        'tuketim': [120, 135, 98]
    })
    st.dataframe(example_data, use_container_width=True)
