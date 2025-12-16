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

st.title("🔥 Doğalgaz Kaçak Tespit Sistemi")
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
    min_value=50, max_value=200, value=80,
    help="Bu değerin üzerindeki kış tüketimi 'normal' kabul edilir"
)

dusuk_tuketim_esik = st.sidebar.slider(
    "Düşük tüketim eşiği (m³/ay)",
    min_value=5, max_value=50, value=20,
    help="Bu değerin altındaki tüketim 'kaçak şüphesi' kabul edilir"
)

ani_dusus_orani = st.sidebar.slider(
    "Kritik düşüş oranı (%)",
    min_value=50, max_value=95, value=80,
    help="Normal tüketime göre bu oranda düşüş kaçak şüphesi oluşturur"
)

min_normal_ay = st.sidebar.slider(
    "Minimum normal tüketim ayı",
    min_value=3, max_value=12, value=6,
    help="Kaçak tespiti için en az kaç ay normal tüketim olmalı"
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
                year, month = col.split('/')
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

def analyze_leak_patterns(df, date_columns, tesisat_col, bina_col):
    """GELİŞTİRİLMİŞ KAÇAK TESPİT ANALİZİ"""
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
                        'date_str': date_col
                    })
            except:
                continue
        
        if len(monthly_data) < 6:
            continue
        
        cons_df = pd.DataFrame(monthly_data)
        cons_df = cons_df.sort_values(['year', 'month'])
        
        # ===========================================
        # KAÇAK TESPİT MANTIKLARI
        # ===========================================
        
        anomalies = []
        leak_score = 0  # Kaçak puanı (0-100)
        
        # 1. ZAMAN SERİSİ ANALİZİ - Normal dönem ve düşük dönem tespiti
        cons_df['is_normal'] = cons_df['consumption'] >= normal_kis_esik
        cons_df['is_low'] = cons_df['consumption'] < dusuk_tuketim_esik
        cons_df['is_zero'] = cons_df['consumption'] == 0
        
        normal_months = cons_df[cons_df['is_normal']]
        low_months = cons_df[cons_df['is_low']]
        zero_months = cons_df[cons_df['is_zero']]
        
        # 2. DÖNEMSEL ANALİZ - İlk dönem vs Son dönem
        total_months = len(cons_df)
        first_half = cons_df.iloc[:total_months//2]
        second_half = cons_df.iloc[total_months//2:]
        
        first_half_avg = first_half['consumption'].mean()
        second_half_avg = second_half['consumption'].mean()
        
        # 3. KIŞ AYLARINDA ANALİZ
        kis_aylari = cons_df[cons_df['season'] == 'Kış'].copy()
        
        if len(kis_aylari) > 0:
            # Kış aylarını yıllara göre grupla (Aralık + Ocak + Şubat = bir kış)
            kis_aylari['kis_sezonu'] = kis_aylari.apply(
                lambda x: f"{x['year']-1}/{x['year']}" if x['month'] in [1, 2] 
                else f"{x['year']}/{x['year']+1}",
                axis=1
            )
            
            kis_sezon_avg = kis_aylari.groupby('kis_sezonu')['consumption'].mean()
            kis_sezonlari = sorted(kis_sezon_avg.index)
            
            if len(kis_sezonlari) >= 2:
                ilk_kis_sezonlari = kis_sezon_avg[kis_sezonlari[:len(kis_sezonlari)//2]]
                son_kis_sezonlari = kis_sezon_avg[kis_sezonlari[len(kis_sezonlari)//2:]]
                
                ilk_kis_ort = ilk_kis_sezonlari.mean()
                son_kis_ort = son_kis_sezonlari.mean()
        
        # ===========================================
        # KAÇAK SKORLAMA VE ANOMALİ TESPİTİ
        # ===========================================
        
        # SENARYO 1: Normal dönem var + Sonra ani düşüş
        if len(normal_months) >= min_normal_ay:
            normal_avg = normal_months['consumption'].mean()
            
            # Son aylar düşük mü?
            son_6_ay = cons_df.tail(6)
            son_6_ay_avg = son_6_ay['consumption'].mean()
            
            if son_6_ay_avg < normal_avg * (1 - ani_dusus_orani/100):
                dusus_orani = ((normal_avg - son_6_ay_avg) / normal_avg) * 100
                
                if son_6_ay_avg == 0:
                    anomalies.append(f"🚨 KRİTİK KAÇAK: Tüketim SIFIRA düştü (Normal: {normal_avg:.1f} → Son: 0)")
                    leak_score += 50
                elif son_6_ay_avg < 10:
                    anomalies.append(f"🚨 KRİTİK KAÇAK: Neredeyse sıfır tüketim (Normal: {normal_avg:.1f} → Son: {son_6_ay_avg:.1f})")
                    leak_score += 45
                else:
                    anomalies.append(f"⚠️ ŞÜPHELİ DÜŞÜŞ: %{dusus_orani:.0f} düşüş (Normal: {normal_avg:.1f} → Son: {son_6_ay_avg:.1f})")
                    leak_score += 30
        
        # SENARYO 2: Kış sezonları arasında dramatik düşüş
        if len(kis_aylari) > 0 and len(kis_sezonlari) >= 2:
            if ilk_kis_ort >= normal_kis_esik and son_kis_ort < dusuk_tuketim_esik:
                dusus = ((ilk_kis_ort - son_kis_ort) / ilk_kis_ort) * 100
                
                ilk_sezon_str = ', '.join(kis_sezonlari[:len(kis_sezonlari)//2])
                son_sezon_str = ', '.join(kis_sezonlari[len(kis_sezonlari)//2:])
                
                if son_kis_ort == 0:
                    anomalies.append(f"🚨 KIŞ KAÇAĞI: {ilk_sezon_str} ({ilk_kis_ort:.1f}) → {son_sezon_str} (0)")
                    leak_score += 40
                else:
                    anomalies.append(f"⚠️ KIŞ DÜŞÜŞÜ: {ilk_sezon_str} ({ilk_kis_ort:.1f}) → {son_sezon_str} ({son_kis_ort:.1f}), %{dusus:.0f} düşüş")
                    leak_score += 25
        
        # SENARYO 3: İlk yarı vs İkinci yarı karşılaştırması
        if first_half_avg >= normal_kis_esik and second_half_avg < dusuk_tuketim_esik:
            dusus = ((first_half_avg - second_half_avg) / first_half_avg) * 100
            anomalies.append(f"📉 DÖNEMSEL DÜŞÜŞ: İlk dönem {first_half_avg:.1f} → Son dönem {second_half_avg:.1f} (%{dusus:.0f})")
            leak_score += 20
        
        # SENARYO 4: Sürekli sıfır veya çok düşük tüketim
        if len(zero_months) >= 6:
            anomalies.append(f"⛔ SÜREKLİ SIFIR: {len(zero_months)} ay sıfır tüketim")
            leak_score += 35
        elif len(low_months) >= 8:
            anomalies.append(f"📊 SÜREKLİ DÜŞÜK: {len(low_months)} ay düşük tüketim (<{dusuk_tuketim_esik})")
            leak_score += 15
        
        # SENARYO 5: Kış-Yaz farkı yok (doğal olmayan)
        kis_avg = cons_df[cons_df['season'] == 'Kış']['consumption'].mean()
        yaz_avg = cons_df[cons_df['season'] == 'Yaz']['consumption'].mean()
        
        if kis_avg > 0 and yaz_avg > 0:
            if abs(kis_avg - yaz_avg) < 15 and kis_avg < dusuk_tuketim_esik:
                anomalies.append(f"🔍 DOĞAL OLMAYAN: Kış-yaz farkı yok (Kış: {kis_avg:.1f}, Yaz: {yaz_avg:.1f})")
                leak_score += 10
        
        # ===========================================
        # KAÇAK SEVİYESİ BELİRLEME
        # ===========================================
        
        if leak_score >= 40:
            leak_level = "🚨 YÜksek Riskli"
            suspicion = "Yüksek Riskli Kaçak"
        elif leak_score >= 20:
            leak_level = "⚠️ Orta Riskli"
            suspicion = "Orta Riskli Kaçak"
        elif leak_score > 0:
            leak_level = "🔍 Düşük Riskli"
            suspicion = "Düşük Riskli"
        else:
            leak_level = "✅ Normal"
            suspicion = "Normal"
        
        # Trend analizi
        if len(cons_df) >= 12:
            ilk_12 = cons_df.head(12)['consumption'].mean()
            son_12 = cons_df.tail(12)['consumption'].mean()
            
            if ilk_12 >= normal_kis_esik:
                if son_12 == 0:
                    trend = "SIFIRA DÜŞTÜ"
                elif son_12 < ilk_12 * 0.2:
                    trend = "Kritik Düşüş (%80+)"
                elif son_12 < ilk_12 * 0.5:
                    trend = "Ciddi Düşüş"
                elif son_12 < ilk_12 * 0.8:
                    trend = "Azalış Trendi"
                else:
                    trend = "Stabil"
            else:
                trend = "Düşük Başlangıç"
        else:
            trend = "Yetersiz Veri"
        
        # Sonuçları kaydet
        results.append({
            'tesisat_no': tesisat_no,
            'bina_no': bina_no,
            'ortalama_tuketim': cons_df['consumption'].mean(),
            'kis_tuketim': kis_avg if kis_avg > 0 else 0,
            'yaz_tuketim': yaz_avg if yaz_avg > 0 else 0,
            'ilk_donem_ort': first_half_avg,
            'son_donem_ort': second_half_avg,
            'normal_ay_sayisi': len(normal_months),
            'dusuk_ay_sayisi': len(low_months),
            'sifir_ay_sayisi': len(zero_months),
            'leak_score': leak_score,
            'leak_level': leak_level,
            'suspicion': suspicion,
            'trend': trend,
            'anomali_sayisi': len(anomalies),
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
        # Anomali sayısı dağılımı
        fig2 = px.histogram(
            results_df,
            x='anomali_sayisi',
            title="Anomali Sayısı Dağılımı",
            color='suspicion',
            color_discrete_map={
                'Normal': '#4ECDC4',
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
        title="Kaçak Skoru Dağılımı (Risk Seviyesine Göre)",
        color='suspicion',
        color_discrete_map={
            'Normal': '#4ECDC4',
            'Düşük Riskli': '#FFE66D',
            'Orta Riskli Kaçak': '#FF6B6B',
            'Yüksek Riskli Kaçak': '#C70039'
        }
    )
    st.plotly_chart(fig3, use_container_width=True)
    
    # İlk dönem vs Son dönem karşılaştırması
    fig4 = px.scatter(
        results_df,
        x='ilk_donem_ort',
        y='son_donem_ort',
        color='suspicion',
        size='leak_score',
        title="İlk Dönem vs Son Dönem Tüketim Karşılaştırması",
        labels={'ilk_donem_ort': 'İlk Dönem Ortalama', 'son_donem_ort': 'Son Dönem Ortalama'},
        color_discrete_map={
            'Normal': '#4ECDC4',
            'Düşük Riskli': '#FFE66D',
            'Orta Riskli Kaçak': '#FF6B6B',
            'Yüksek Riskli Kaçak': '#C70039'
        },
        hover_data=['tesisat_no', 'leak_score', 'trend']
    )
    
    # Eşitlik çizgisi
    max_val = max(results_df['ilk_donem_ort'].max(), results_df['son_donem_ort'].max())
    fig4.add_trace(go.Scatter(
        x=[0, max_val],
        y=[0, max_val],
        mode='lines',
        name='Eşitlik Çizgisi',
        line=dict(dash='dash', color='gray')
    ))
    
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
        
        if st.button("🔍 Kaçak Analizi Başlat", type="primary"):
            with st.spinner("Analiz yapılıyor..."):
                results_df = analyze_leak_patterns(df, date_columns, tesisat_col, bina_col)
                
                # Özet istatistikler
                st.subheader("📈 Analiz Sonuçları")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Toplam Tesisat", len(results_df))
                
                with col2:
                    high_risk = len(results_df[results_df['suspicion'] == 'Yüksek Riskli Kaçak'])
                    st.metric("Yüksek Riskli", high_risk, delta=f"%{(high_risk/len(results_df)*100):.1f}")
                
                with col3:
                    medium_risk = len(results_df[results_df['suspicion'] == 'Orta Riskli Kaçak'])
                    st.metric("Orta Riskli", medium_risk)
                
                with col4:
                    total_anomalies = results_df['anomali_sayisi'].sum()
                    st.metric("Toplam Anomali", total_anomalies)
                
                # Görselleştirmeler
                st.subheader("📊 Görselleştirmeler")
                create_visualizations(results_df)
                
                # Yüksek riskli tesisatlar
                st.subheader("🚨 Yüksek Riskli Kaçak Şüpheleri")
                high_risk_df = results_df[results_df['suspicion'] == 'Yüksek Riskli Kaçak'].copy()
                
                if not high_risk_df.empty:
                    high_risk_df = high_risk_df.sort_values('leak_score', ascending=False)
                    
                    display_cols = ['tesisat_no', 'bina_no', 'leak_score', 'ilk_donem_ort', 
                                   'son_donem_ort', 'trend', 'anomali_sayisi', 'anomaliler']
                    
                    display_df = high_risk_df[display_cols].copy()
                    display_df.columns = ['Tesisat No', 'Bina No', 'Kaçak Skoru', 
                                         'İlk Dönem Ort.', 'Son Dönem Ort.', 'Trend',
                                         'Anomali Sayısı', 'Tespit Edilen Anomaliler']
                    
                    for col in ['Kaçak Skoru', 'İlk Dönem Ort.', 'Son Dönem Ort.']:
                        display_df[col] = display_df[col].round(1)
                    
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                    # Excel indirme
                    import io
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                        display_df.to_excel(writer, index=False, sheet_name="Yüksek Riskli")
                    output.seek(0)
                    
                    st.download_button(
                        label="📥 Yüksek Riskli Tesisatları İndir (EXCEL)",
                        data=output,
                        file_name="yuksek_riskli_kacaklar.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.success("🎉 Yüksek riskli kaçak tespit edilmedi!")
                
                # Tüm sonuçlar
                st.subheader("📋 Tüm Sonuçlar")
                
                risk_filter = st.selectbox(
                    "Risk Seviyesi Filtrele",
                    options=['Tümü'] + results_df['suspicion'].unique().tolist()
                )
                
                filtered_df = results_df.copy()
                if risk_filter != 'Tümü':
                    filtered_df = filtered_df[filtered_df['suspicion'] == risk_filter]
                
                if not filtered_df.empty:
                    display_cols = ['tesisat_no', 'bina_no', 'leak_level', 'leak_score',
                                   'trend', 'anomali_sayisi', 'anomaliler']
                    
                    all_display = filtered_df[display_cols].copy()
                    all_display.columns = ['Tesisat No', 'Bina No', 'Risk Seviyesi', 'Kaçak Skoru',
                                          'Trend', 'Anomali Sayısı', 'Anomaliler']
                    
                    all_display['Kaçak Skoru'] = all_display['Kaçak Skoru'].round(1)
                    
                    st.dataframe(all_display, use_container_width=True, hide_index=True)

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

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎯 Kaçak Tespit Yöntemi")
st.sidebar.markdown(f"""
**Analiz Kriterleri:**
- Normal kış: ≥ {normal_kis_esik} m³/ay
- Düşük tüketim: < {dusuk_tuketim_esik} m³/ay
- Kritik düşüş: %{ani_dusus_orani}+ düşüş

**Tespit Senaryoları:**
1. ✅ Normal dönem + Ani düşüş
2. ❄️ Kış sezonları arası düşüş
3. 📊 Dönemsel analiz
4. ⛔ Sürekli sıfır/düşük
5. 🔍 Kış-yaz farkı analizi

**Skorlama:**
- 40+ puan: Yüksek Risk
- 20-39: Orta Risk
- 1-19: Düşük Risk
- 0: Normal
""")
