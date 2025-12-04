import streamlit as st
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(page_title="Doğalgaz Kaçak Kullanım Tespit", page_icon="⚠️", layout="wide")

class GasFraudDetector:
    """
    Doğalgaz kaçak kullanım anomali tespit sistemi
    
    VERİDEKİ PATTERN ANALİZİ:
    -------------------------
    Yüklediğiniz PDF'deki verilerde şu patternleri tespit ettim:
    
    1. SIKÇA SIFIR TÜKETİM: Bazı tesisatlar uzun süre 0 değer gösteriyor
       Örnek: Tesisat 10100311, 10109574, 10219911 - aylarca 0 tüketim
       → Bu ANORMAL: Ev boş değilse sayaca müdahale şüphesi
    
    2. ANİ DÜŞÜŞLER: Normal tüketimden aniden çok düşük değerlere düşüş
       Örnek: Tesisat 10004494 → 165 tondan 19 tona düşmüş (90% düşüş)
       → Sayaç manipülasyonu işareti
    
    3. UZUN SÜRELİ DÜŞÜK TÜKETİM: 10+ ay boyunca çok düşük değerler
       Örnek: Tesisat 10410643, 10415131 - sürekli 0-5 ton arası
       → Kaçak kullanım paterni
    
    4. AŞİRİ DEĞİŞKENLİK: Bir ay 200, bir ay 5, bir ay 300
       → Tutarsız, şüpheli davranış
    
    5. MEVSİMSEL ANORMALLIK: Kış-yaz farkı olmaması
       → Normal evlerde kışın 3-4 kat fazla tüketim olmalı
    """
    
    def __init__(self, contamination=0.15):
        self.contamination = contamination
        self.scaler = StandardScaler()
        self.model = IsolationForest(contamination=contamination, random_state=42, n_estimators=100)
        
    def load_excel(self, uploaded_file):
        """Excel/CSV dosyasını yükle"""
        try:
            # Excel ise
            if uploaded_file.name.endswith('.xlsx') or uploaded_file.name.endswith('.xls'):
                df = pd.read_excel(uploaded_file, header=None)
            # CSV ise
            else:
                # Boşlukla ayrılmış format
                df = pd.read_csv(uploaded_file, sep=r'\s+', header=None, engine='python')
            
            # İlk sütun tesisat ID'si
            self.facility_ids = df.iloc[:, 0].astype(str).values
            # Diğer sütunlar tüketim değerleri
            self.consumption_data = df.iloc[:, 1:].apply(pd.to_numeric, errors='coerce').values
            
            return df
        except Exception as e:
            st.error(f"Dosya yükleme hatası: {str(e)}")
            return None
    
    def extract_features(self):
        """
        Kaçak kullanım patternlerini tespit etmek için özellikler çıkar
        
        ÇIKARILAN ÖZELLİKLER:
        1. Sıfır tüketim oranı (en önemli)
        2. Ani düşüş sayısı
        3. Maksimum düşüş yüzdesi
        4. Ardışık düşük tüketim ay sayısı
        5. Tüketim değişkenliği (düzensizlik)
        6. Negatif trend dönem sayısı
        7. Mevsimsel düzensizlik
        """
        features = []
        
        progress_bar = st.progress(0)
        total = len(self.consumption_data)
        
        for i, row in enumerate(self.consumption_data):
            progress_bar.progress((i + 1) / total)
            
            # NaN değerleri temizle
            row_clean = row[~np.isnan(row)]
            row_clean = row_clean[row_clean >= 0]  # Negatif değerleri de temizle
            
            if len(row_clean) == 0:
                continue
            
            # Sıfır olmayan değerler
            row_nonzero = row_clean[row_clean > 0]
            
            if len(row_nonzero) == 0:
                row_nonzero = np.array([0.001])  # Tüm değerler sıfırsa
                
            feature_dict = {
                'facility_id': self.facility_ids[i],
                
                # 1. SIFIR/DÜŞÜK TÜKETİM ANALİZİ (EN ÖNEMLİ!)
                'zero_count': int(np.sum(row_clean == 0)),
                'zero_ratio': float(np.sum(row_clean == 0) / len(row_clean)),
                'low_consumption_count': int(np.sum(row_clean < 5)),
                'low_consumption_ratio': float(np.sum(row_clean < 5) / len(row_clean)),
                
                # 2. ANİ DEĞİŞİMLER
                'sudden_drops': int(self._count_sudden_changes(row_clean, threshold=0.5, direction='down')),
                'sudden_spikes': int(self._count_sudden_changes(row_clean, threshold=0.8, direction='up')),
                'max_drop_percentage': float(self._max_change_ratio(row_clean, direction='down') * 100),
                'max_spike_percentage': float(self._max_change_ratio(row_clean, direction='up') * 100),
                
                # 3. UZUN SÜRELİ DÜŞÜK TÜKETİM
                'consecutive_zero_months': int(self._max_consecutive(row_clean, value=0)),
                'consecutive_low_months': int(self._max_consecutive_low(row_clean, threshold=10)),
                
                # 4. TEMEL İSTATİSTİKLER
                'mean_consumption': float(np.mean(row_nonzero)),
                'std_consumption': float(np.std(row_nonzero)),
                'median_consumption': float(np.median(row_nonzero)),
                'max_consumption': float(np.max(row_nonzero)),
                'min_consumption': float(np.min(row_nonzero)),
                
                # 5. DEĞİŞKENLİK
                'coefficient_of_variation': float(np.std(row_nonzero) / np.mean(row_nonzero) if np.mean(row_nonzero) > 0 else 0),
                'range_ratio': float((np.max(row_nonzero) - np.min(row_nonzero)) / np.mean(row_nonzero) if np.mean(row_nonzero) > 0 else 0),
                
                # 6. TREND ANALİZİ
                'overall_trend': float(self._calculate_trend(row_nonzero)),
                'negative_trend_periods': int(self._count_negative_trends(row_clean)),
                
                # 7. MEVSİMSEL ANORMALLIK
                'seasonal_variation': float(self._calculate_seasonal_variation(row_clean)),
                'missing_winter_peak': int(self._check_missing_winter_peak(row_clean)),
            }
            
            features.append(feature_dict)
        
        progress_bar.empty()
        return pd.DataFrame(features)
    
    def _count_sudden_changes(self, data, threshold=0.5, direction='down'):
        """Ani değişim sayısı"""
        if len(data) < 2:
            return 0
        changes = np.diff(data) / (data[:-1] + 0.001)
        if direction == 'down':
            return np.sum(changes < -threshold)
        else:
            return np.sum(changes > threshold)
    
    def _max_change_ratio(self, data, direction='down'):
        """Maksimum değişim oranı"""
        if len(data) < 2:
            return 0
        changes = np.diff(data) / (data[:-1] + 0.001)
        if direction == 'down':
            return abs(np.min(changes)) if len(changes) > 0 else 0
        else:
            return np.max(changes) if len(changes) > 0 else 0
    
    def _max_consecutive(self, data, value=0):
        """Ardışık belirli değer sayısı"""
        count = 0
        max_count = 0
        for val in data:
            if val == value:
                count += 1
                max_count = max(max_count, count)
            else:
                count = 0
        return max_count
    
    def _max_consecutive_low(self, data, threshold=10):
        """Ardışık düşük tüketim periyodu"""
        count = 0
        max_count = 0
        for val in data:
            if val < threshold:
                count += 1
                max_count = max(max_count, count)
            else:
                count = 0
        return max_count
    
    def _calculate_trend(self, data):
        """Genel trend"""
        if len(data) < 2:
            return 0
        x = np.arange(len(data))
        return np.polyfit(x, data, 1)[0]
    
    def _count_negative_trends(self, data, window=6):
        """Negatif trend dönem sayısı"""
        if len(data) < window:
            return 0
        count = 0
        for i in range(len(data) - window + 1):
            window_data = data[i:i+window]
            if self._calculate_trend(window_data) < -1:
                count += 1
        return count
    
    def _calculate_seasonal_variation(self, data):
        """Mevsimsel varyasyon (kış-yaz farkı)"""
        if len(data) < 12:
            return 0
        # 12 aylık periyotlara böl
        years = len(data) // 12
        if years == 0:
            return 0
        
        variations = []
        for year in range(years):
            year_data = data[year*12:(year+1)*12]
            if len(year_data) == 12:
                winter = np.mean([year_data[11], year_data[0], year_data[1]])  # Aralık, Ocak, Şubat
                summer = np.mean([year_data[5], year_data[6], year_data[7]])   # Haziran, Temmuz, Ağustos
                if summer > 0:
                    variations.append((winter - summer) / summer)
        
        return np.mean(variations) if len(variations) > 0 else 0
    
    def _check_missing_winter_peak(self, data):
        """Kış zirvesi eksikliği kontrolü"""
        if len(data) < 12:
            return 0
        years = len(data) // 12
        missing_count = 0
        
        for year in range(years):
            year_data = data[year*12:(year+1)*12]
            if len(year_data) == 12:
                winter_avg = np.mean([year_data[11], year_data[0], year_data[1]])
                summer_avg = np.mean([year_data[5], year_data[6], year_data[7]])
                # Normal evlerde kış en az 1.5 kat fazla olmalı
                if winter_avg < summer_avg * 1.2:
                    missing_count += 1
        
        return missing_count
    
    def calculate_risk_score(self, features_df):
        """
        Kaçak kullanım risk skoru hesapla
        
        AĞIRLIKLAR (verimizdeki patternlere göre):
        - Sıfır tüketim oranı: x100 (en önemli!)
        - Ardışık sıfır aylar: x20
        - Ani düşüş: x15
        - Düşük tüketim oranı: x50
        """
        risk = np.zeros(len(features_df))
        
        # 1. Sıfır tüketim (ÇOK ÖNEMLİ!)
        risk += features_df['zero_ratio'] * 100
        risk += features_df['consecutive_zero_months'] * 20
        
        # 2. Düşük tüketim
        risk += features_df['low_consumption_ratio'] * 50
        risk += features_df['consecutive_low_months'] * 10
        
        # 3. Ani düşüşler
        risk += features_df['sudden_drops'] * 15
        risk += features_df['max_drop_percentage'] / 10
        
        # 4. Negatif trendler
        risk += features_df['negative_trend_periods'] * 12
        
        # 5. Mevsimsel anormallik
        risk += features_df['missing_winter_peak'] * 8
        
        # 6. Yüksek değişkenlik
        risk += features_df['coefficient_of_variation'] * 5
        
        return risk
    
    def detect_anomalies(self, features_df):
        """Anomali tespiti"""
        facility_ids = features_df['facility_id'].values
        feature_columns = features_df.drop('facility_id', axis=1)
        
        # Normalizasyon
        features_scaled = self.scaler.fit_transform(feature_columns)
        
        # ML modeli ile anomali tespiti
        predictions = self.model.fit_predict(features_scaled)
        anomaly_scores = self.model.score_samples(features_scaled)
        
        # Sonuçlar
        results = features_df.copy()
        results['is_anomaly'] = predictions == -1
        results['ml_anomaly_score'] = -anomaly_scores
        results['risk_score'] = self.calculate_risk_score(features_df)
        
        # Risk seviyesi
        results['risk_level'] = pd.cut(results['risk_score'], 
                                       bins=[-np.inf, 20, 50, 100, np.inf],
                                       labels=['Düşük', 'Orta', 'Yüksek', 'Çok Yüksek'])
        
        return results.sort_values('risk_score', ascending=False)


