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
    page_title="Doğalgaz Kaçak Tespit Sistemi",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 Doğalgaz Kaçak Tespit Sistemi - Gelişmiş v3")
st.markdown("---")

# Yan panel
st.sidebar.header("📁 Dosya Yükleme")
uploaded_file = st.sidebar.file_uploader(
    "CSV veya Excel dosyası seçin",
    type=['csv', 'xlsx', 'xls']
)

# Parametreler
st.sidebar.header("⚙️ Tespit Parametreleri")

normal_kis_esik = st.sidebar.slider(
    "Normal kış tüketimi eşiği (m³/ay)",
    min_value=30, max_value=150, value=60,
    help="Bu değerin üzerindeki kış tüketimi 'normal' kabul edilir"
)

dusuk_tuketim_esik = st.sidebar.slider(
    "Düşük tüketim eşiği (m³/ay)",
    min_value=5, max_value=50, value=25,
    help="Bu değerin altındaki tüketim 'şüpheli' kabul edilir"
)

min_dusus_orani = st.sidebar.slider(
    "Minimum düşüş oranı (%)",
    min_value=30, max_value=80, value=50,
    help="Bu oranda düşüş kaçak şüphesi oluşturur"
)

agresif_mod = st.sidebar.checkbox(
    "🔥 Agresif Tespit Modu",
    value=True,
    help="Daha fazla kaçak tespit eder, ancak yanlış pozitif artabilir"
)

def load_data(file):
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Dosya yükleme hatası: {str(e)}")
        return None

def parse_date_columns(df):
    date_columns = []
    other_columns = []
    
    for col in df.columns:
        if isinstance(col, str) and '/' in col:
            try:
                parts = col.split('/')
                year = parts[0]
                month = parts[1] if len(parts) > 1 else '1'
                if len(year) == 4 and 1 <= int(month) <= 12:
                    date_columns.append(col)
                else:
                    other_columns.append(col)
            except:
                other_columns.append(col)
        else:
            other_columns.append(col)
    
    return sorted(date_columns), other_columns

def get_season(month):
    if month in [12, 1, 2]:
        return "Kış"
    elif month in [3, 4, 5]:
        return "İlkbahar"
    elif month in [6, 7, 8]:
        return "Yaz"
    else:
        return "Sonbahar"

