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
    help="Excel dosyası: TN (Tesisat No), BN (Bina No), tarih sütunları (MM/YYYY formatında) içermelidir"
)

if uploaded_file is not None:
    try:
        # Excel dosyasını okuma
        df = pd.read_excel(uploaded_file)
        
        # Sütun adlarını temizleme
        df.columns = df.columns.astype(str).str.strip()
        
        # TN ve BN sütunlarını bulma
        tn_col = None
        bn_col = None
        
        for col in df.columns:
            col_lower = col.lower().strip()
            if 'tn' in col_lower or 'tesisat' in col_lower:
                tn_col = col
            elif 'bn' in col_lower or 'bina' in col_lower:
                bn_col = col
        
        if not tn_col or not bn_col:
            st.error("❌ TN (Tesisat Numarası) ve BN (Bina Numarası) sütunları bulunamadı!")
            st.info("Mevcut sütunlar:")
            st.write(list(df.columns))
            st.stop()
            
        # Tarih sütunlarını bulma (MM/YYYY formatında)
        tarih_sutunlari = []
        for col in df.columns:
            if col not in [tn_col, bn_col]:
                # MM/YYYY formatında tarih olup olmadığını kontrol et
                if '/' in str(col) and len(str(col).split('/')) == 2:
                    try:
                        ay, yil = str(col).split('/')
                        if 1 <= int(ay) <= 12 and 2018 <= int(yil) <= 2025:
                            tarih_sutunlari.append(col)
                    except:
                        continue
        
        if not tarih_sutunlari:
            st.error("❌ MM/YYYY formatında tarih sütunları bulunamadı!")
            st.info("Örnek tarih formatı: 01/2023, 12/2024")
            st.stop()
        
        # Veriyi yeniden düzenleme (melting)
        id_vars = [tn_col, bn_col]
        df_melted = df.melt(
            id_vars=id_vars,
            value_vars=tarih_sutunlari,
            var_name='tarih_str',
            value_name='tuketim_miktari'
        )
        
        # Tarih bilgilerini ayıklama
        df_melted['ay'] = df_melted['tarih_str'].str.split('/').str[0].astype(int)
        df_melted['yil'] = df_melted['tarih_str'].str.split('/').str[1].astype(int)
        df_melted['tarih'] = pd.to_datetime(df_melted[['yil', 'ay']].assign(day=1))
        
        # Tüketim değerlerini temizleme
        df_melted['tuketim_miktari'] = pd.to_numeric(df_melted['tuketim_miktari'], errors='coerce')
        df_melted = df_melted.dropna(subset=['tuketim_miktari'])
        
        # Sıfır ve negatif değerleri kaldırma
        df_melted = df_melted[df_melted['tuketim_miktari'] > 0]
        
        # Sütun adlarını standartlaştırma
        df_melted = df_melted.rename(columns={
            tn_col: 'tuketim_noktasi',
            bn_col: 'baglanti_nesnesi'
        })
        
        st.success(f"✅ Dosya başarıyla işlendi! {len(df_melted)} kayıt oluşturuldu.")
        
        # Veri önizlemesi
        with st.expander("📊 İşlenmiş Veri Önizlemesi"):
            st.dataframe(df_melted.head(10))
            
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Toplam Kayıt", len(df_melted))
        with col2:
            st.metric("Tesisat Sayısı", df_melted['tuketim_noktasi'].nunique())
        with col3:
            st.metric("Bina Sayısı", df_melted['baglanti_nesnesi'].nunique())
        with col4:
            st.metric("Tarih Aralığı", f"{len(tarih_sutunlari)} ay")
            
    except Exception as e:
        st.error(f"❌ Dosya okuma hatası: {str(e)}")
        st.stop()
        
    # Parametreler bölümü
    st.sidebar.header("⚙️ Analiz Parametreleri")
    kis_tuketim_esigi = st.sidebar.slider(
        "Kış ayı düşük tüketim eşiği (sm³/ay)",
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
        "Minimum önceki kış tüketimi (sm³)",
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
            kis_verileri = df[df['ay'].isin(kis_aylari)].copy()
            if kis_verileri.empty:
                return pd.DataFrame()
                
            anomaliler = kis_verileri[kis_verileri['tuketim_miktari'] < esik].copy()
            if not anomaliler.empty:
                anomaliler['anomali_tipi'] = 'Kış Ayı Düşük Tüketim'
                anomaliler['aciklama'] = f'{esik} sm³/ay altında kış tüketimi'
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
            
            if not anomaliler.empty:
                anomaliler['anomali_tipi'] = 'Bina Ortalamasından Düşük'
                anomaliler['aciklama'] = f'Bina ortalamasından %{100-oran} daha düşük'
            return anomaliler
            
        def ani_dusus_anomalisi(df, oran, min_tuketim):
            """Ani düşüş anomalisi"""
            anomaliler = []
            
            for tesisat in df['tuketim_noktasi'].unique():
                tesisat_data = df[df['tuketim_noktasi'] == tesisat].sort_values('tarih')
                
                # Kış ayları için yıllık ortalamalar
                kis_ortalamalari = tesisat_data[
                    tesisat_data['ay'].isin(kis_aylari)
                ].groupby('yil')['tuketim_miktari'].mean()
                
                for yil in kis_ortalamalari.index:
                    if yil == kis_ortalamalari.index.min():
                        continue  # İlk yıl için karşılaştırma yapılamaz
                        
                    mevcut_kis = kis_ortalamalari[yil]
                    onceki_kis = kis_ortalamalari.get(yil-1, np.nan)
                    
                    if (onceki_kis >= min_tuketim and 
                        not pd.isna(mevcut_kis) and 
                        not pd.isna(onceki_kis) and
                        mevcut_kis < onceki_kis * ((100-oran)/100)):
                        
                        # Anomali kayıtlarını ekleme
                        kis_kayitlari = tesisat_data[
                            (tesisat_data['yil'] == yil) & 
                            (tesisat_data['ay'].isin(kis_aylari))
                        ].copy()
                        
                        if not kis_kayitlari.empty:
                            kis_kayitlari['anomali_tipi'] = 'Ani Düşüş'
                            kis_kayitlari['aciklama'] = f'%{oran} ani düşüş (Önceki: {onceki_kis:.1f}, Mevcut: {mevcut_kis:.1f})'
                            anomaliler.append(kis_kayitlari)
                        
            return pd.concat(anomaliler, ignore_index=True) if anomaliler else pd.DataFrame()
        
        # Progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Anomali analizleri
        status_text.text("🔍 Kış ayı düşük tüketim anomalileri tespit ediliyor...")
        progress_bar.progress(25)
        anomali_1 = kis_dusukluk_anomalisi(df_melted, kis_tuketim_esigi)
        
        status_text.text("🔍 Bina ortalamasından düşük tüketim anomalileri tespit ediliyor...")
        progress_bar.progress(50)
        anomali_2 = bina_ortalamasindan_dusuk_anomali(df_melted, bina_ort_dusuk_oran)
        
        status_text.text("🔍 Ani düşüş anomalileri tespit ediliyor...")
        progress_bar.progress(75)
        anomali_3 = ani_dusus_anomalisi(df_melted, ani_dusus_orani, min_onceki_kis_tuketim)
        
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
            
            # Duplike kayıtları kaldırma
            anomali_df = anomali_df.drop_duplicates(
                subset=['tuketim_noktasi', 'tarih_str'], 
                keep='first'
            )
            
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
            
            # Aylık anomali dağılımı
            fig2 = px.bar(
                anomali_df.groupby(['yil', 'ay']).size().reset_index(name='count'),
                x='ay', y='count', color='yil',
                title="Aylık Anomali Dağılımı"
            )
            st.plotly_chart(fig2, use_container_width=True)
            
            # Anomalili tesisatların listesi
            with st.expander("📋 Anomalili Tesisatlar Detayı"):
                # Özet tablo
                anomali_ozet = anomali_df.groupby(['tuketim_noktasi', 'baglanti_nesnesi', 'anomali_tipi']).agg({
                    'tuketim_miktari': ['count', 'mean', 'min', 'max'],
                    'tarih_str': 'first'
                }).round(2)
                
                anomali_ozet.columns = ['Anomali_Sayısı', 'Ortalama_Tüketim', 'Min_Tüketim', 'Max_Tüketim', 'İlk_Tarih']
                st.dataframe(anomali_ozet.reset_index())
                
            # Excel indirme
            def convert_df_to_excel(df):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # Ana anomali verileri
                    df_export = df.copy()
                    df_export['tarih_formatted'] = df_export['tarih'].dt.strftime('%m/%Y')
                    df_export.to_excel(writer, sheet_name='Anomaliler', index=False)
                    
                    # Özet tablo
                    ozet = pd.DataFrame({
                        'Anomali_Türü': anomali_df['anomali_tipi'].value_counts().index,
                        'Adet': anomali_df['anomali_tipi'].value_counts().values
                    })
                    ozet.to_excel(writer, sheet_name='Özet', index=False)
                    
                    # Tesisat bazlı özet
                    tesisat_ozet = anomali_df.groupby(['tuketim_noktasi', 'baglanti_nesnesi']).agg({
                        'anomali_tipi': lambda x: ', '.join(x.unique()),
                        'tuketim_miktari': ['count', 'mean'],
                        'tarih_str': lambda x: ', '.join(x.unique())
                    }).round(2)
                    tesisat_ozet.columns = ['Anomali_Türleri', 'Anomali_Sayısı', 'Ortalama_Tüketim', 'Tarihler']
                    tesisat_ozet.to_excel(writer, sheet_name='Tesisat_Özeti')
                    
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
        'TN': ['10843655', '10843656', '10843657'],
        'BN': ['100000612', '100000612', '100000613'],
        '01/2023': [285, 190, 220],
        '02/2023': [275, 180, 210],
        '03/2023': [150, 120, 140],
        '01/2024': [290, 195, 225],
        '02/2024': [15, 185, 215]  # Anomali örneği
    }
    
    ornek_df = pd.DataFrame(ornek_data)
    st.dataframe(ornek_df)
    
    st.markdown("""
    **Gerekli Format:**
    - **TN**: Tesisat Numarası (her satır bir tesisat)
    - **BN**: Bina Numarası  
    - **MM/YYYY**: Her sütun bir aylık tüketim (sm³ - standart metreküp)
    
    **Örnek:** 01/2023, 02/2023, 12/2024 şeklinde tarih sütunları
    
    **Avantajları:**
    - Her tesisat tek satır
    - Kolay görselleştirme
    - Hızlı anomali tespiti
    - Zaman serisi analizi
    """)