def create_excel_download(df):
    """Excel indirme butonu oluştur"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Anomali Tespiti')
    output.seek(0)
    return output


def main():
    st.title("⚠️ Doğalgaz Kaçak Kullanım Anomali Tespit Sistemi")
    
    st.markdown("""
    ### 📊 Sistem Nasıl Çalışır?
    
    **Verinizdeki şüpheli patternleri tespit eder:**
    
    1. **Sıfır/Düşük Tüketim**: Uzun süre sıfır veya çok düşük tüketim (sayaç manipülasyonu)
    2. **Ani Düşüşler**: Normal tüketimden aniden %50+ düşüş
    3. **Uzun Süreli Düşük Dönemler**: 6+ ay boyunca düşük tüketim
    4. **Mevsimsel Anormallik**: Kış-yaz farkı olmaması (normal evlerde kış 2-3x fazla)
    5. **Düzensizlik**: Tutarsız, aşırı değişken tüketim paterni
    
    ---
    """)
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Ayarlar")
        contamination = st.slider(
            "Beklenen Anomali Oranı (%)",
            min_value=5,
            max_value=30,
            value=15,
            help="Verinizdeki kaçak kullanım oranı tahmini. Daha yüksek değer = daha fazla tespit"
        ) / 100
        
        st.markdown("---")
        st.markdown("""
        ### 📁 Dosya Formatı
        - Excel (.xlsx, .xls)
        - CSV (virgül/boşluk ayrılmış)
        
        **Sütun Yapısı:**
        - 1. Sütun: Tesisat ID
        - Diğer Sütunlar: Aylık tüketim değerleri
        """)
    
    # Dosya yükleme
    uploaded_file = st.file_uploader(
        "📂 Excel/CSV Dosyanızı Yükleyin",
        type=['xlsx', 'xls', 'csv', 'txt'],
        help="Tesisat ID'leri ve aylık tüketim değerlerini içeren dosya"
    )
    
    if uploaded_file is not None:
        try:
            # Dedektör oluştur
            detector = GasFraudDetector(contamination=contamination)
            
            # Veriyi yükle
            with st.spinner("📥 Veri yükleniyor..."):
                df = detector.load_excel(uploaded_file)
                
            if df is not None:
                st.success(f"✅ {len(df)} tesisat yüklendi!")
                
                # Veri önizleme
                with st.expander("👁️ Veri Önizleme (İlk 10 Satır)"):
                    st.dataframe(df.head(10))
                
                # Analiz butonu
                if st.button("🔍 ANOMALİ TESPİTİ BAŞLAT", type="primary"):
                    
                    # Özellik çıkarma
                    with st.spinner("🔧 Özellikler çıkarılıyor..."):
                        features = detector.extract_features()
                    
                    st.success(f"✅ {len(features)} tesisat için özellikler çıkarıldı")
                    
                    # Anomali tespiti
                    with st.spinner("🤖 Makine öğrenmesi modeli çalışıyor..."):
                        results = detector.detect_anomalies(features)
                    
                    # SONUÇLAR
                    st.markdown("---")
                    st.header("📊 ANALİZ SONUÇLARI")
                    
                    # Özet metrikler
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Toplam Tesisat", len(results))
                    with col2:
                        anomaly_count = results['is_anomaly'].sum()
                        st.metric("Tespit Edilen Anomali", anomaly_count)
                    with col3:
                        anomaly_rate = (anomaly_count / len(results) * 100)
                        st.metric("Anomali Oranı", f"{anomaly_rate:.1f}%")
                    with col4:
                        high_risk = (results['risk_level'].isin(['Yüksek', 'Çok Yüksek'])).sum()
                        st.metric("Yüksek Risk", high_risk)
                    
                    # Risk dağılımı
                    st.subheader("📈 Risk Seviyesi Dağılımı")
                    risk_dist = results['risk_level'].value_counts()
                    fig = px.pie(values=risk_dist.values, names=risk_dist.index, 
                                color_discrete_sequence=['green', 'yellow', 'orange', 'red'])
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # En şüpheli tesisatlar
                    st.subheader("🚨 EN ŞÜPHELİ TESİSATLAR")
                    
                    top_n = st.slider("Gösterilecek tesisat sayısı", 10, 50, 20)
                    top_suspicious = results.head(top_n)
                    
                    # Önemli sütunları seç
                    display_cols = [
                        'facility_id', 'risk_score', 'risk_level', 'is_anomaly',
                        'zero_ratio', 'zero_count', 'consecutive_zero_months',
                        'low_consumption_ratio', 'sudden_drops', 'max_drop_percentage',
                        'consecutive_low_months', 'mean_consumption'
                    ]
                    
                    # Yüzdeleri düzenle
                    display_df = top_suspicious[display_cols].copy()
                    display_df['zero_ratio'] = (display_df['zero_ratio'] * 100).round(1)
                    display_df['low_consumption_ratio'] = (display_df['low_consumption_ratio'] * 100).round(1)
                    display_df['max_drop_percentage'] = display_df['max_drop_percentage'].round(1)
                    display_df['mean_consumption'] = display_df['mean_consumption'].round(2)
                    display_df['risk_score'] = display_df['risk_score'].round(2)
                    
                    # Sütun isimlerini Türkçeleştir
                    display_df.columns = [
                        'Tesisat ID', 'Risk Skoru', 'Risk Seviyesi', 'Anomali',
                        'Sıfır Tük. %', 'Sıfır Ay', 'Ardışık Sıfır',
                        'Düşük Tük. %', 'Ani Düşüş', 'Maks Düşüş %',
                        'Ardışık Düşük Ay', 'Ort. Tüketim'
                    ]
                    
                    # Renkli tablo
                    st.dataframe(
                        display_df.style.background_gradient(subset=['Risk Skoru'], cmap='Reds'),
                        use_container_width=True,
                        height=600
                    )
                    
                    # Risk skoru dağılımı
                    st.subheader("📊 Risk Skoru Dağılımı")
                    fig2 = px.histogram(results, x='risk_score', nbins=50,
                                       labels={'risk_score': 'Risk Skoru', 'count': 'Tesisat Sayısı'})
                    st.plotly_chart(fig2, use_container_width=True)
                    
                    # Excel indirme butonları
                    st.markdown("---")
                    st.subheader("💾 Sonuçları İndir")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Tüm sonuçlar
                        excel_all = create_excel_download(results)
                        st.download_button(
                            label="📥 Tüm Sonuçları İndir (Excel)",
                            data=excel_all,
                            file_name="tum_anomali_sonuclari.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    
                    with col2:
                        # Sadece şüpheliler
                        suspicious_only = results[results['risk_level'].isin(['Yüksek', 'Çok Yüksek'])]
                        excel_suspicious = create_excel_download(suspicious_only)
                        st.download_button(
                            label="📥 Sadece Şüpheli Tesisatlar (Excel)",
                            data=excel_suspicious,
                            file_name="supheli_tesisatlar.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    
                    # Detaylı açıklama
                    with st.expander("ℹ️ Risk Skoru Nasıl Hesaplanıyor?"):
                        st.markdown("""
                        **Risk Skoru Formülü:**
                        
                        - **Sıfır Tüketim Oranı** × 100 (en önemli faktör)
                        - **Ardışık Sıfır Aylar** × 20
                        - **Düşük Tüketim Oranı** × 50
                        - **Ardışık Düşük Aylar** × 10
                        - **Ani Düşüş Sayısı** × 15
                        - **Maksimum Düşüş Yüzdesi** ÷ 10
                        - **Negatif Trend Dönemleri** × 12
                        - **Mevsimsel Anormallik** × 8
                        - **Değişkenlik Katsayısı** × 5
                        
                        **Risk Seviyeleri:**
                        - 🟢 Düşük: 0-20
                        - 🟡 Orta: 20-50
                        - 🟠 Yüksek: 50-100
                        - 🔴 Çok Yüksek: 100+
                        """)
                        
        except Exception as e:
            st.error(f"❌ Hata oluştu: {str(e)}")
            st.info("Lütfen dosya formatını kontrol edin. İlk sütun Tesisat ID, diğer sütunlar aylık tüketim değerleri olmalı.")


if __name__ == "__main__":
    main()