def detect_leak_comprehensive(df, date_columns, tesisat_col, bina_col, params):
    """KAPSAMLI KAÇAK TESPİT SİSTEMİ - TÜM PATERNLER"""
    results = []
    
    for idx, row in df.iterrows():
        tesisat_no = row[tesisat_col]
        bina_no = row[bina_col]
        
        # Tüm aylık verileri topla
        monthly_data = []
        for date_col in date_columns:
            try:
                value = row[date_col]
                if pd.notna(value):
                    year, month = date_col.split('/')
                    monthly_data.append({
                        'year': int(year),
                        'month': int(month),
                        'consumption': float(value),
                        'season': get_season(int(month)),
                        'date_str': date_col,
                        'date_col': date_col
                    })
            except:
                continue
        
        if len(monthly_data) < 4:
            continue
        
        cons_df = pd.DataFrame(monthly_data)
        cons_df = cons_df.sort_values(['year', 'month']).reset_index(drop=True)
        
        # ===========================================
        # VERİ ÖN ANALİZ
        # ===========================================
        
        total_months = len(cons_df)
        avg_consumption = cons_df['consumption'].mean()
        median_consumption = cons_df['consumption'].median()
        max_consumption = cons_df['consumption'].max()
        min_consumption = cons_df['consumption'].min()
        
        # Sıfır olmayan değerler
        non_zero = cons_df[cons_df['consumption'] > 0]
        if len(non_zero) > 0:
            avg_non_zero = non_zero['consumption'].mean()
            median_non_zero = non_zero['consumption'].median()
        else:
            avg_non_zero = 0
            median_non_zero = 0
        
        # ===========================================
        # KAÇAK TESPİT MANTIKLARI (12 FARKLI YÖNTEM)
        # ===========================================
        
        anomalies = []
        leak_score = 0
        detected_patterns = []
        
        # ========== YÖNTEM 1: ZAMAN DİLİMLERİ ANALİZİ ==========
        # Her 6 aylık dilimlere böl ve karşılaştır
        if total_months >= 12:
            chunks = []
            for i in range(0, total_months, 6):
                chunk = cons_df.iloc[i:i+6]
                if len(chunk) >= 3:
                    chunks.append({
                        'start': i,
                        'end': i+len(chunk),
                        'avg': chunk['consumption'].mean(),
                        'median': chunk['consumption'].median(),
                        'max': chunk['consumption'].max(),
                        'period': f"{chunk.iloc[0]['date_str']} - {chunk.iloc[-1]['date_str']}"
                    })
            
            # İlk dilim ile sonraki dilimleri karşılaştır
            if len(chunks) >= 2:
                first_chunk = chunks[0]
                
                for i, chunk in enumerate(chunks[1:], 1):
                    if first_chunk['avg'] >= params['normal_kis_esik']:
                        dusus = ((first_chunk['avg'] - chunk['avg']) / first_chunk['avg']) * 100
                        
                        if dusus >= params['min_dusus_orani']:
                            if chunk['avg'] == 0:
                                anomalies.append(f"🚨 DÖNEM-{i}: Sıfıra düştü ({first_chunk['period']}: {first_chunk['avg']:.1f} → {chunk['period']}: 0)")
                                leak_score += 50
                                detected_patterns.append("Sıfıra Düşüş")
                            elif chunk['avg'] < params['dusuk_tuketim_esik']:
                                anomalies.append(f"⚠️ DÖNEM-{i}: Kritik düşüş ({first_chunk['avg']:.1f} → {chunk['avg']:.1f}, %{dusus:.0f})")
                                leak_score += 40
                                detected_patterns.append("Kritik Düşüş")
                            else:
                                anomalies.append(f"📉 DÖNEM-{i}: Ciddi düşüş (%{dusus:.0f})")
                                leak_score += 25
                                detected_patterns.append("Ciddi Düşüş")
        
        # ========== YÖNTEM 2: YILLIK KARŞILAŞTIRMA ==========
        yearly_avg = cons_df.groupby('year')['consumption'].mean()
        years = sorted(yearly_avg.index)
        
        if len(years) >= 2:
            first_year_avg = yearly_avg[years[0]]
            last_year_avg = yearly_avg[years[-1]]
            
            if first_year_avg >= params['normal_kis_esik']:
                year_dusus = ((first_year_avg - last_year_avg) / first_year_avg) * 100
                
                if year_dusus >= params['min_dusus_orani']:
                    anomalies.append(f"📅 YILLIK: {years[0]} ({first_year_avg:.1f}) → {years[-1]} ({last_year_avg:.1f}), %{year_dusus:.0f} düşüş")
                    leak_score += 30
                    detected_patterns.append("Yıllık Düşüş")
        
        # ========== YÖNTEM 3: KIŞ AYLARINDA ÖZEL ANALİZ ==========
        kis_data = cons_df[cons_df['season'] == 'Kış'].copy()
        
        if len(kis_data) >= 3:
            # Her kış ayını ayrı değerlendir
            kis_values = kis_data['consumption'].values
            kis_dates = kis_data['date_str'].values
            
            # İlk kış ayları ortalaması
            first_kis = kis_values[:len(kis_values)//2]
            last_kis = kis_values[len(kis_values)//2:]
            
            if len(first_kis) > 0 and len(last_kis) > 0:
                first_kis_avg = np.mean(first_kis)
                last_kis_avg = np.mean(last_kis)
                
                if first_kis_avg >= params['normal_kis_esik']:
                    kis_dusus = ((first_kis_avg - last_kis_avg) / first_kis_avg) * 100
                    
                    if kis_dusus >= params['min_dusus_orani']:
                        anomalies.append(f"❄️ KIŞ: İlk kışlar ({first_kis_avg:.1f}) → Son kışlar ({last_kis_avg:.1f}), %{kis_dusus:.0f} düşüş")
                        leak_score += 35
                        detected_patterns.append("Kış Düşüşü")
        
        # ========== YÖNTEM 4: HAREKET EDEN ORTALAMA ==========
        # Son 3 ay vs Önceki 3 ay karşılaştırması (kayan pencere)
        if total_months >= 12:
            window = 3
            max_drop = 0
            drop_location = None
            
            for i in range(window, total_months - window):
                before_avg = cons_df.iloc[i-window:i]['consumption'].mean()
                after_avg = cons_df.iloc[i:i+window]['consumption'].mean()
                
                if before_avg >= params['normal_kis_esik']:
                    drop = ((before_avg - after_avg) / before_avg) * 100
                    if drop > max_drop:
                        max_drop = drop
                        drop_location = (i-window, i+window)
            
            if max_drop >= params['min_dusus_orani']:
                start_date = cons_df.iloc[drop_location[0]]['date_str']
                end_date = cons_df.iloc[drop_location[1]-1]['date_str']
                anomalies.append(f"📊 KAYAN: {start_date} civarında %{max_drop:.0f} düşüş tespit edildi")
                leak_score += 20
                detected_patterns.append("Ani Değişim")
        
        # ========== YÖNTEM 5: SÜREKLİ DÜŞÜK TÜKETİM ==========
        low_count = len(cons_df[cons_df['consumption'] < params['dusuk_tuketim_esik']])
        zero_count = len(cons_df[cons_df['consumption'] == 0])
        
        if low_count >= total_months * 0.5:  # Yarısından fazlası düşük
            anomalies.append(f"📉 SÜREKLİ DÜŞÜK: {low_count}/{total_months} ay düşük tüketim")
            leak_score += 30
            detected_patterns.append("Sürekli Düşük")
        
        if zero_count >= 4:
            anomalies.append(f"⛔ SIFIR: {zero_count} ay sıfır tüketim")
            leak_score += 25
            detected_patterns.append("Sıfır Aylar")
        
        # ========== YÖNTEM 6: STANDART SAPMA ANALİZİ ==========
        if len(non_zero) > 0:
            std = non_zero['consumption'].std()
            cv = (std / avg_non_zero) if avg_non_zero > 0 else 0  # Varyasyon katsayısı
            
            # Yüksek varyasyon + düşük son değerler = şüpheli
            if cv > 0.8:  # Yüksek varyasyon
                son_5 = cons_df.tail(5)['consumption'].mean()
                if son_5 < avg_non_zero * 0.3:
                    anomalies.append(f"📈 VARYASYON: Yüksek dalgalanma ve düşük son değerler")
                    leak_score += 15
                    detected_patterns.append("Yüksek Varyasyon")
        
        # ========== YÖNTEM 7: MEVSİMSEL PATTERN ==========
        seasonal_avg = cons_df.groupby('season')['consumption'].mean()
        
        if 'Kış' in seasonal_avg.index and 'Yaz' in seasonal_avg.index:
            kis_avg = seasonal_avg['Kış']
            yaz_avg = seasonal_avg['Yaz']
            
            # Kış yaz farkı çok az ve her ikisi de düşük
            if kis_avg < params['dusuk_tuketim_esik'] and abs(kis_avg - yaz_avg) < 10:
                anomalies.append(f"🔍 MEVSİM: Kış-yaz farkı yok ve düşük (Kış: {kis_avg:.1f}, Yaz: {yaz_avg:.1f})")
                leak_score += 20
                detected_patterns.append("Mevsim Anomalisi")
        
        # ========== YÖNTEM 8: TOPLAM TÜKETİM ANALİZİ ==========
        total_consumption = cons_df['consumption'].sum()
        expected_min = total_months * 30  # Minimum beklenen (30 m³/ay)
        
        if total_consumption < expected_min:
            anomalies.append(f"💰 TOPLAM DÜŞÜK: {total_consumption:.1f} m³ (Beklenen min: {expected_min})")
            leak_score += 15
            detected_patterns.append("Toplam Düşük")
        
        # ========== YÖNTEM 9: SON AYLARA ÖZEL BAKIM ==========
        if total_months >= 6:
            son_6 = cons_df.tail(6)
            son_3 = cons_df.tail(3)
            
            son_6_avg = son_6['consumption'].mean()
            son_3_avg = son_3['consumption'].mean()
            
            # Son 6 ay çok düşük
            if avg_non_zero >= params['normal_kis_esik'] and son_6_avg < params['dusuk_tuketim_esik']:
                anomalies.append(f"🔴 SON 6 AY: Çok düşük tüketim ({son_6_avg:.1f})")
                leak_score += 35
                detected_patterns.append("Son Aylar Düşük")
            
            # Son 3 ay sıfır veya neredeyse sıfır
            if son_3_avg < 5:
                anomalies.append(f"🚨 SON 3 AY: Neredeyse sıfır ({son_3_avg:.1f})")
                leak_score += 40
                detected_patterns.append("Son Aylar Sıfır")
        
        # ========== YÖNTEM 10: TREND ANALİZİ (Linear Regression) ==========
        if total_months >= 12:
            x = np.arange(len(cons_df))
            y = cons_df['consumption'].values
            
            # Basit doğrusal trend
            if len(x) > 0 and np.std(y) > 0:
                z = np.polyfit(x, y, 1)
                slope = z[0]
                
                # Negatif trend (düşüş) ve yüksek başlangıç
                if slope < -2 and cons_df.head(6)['consumption'].mean() >= params['normal_kis_esik']:
                    anomalies.append(f"📉 TREND: Sürekli azalış trendi (eğim: {slope:.2f})")
                    leak_score += 20
                    detected_patterns.append("Negatif Trend")
        
        # ========== YÖNTEM 11: BİNA ORTALAMASIYLA KARŞILAŞTIRMA ==========
        bina_tesisatlari = df[df[bina_col] == bina_no]
        
        if len(bina_tesisatlari) > 2:
            bina_averages = []
            
            for _, other_row in bina_tesisatlari.iterrows():
                if other_row[tesisat_col] == tesisat_no:
                    continue
                
                other_total = 0
                other_count = 0
                
                for date_col in date_columns:
                    try:
                        val = other_row[date_col]
                        if pd.notna(val) and val > 0:
                            other_total += float(val)
                            other_count += 1
                    except:
                        continue
                
                if other_count > 0:
                    bina_averages.append(other_total / other_count)
            
            if len(bina_averages) > 0:
                bina_avg = np.mean(bina_averages)
                
                if avg_non_zero > 0 and bina_avg > params['normal_kis_esik']:
                    fark = ((bina_avg - avg_non_zero) / bina_avg) * 100
                    
                    if fark >= 60:
                        anomalies.append(f"🏢 BİNA: Bina ortalamasından %{fark:.0f} düşük (Bina: {bina_avg:.1f}, Bu: {avg_non_zero:.1f})")
                        leak_score += 25
                        detected_patterns.append("Bina Farkı")
        
        # ========== YÖNTEM 12: AGRESİF MOD - EK KONTROLER ==========
        if params['agresif_mod']:
            # Herhangi bir 12 aylık dönemde ortalama çok düşükse
            if total_months >= 12:
                for i in range(total_months - 11):
                    period_12 = cons_df.iloc[i:i+12]
                    period_avg = period_12['consumption'].mean()
                    
                    if period_avg < params['dusuk_tuketim_esik']:
                        start = period_12.iloc[0]['date_str']
                        end = period_12.iloc[-1]['date_str']
                        anomalies.append(f"🔍 AGRESİF: {start} - {end} arası düşük ({period_avg:.1f})")
                        leak_score += 10
                        detected_patterns.append("Agresif Tespit")
                        break  # Bir kez tespit yeterli
        
        # ===========================================
        # KAÇAK SEVİYESİ BELİRLEME
        # ===========================================
        
        if leak_score >= 50:
            leak_level = "🚨 Yüksek Riskli"
            suspicion = "Yüksek Riskli Kaçak"
        elif leak_score >= 30:
            leak_level = "⚠️ Orta Riskli"
            suspicion = "Orta Riskli Kaçak"
        elif leak_score >= 15:
            leak_level = "🔍 Düşük Riskli"
            suspicion = "Düşük Riskli"
        else:
            leak_level = "✅ Normal"
            suspicion = "Normal"
        
        # Trend belirleme
        if len(cons_df) >= 12:
            ilk_12 = cons_df.head(12)['consumption'].mean()
            son_12 = cons_df.tail(12)['consumption'].mean()
            
            if ilk_12 >= params['normal_kis_esik']:
                if son_12 == 0:
                    trend = "SIFIRA DÜŞTÜ"
                elif son_12 < ilk_12 * 0.2:
                    trend = "Kritik Düşüş (%80+)"
                elif son_12 < ilk_12 * 0.5:
                    trend = "Ciddi Düşüş (%50+)"
                elif son_12 < ilk_12 * 0.7:
                    trend = "Orta Düşüş"
                elif son_12 < ilk_12 * 0.9:
                    trend = "Hafif Düşüş"
                else:
                    trend = "Stabil"
            else:
                trend = "Düşük Başlangıç"
        else:
            trend = "Yetersiz Veri"
        
        # ===========================================
        # SONUÇLARI KAYDET
        # ===========================================
        
        results.append({
            'tesisat_no': tesisat_no,
            'bina_no': bina_no,
            'ortalama_tuketim': avg_consumption,
            'median_tuketim': median_consumption,
            'max_tuketim': max_consumption,
            'toplam_tuketim': total_consumption,
            'ay_sayisi': total_months,
            'sifir_ay': zero_count,
            'leak_score': leak_score,
            'leak_level': leak_level,
            'suspicion': suspicion,
            'trend': trend,
            'anomali_sayisi': len(anomalies),
            'tespit_yontemleri': ', '.join(set(detected_patterns)) if detected_patterns else 'Yok',
            'anomaliler': ' | '.join(anomalies) if anomalies else 'Anomali yok'
        })
    
    return pd.DataFrame(results)

def create_visualizations(results_df):
    """Görselleştirmeler"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Kaçak seviyesi dağılımı
        level_counts = results_df['leak_level'].value_counts()
        fig1 = px.pie(
            values=level_counts.values,
            names=level_counts.index,
            title="Kaçak Risk Seviyesi Dağılımı",
            color_discrete_sequence=['#00D9FF', '#FFD700', '#FF6B6B', '#C70039']
        )
        st.plotly_chart(fig1, use_container_width=True)
    
    with col2:
        # Tespit yöntemi dağılımı
        fig2 = px.histogram(
            results_df[results_df['suspicion'] != 'Normal'],
            x='anomali_sayisi',
            title="Tespit Edilen Anomali Sayısı (Kaçaklarda)",
            color='suspicion',
            color_discrete_map={
                'Düşük Riskli': '#FFE66D',
                'Orta Riskli Kaçak': '#FF6B6B',
                'Yüksek Riskli Kaçak': '#C70039'
            }
        )
        st.plotly_chart(fig2, use_container_width=True)
    
    # Kaçak skoru dağılımı
    fig3 = px.box(
        results_df,
        x='suspicion',
        y='leak_score',
        title="Kaçak Skoru Dağılımı",
        color='suspicion',
        color_discrete_map={
            'Normal': '#4ECDC4',
            'Düşük Riskli': '#FFE66D',
            'Orta Riskli Kaçak': '#FF6B6B',
            'Yüksek Riskli Kaçak': '#C70039'
        }
    )
    st.plotly_chart(fig3, use_container_width=True)
    
    # Ortalama vs Skor scatter
    fig4 = px.scatter(
        results_df,
        x='ortalama_tuketim',
        y='leak_score',
        color='suspicion',
        size='anomali_sayisi',
        title="Ortalama Tüketim vs Kaçak Skoru",
        hover_data=['tesisat_no', 'trend', 'tespit_yontemleri'],
        color_discrete_map={
            'Normal': '#4ECDC4',
            'Düşük Riskli': '#FFE66D',
            'Orta Riskli Kaçak': '#FF6B6B',
            'Yüksek Riskli Kaçak': '#C70039'
        }
    )
    st.plotly_chart(fig4, use_container_width=True)

# Ana uygulama
if uploaded_file is not None:
    df = load_data(uploaded_file)
    
    if df is not None:
        st.success("✅ Dosya başarıyla yüklendi!")
        
        st.subheader("📊 Veri Önizleme")
        st.dataframe(df.head())
        
        st.subheader("🔧 Sütun Seçimi")
        
        date_columns, other_columns = parse_date_columns(df)
        
        col1, col2 = st.columns(2)
        
        with col1:
            tesisat_col = st.selectbox("Tesisat Numarası Sütunu", options=other_columns)
        
        with col2:
            bina_col = st.selectbox("Bina Numarası Sütunu", options=other_columns)
        
        st.write(f"**Tespit edilen tarih sütunları:** {len(date_columns)} adet")
        if date_columns:
            st.write(f"Tarih aralığı: {date_columns[0]} - {date_columns[-1]}")
        
        if st.button("🔍 Kapsamlı Kaçak Analizi Başlat", type="primary"):
            with st.spinner("12 farklı yöntemle analiz yapılıyor..."):
                
                params = {
                    'normal_kis_esik': normal_kis_esik,
                    'dusuk_tuketim_esik': dusuk_tuketim_esik,
                    'min_dusus_orani': min_dusus_orani,
                    'agresif_mod': agresif_mod
                }
                
                results_df = detect_leak_comprehensive(df, date_columns, tesisat_col, bina_col, params)
                
                # Özet istatistikler
                st.subheader("📈 Analiz Sonuçları")
                
                col1, col2, col3, col4, col5 = st.columns(5)
                
                with col1:
                    st.metric("Toplam Tesisat", len(results_df))
                
                with col2:
                    high_risk = len(results_df[results_df['suspicion'] == 'Yüksek Riskli Kaçak'])
                    st.metric("Yüksek Risk", high_risk, delta=f"%{(high_risk/len(results_df)*100):.1f}")
                
                with col3:
                    medium_risk = len(results_df[results_df['suspicion'] == 'Orta Riskli Kaçak'])
                    st.metric("Orta Risk", medium_risk)
                
                with col4:
                    low_risk = len(results_df[results_df['suspicion'] == 'Düşük Riskli'])
                    st.metric("Düşük Risk", low_risk)
                
                with col5:
                    total_suspicious = high_risk + medium_risk + low_risk
                    st.metric("Toplam Şüpheli", total_suspicious)
                
                # Görselleştirmeler
                st.subheader("📊 Görselleştirmeler")
                create_visualizations(results_df)
                
                # Yüksek + Orta riskli tesisatlar
                st.subheader("🚨 Yüksek ve Orta Riskli Kaçak Şüpheleri")
                
                risk_df = results_df[
                    (results_df['suspicion'] == 'Yüksek Riskli Kaçak') | 
                    (results_df['suspicion'] == 'Orta Riskli Kaçak')
                ].copy()
                
                if not risk_df.empty:
                    risk_df = risk_df.sort_values('leak_score', ascending=False)
                    
                    display_cols = ['tesisat_no', 'bina_no', 'leak_score', 'leak_level',
                                   'ortalama_tuketim', 'trend', 'anomali_sayisi', 
                                   'tespit_yontemleri', 'anomaliler']
                    
                    display_df = risk_df[display_cols].copy()
                    display_df.columns = ['Tesisat No', 'Bina No', 'Kaçak Skoru', 'Risk Seviyesi',
                                         'Ortalama Tüketim', 'Trend', 'Anomali Sayısı',
                                         'Tespit Yöntemleri', 'Detaylar']
                    
                    for col in ['Kaçak Skoru', 'Ortalama Tüketim']:
                        display_df[col] = display_df[col].round(1)
                    
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                    # Excel indirme
                    import io
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                        display_df.to_excel(writer, index=False, sheet_name="Yüksek-Orta Risk")
                    output.seek(0)
                    
                    st.download_button(
                        label="📥 Yüksek ve Orta Riskli Tesisatları İndir (EXCEL)",
                        data=output,
                        file_name="yuksek_orta_riskli_kacaklar.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.success("🎉 Yüksek/Orta riskli kaçak tespit edilmedi!")
                
                # Tüm sonuçlar
                st.subheader("📋 Tüm Sonuçlar")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    risk_filter = st.selectbox(
                        "Risk Seviyesi Filtrele",
                        options=['Tümü'] + sorted(results_df['suspicion'].unique().tolist())
                    )
                
                with col2:
                    bina_filter = st.selectbox(
                        "Bina Numarası Filtrele",
                        options=['Tümü'] + sorted(results_df['bina_no'].unique().tolist())
                    )
                
                filtered_df = results_df.copy()
                
                if risk_filter != 'Tümü':
                    filtered_df = filtered_df[filtered_df['suspicion'] == risk_filter]
                
                if bina_filter != 'Tümü':
                    filtered_df = filtered_df[filtered_df['bina_no'] == bina_filter]
                
                if not filtered_df.empty:
                    display_cols = ['tesisat_no', 'bina_no', 'leak_level', 'leak_score',
                                   'ortalama_tuketim', 'trend', 'anomali_sayisi', 
                                   'tespit_yontemleri']
                    
                    all_display = filtered_df[display_cols].copy()
                    all_display.columns = ['Tesisat No', 'Bina No', 'Risk Seviyesi', 'Kaçak Skoru',
                                          'Ortalama', 'Trend', 'Anomali', 'Yöntemler']
                    
                    for col in ['Kaçak Skoru', 'Ortalama']:
                        all_display[col] = all_display[col].round(1)
                    
                    st.dataframe(all_display, use_container_width=True, hide_index=True)
                    
                    # Tümünü excel olarak indir
                    output2 = io.BytesIO()
                    with pd.ExcelWriter(output2, engine="xlsxwriter") as writer:
                        all_display.to_excel(writer, index=False, sheet_name="Tüm Sonuçlar")
                    output2.seek(0)
                    
                    st.download_button(
                        label="📥 Tüm Sonuçları İndir (EXCEL)",
                        data=output2,
                        file_name="tum_analiz_sonuclari.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("Filtreye uygun veri bulunamadı.")

else:
    st.info("👈 Lütfen sol panelden bir dosya yükleyin")
    
    st.subheader("📄 Beklenen Dosya Formatı")
    
    example_data = {
        'tesisat_no': ['T001', 'T002', 'T003'],
        'bina_no': ['B001', 'B001', 'B002'],
        '2018/1': [150, 145, 160],
        '2018/2': [140, 135, 150],
        '2022/11': [145, 140, 155],
        '2022/12': [155, 150, 165],
        '2023/1': [10, 5, 8],
        '2023/2': [8, 3, 6]
    }
    
    st.dataframe(pd.DataFrame(example_data), use_container_width=True)
    
    st.markdown("""
    **Dosya Formatı:**
    - **Tesisat No**: Benzersiz tesisat kimliği
    - **Bina No**: Bina numarası
    - **Tarih Sütunları**: YYYY/M formatında (2018/1, 2018/2, ...)
    - **Değerler**: Aylık doğalgaz tüketimi (m³)
    """)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎯 12 Tespit Yöntemi")
st.sidebar.markdown(f"""
**Temel Eşikler:**
- Normal kış: ≥ {normal_kis_esik} m³/ay
- Düşük tüketim: < {dusuk_tuketim_esik} m³/ay
- Minimum düşüş: %{min_dusus_orani}

**Tespit Yöntemleri:**
1. ⏱️ Zaman dilimleri (6 aylık)
2. 📅 Yıllık karşılaştırma
3. ❄️ Kış ayları analizi
4. 📊 Kayan pencere (3 aylık)
5. 📉 Sürekli düşük tüketim
6. ⛔ Sıfır aylar
7. 📈 Standart sapma analizi
8. 🌡️ Mevsimsel pattern
9. 💰 Toplam tüketim
10. 🔴 Son aylar analizi
11. 📉 Trend analizi
12. 🏢 Bina karşılaştırma

**Skorlama:**
- 50+ puan: 🚨 Yüksek Risk
- 30-49: ⚠️ Orta Risk
- 15-29: 🔍 Düşük Risk
- 0-14: ✅ Normal
""")
