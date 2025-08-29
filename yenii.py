import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io

# Sayfa yapılandırması
st.set_page_config(
    page_title="🔥 Doğalgaz Tüketim Anomali Tespiti",
    page_icon="🔥",
    layout="wide"
)

# Ana başlık
st.title("🔥 Doğalgaz Tüketim Anomali Tespit Sistemi")
st.markdown("---")

# Dosya yükleme bölümü
st.header("📂 Excel Dosyası Yükle")
uploaded_file = st.file_uploader(
    "Doğalgaz tüketim verilerini içeren Excel dosyasını yükleyin",
    type=['xlsx', 'xls'],
    help="Excel dosyası: Belge tarihi, Tüketim noktası, Bağlantı nesnesi, Tüketim miktarı, KWH Tüketim sütunlarını içermelidir"
)

if uploaded_file is not None:
    try:
        # Excel dosyasını okuma
        df = pd.read_excel(uploaded_file)
        
        # Sütun adlarını standartlaştırma
        column_mapping = {
            'Belge tarihi': 'tarih',
            'Tüketim noktası': 'tuketim_noktasi', 
            'Bağlantı nesnesi': 'baglanti_nesnesi',
            'Tüketim miktarı': 'tuketim_miktari',
            'KWH Tüketim': 'kwh_tuketim'
        }
        
        # Sütun adlarını eşleştirme
        df.columns = df.columns.str.strip()
        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                df = df.rename(columns={old_name: new_name})
        
        # Tarih sütununu datetime'a çevirme
        if 'tarih' in df.columns:
            df['tarih'] = pd.to_datetime(df['tarih'])
            df['yil'] = df['tarih'].dt.year
            df['ay'] = df['tarih'].dt.month
            df['ay_ad'] = df['tarih'].dt.strftime('%B')
        
        st.success(f"✅ Dosya başarıyla yüklendi! {len(df)} satır veri okundu.")
        
        # Veri önizlemesi
        with st.expander("📊 Veri Önizlemesi"):
            st.dataframe(df.head(10))
            
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Toplam Kayıt", len(df))
        with col2:
            st.metric("Tesisat Sayısı", df['tuketim_noktasi'].nunique())
        with col3:
            st.metric("Bina Sayısı", df['baglanti_nesnesi'].nunique())
            
    except Exception as e:
        st.error(f"❌ Dosya okuma hatası: {str(e)}")
        st.stop()
        
    # Parametreler bölümü
    st.sidebar.header("⚙️ Analiz Parametreleri")
    kis_tuketim_esigi = st.sidebar.slider(
        "Kış ayı düşük tüketim eşiği (m³/ay)",
        min_value=10, max_value=100, value=30,
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
        min_value=50, max_value=200, value=100,
        help="Ani düşüş tespiti için önceki kış aylarında minimum tüketim"
    )
    
    # Analiz başlatma butonu
    if st.sidebar.button("🔍 Anomali Analizi Başlat", type="primary"):
        
        # Kış ayları tanımı (Kasım, Aralık, Ocak, Şubat)
        kis_aylari = [11, 12, 1, 2]
        
        # Anomali tespit fonksiyonları
        def kis_dusukluk_anomalisi(df, esik):
            """Kış aylarında düşük tüketim anomalisi"""
            kis_verileri = df[df['ay'].isin(kis_aylari)]
            anomaliler = kis_verileri[kis_verileri['tuketim_miktari'] < esik].copy()
            anomaliler['anomali_tipi'] = 'Kış Ayı Düşük Tüketim'
            anomaliler['aciklama'] = f'{esik} m³/ay altında kış tüketimi'
            return anomaliler
            
        def bina_ortalamasindan_dusuk_anomali(df, oran):
            """Bina ortalamasından düşük tüketim anomalisi"""
            # Her bina için ortalama tüketim hesaplama
            bina_ortalamalari = df.groupby('baglanti_nesnesi')['tuketim_miktari'].mean().reset_index()
            bina_ortalamalari.columns = ['baglanti_nesnesi', 'bina_ortalama']
            
            # Veriyi bina ortalamaları ile birleştirme
            df_with_avg = df.merge(bina_ortalamalari, on='baglanti_nesnesi')
            
            # Anomali tespiti
            esik_deger = df_with_avg['bina_ortalama'] * (oran / 100)
            anomaliler = df_with_avg[df_with_avg['tuketim_miktari'] < esik_deger].copy()
            anomaliler['anomali_tipi'] = 'Bina Ortalamasından Düşük'
            anomaliler['aciklama'] = f'Bina ortalamasından %{100-oran} daha düşük'
            return anomaliler
            
        def ani_dusus_anomalisi(df, oran, min_tuketim):
            """Ani düşüş anomalisi"""
            anomaliler = []
            
            for tesisat in df['tuketim_noktasi'].unique():
                tesisat_data = df[df['tuketim_noktasi'] == tesisat].sort_values('tarih')
                
                for yil in tesisat_data['yil'].unique():
                    if yil == tesisat_data['yil'].min():
                        continue  # İlk yıl için karşılaştırma yapılamaz
                        
                    mevcut_kis = tesisat_data[
                        (tesisat_data['yil'] == yil) & 
                        (tesisat_data['ay'].isin(kis_aylari))
                    ]['tuketim_miktari'].mean()
                    
                    onceki_kis = tesisat_data[
                        (tesisat_data['yil'] == yil-1) & 
                        (tesisat_data['ay'].isin(kis_aylari))
                    ]['tuketim_miktari'].mean()
                    
                    if (onceki_kis >= min_tuketim and 
                        not pd.isna(mevcut_kis) and 
                        not pd.isna(onceki_kis) and
                        mevcut_kis < onceki_kis * ((100-oran)/100)):
                        
                        # Anomali kayıtlarını ekleme
                        kis_kayitlari = tesisat_data[
                            (tesisat_data['yil'] == yil) & 
                            (tesisat_data['ay'].isin(kis_aylari))
                        ].copy()
                        
                        kis_kayitlari['anomali_tipi'] = 'Ani Düşüş'
                        kis_kayitlari['aciklama'] = f'%{oran} ani düşüş (Önceki: {onceki_kis:.1f}, Mevcut: {mevcut_kis:.1f})'
                        anomaliler.append(kis_kayitlari)
                        
            return pd.concat(anomaliler) if anomaliler else pd.DataFrame()
        
        # Progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Anomali analizleri
        status_text.text("🔍 Kış ayı düşük tüketim anomalileri tespit ediliyor...")
        progress_bar.progress(25)
        anomali_1 = kis_dusukluk_anomalisi(df, kis_tuketim_esigi)
        
        status_text.text("🔍 Bina ortalamasından düşük tüketim anomalileri tespit ediliyor...")
        progress_bar.progress(50)
        anomali_2 = bina_ortalamasindan_dusuk_anomali(df, bina_ort_dusuk_oran)
        
        status_text.text("🔍 Ani düşüş anomalileri tespit ediliyor...")
        progress_bar.progress(75)
        anomali_3 = ani_dusus_anomalisi(df, ani_dusus_orani, min_onceki_kis_tuketim)
        
        status_text.text("✅ Anomali analizi tamamlandı!")
        progress_bar.progress(100)
        
        # Tüm anomalileri birleştirme
        tum_anomaliler = []
        if not anomali_1.empty:
            tum_anomaliler.append(anomali_1)
        if not anomali_2.empty:
            tum_anomaliler.append(anomali_2)
        if not anomali_3.empty:
            tum_anomaliler.append(anomali_3)
            
        if tum_anomaliler:
            anomali_df = pd.concat(tum_anomaliler, ignore_index=True)
            
            # Sonuçları görüntüleme
            st.header("🚨 Tespit Edilen Anomaliler")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Toplam Anomali", len(anomali_df))
            with col2:
                st.metric("Anomalili Tesisat", anomali_df['tuketim_noktasi'].nunique())
            with col3:
                st.metric("Anomali Türü", anomali_df['anomali_tipi'].nunique())
                
            # Anomali türleri dağılımı
            fig = px.pie(
                anomali_df.groupby('anomali_tipi').size().reset_index(name='count'),
                values='count', names='anomali_tipi',
                title="Anomali Türleri Dağılımı"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Anomalili tesisatların listesi
            with st.expander("📋 Anomalili Tesisatlar Detayı"):
                st.dataframe(anomali_df.sort_values('tarih'))
                
            # Excel indirme
            def convert_df_to_excel(df):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='Anomaliler', index=False)
                    
                    # Özet sayfa ekleme
                    ozet = pd.DataFrame({
                        'Anomali Türü': anomali_df['anomali_tipi'].value_counts().index,
                        'Adet': anomali_df['anomali_tipi'].value_counts().values
                    })
                    ozet.to_excel(writer, sheet_name='Özet', index=False)
                    
                processed_data = output.getvalue()
                return processed_data
                
            excel_data = convert_df_to_excel(anomali_df)
            
            st.download_button(
                label="📥 Anomali Raporunu Excel Olarak İndir",
                data=excel_data,
                file_name=f"dogalgaz_anomaliler_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
            
        else:
            st.success("🎉 Belirlenen parametrelere göre herhangi bir anomali tespit edilmedi!")
            
        # Progress bar'ı temizleme
        progress_bar.empty()
        status_text.empty()
        
else:
    st.info("👆 Lütfen analiz için Excel dosyanızı yükleyin.")
    
    # Örnek veri formatı gösterimi
    st.header("📋 Beklenen Excel Dosya Formatı")
    
    ornek_data = {
        'Belge tarihi': ['01.05.2023', '01.06.2023', '01.07.2023'],
        'Tüketim noktası': ['10843655', '10843655', '10843655'],
        'Bağlantı nesnesi': ['100000612', '100000612', '100000612'],
        'Tüketim miktarı': [285, 15, 8],
        'KWH Tüketim': [2873.207, 156.45, 83.44]
    }
    
    ornek_df = pd.DataFrame(ornek_data)
    st.dataframe(ornek_df)
    
    st.markdown("""
    **Gerekli Sütunlar:**
    - **Belge tarihi**: Tüketim tarihi
    - **Tüketim noktası**: Tesisat numarası  
    - **Bağlantı nesnesi**: Bina numarası
    - **Tüketim miktarı**: Aylık doğalgaz tüketimi (m³)
    - **KWH Tüketim**: KWH cinsinden tüketim
    """)
