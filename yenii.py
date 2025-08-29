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
    help="Excel dosyası: Tüketim Noktası, Bağlantı Nesnesi, Belge Tarihi, SM3 sütunları içermelidir"
)

if uploaded_file is not None:
    try:
        # Excel dosyasını okuma
        df = pd.read_excel(uploaded_file)
        
        # Sütun adlarını temizleme (büyük/küçük harf ve boşluk hassasiyetini kaldırmak için)
        df.columns = df.columns.astype(str).str.strip()
        
        # Sütun adlarını normalize etme fonksiyonu
        def normalize_column_name(col_name):
            return col_name.lower().replace('ı', 'i').replace('ğ', 'g').replace('ü', 'u').replace('ö', 'o').replace('ş', 's').replace('ç', 'c').strip()
        
        # Gerekli sütunları bulma ve eşleme
        sutun_esleme = {}
        
        # Her sütunu normalize ederek kontrol etme
        for col in df.columns:
            col_normalized = normalize_column_name(col)
            
            if 'tuketim' in col_normalized and 'nokta' in col_normalized:
                sutun_esleme['tuketim_noktasi'] = col
            elif 'baglanti' in col_normalized and 'nesne' in col_normalized:
                sutun_esleme['baglanti_nesnesi'] = col
            elif 'belge' in col_normalized and 'tarih' in col_normalized:
                sutun_esleme['belge_tarihi'] = col
            elif col_normalized in ['sm3', 'sm³']:
                sutun_esleme['sm3'] = col
        
        # Eksik sütunları kontrol etme
        gerekli_alanlar = ['tuketim_noktasi', 'baglanti_nesnesi', 'belge_tarihi', 'sm3']
        eksik_sutunlar = []
        
        for gerekli in gerekli_alanlar:
            if gerekli not in sutun_esleme:
                eksik_sutunlar.append(gerekli)
        
        if eksik_sutunlar:
            st.error(f"❌ Şu sütunlar bulunamadı: {', '.join(eksik_sutunlar)}")
            st.info("📋 Mevcut sütunlar:")
            for i, col in enumerate(df.columns, 1):
                st.write(f"{i}. **{col}**")
            
            st.info("💡 Beklenen sütun isimleri (tam eşleşme):")
            st.write("• **Tüketim noktası**")
            st.write("• **Bağlantı nesnesi**")  
            st.write("• **Belge tarihi**")
            st.write("• **Sm3**")
            st.stop()
        
        # Sütun adlarını standartlaştırma
        df_temiz = df.rename(columns={
            sutun_esleme['tuketim_noktasi']: 'tuketim_noktasi',
            sutun_esleme['baglanti_nesnesi']: 'baglanti_nesnesi',
            sutun_esleme['belge_tarihi']: 'belge_tarihi',
            sutun_esleme['sm3']: 'tuketim_miktari'
        })
        
        # Sadece gerekli sütunları seçme
        df_temiz = df_temiz[['tuketim_noktasi', 'baglanti_nesnesi', 'belge_tarihi', 'tuketim_miktari']].copy()
        
        # Tarih sütununu işleme
        try:
            df_temiz['tarih'] = pd.to_datetime(df_temiz['belge_tarihi'], errors='coerce')
            # Geçersiz tarihleri kaldırma
            df_temiz = df_temiz.dropna(subset=['tarih'])
        except:
            st.error("❌ Belge Tarihi sütunu tarih formatında değil!")
            st.stop()
        
        # Ay ve yıl bilgilerini ekleme
        df_temiz['ay'] = df_temiz['tarih'].dt.month
        df_temiz['yil'] = df_temiz['tarih'].dt.year
        df_temiz['tarih_str'] = df_temiz['tarih'].dt.strftime('%m/%Y')
        
        # Tüketim değerlerini temizleme
        df_temiz['tuketim_miktari'] = pd.to_numeric(df_temiz['tuketim_miktari'], errors='coerce')
        df_temiz = df_temiz.dropna(subset=['tuketim_miktari'])
        
        # Sıfır ve negatif değerleri kaldırma
        df_temiz = df_temiz[df_temiz['tuketim_miktari'] > 0]
        
        # Tüketim noktası ve bağlantı nesnesi değerlerini string'e çevirme
        df_temiz['tuketim_noktasi'] = df_temiz['tuketim_noktasi'].astype(str)
        df_temiz['baglanti_nesnesi'] = df_temiz['baglanti_nesnesi'].astype(str)
        
        st.success(f"✅ Dosya başarıyla işlendi! {len(df_temiz)} kayıt oluşturuldu.")
        
        # Veri önizlemesi
        with st.expander("📊 İşlenmiş Veri Önizlemesi"):
            st.dataframe(df_temiz.head(10))
            
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Toplam Kayıt", len(df_temiz))
        with col2:
            st.metric("Tesisat Sayısı", df_temiz['tuketim_noktasi'].nunique())
        with col3:
            st.metric("Bina Sayısı", df_temiz['baglanti_nesnesi'].nunique())
        with col4:
            tarih_aralik = f"{df_temiz['tarih'].min().strftime('%m/%Y')} - {df_temiz['tarih'].max().strftime('%m/%Y')}"
            st.metric("Tarih Aralığı", tarih_aralik)
            
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
                kis_verileri = tesisat_data[tesisat_data['ay'].isin(kis_aylari)]
                if kis_verileri.empty:
                    continue
                    
                kis_ortalamalari = kis_verileri.groupby('yil')['tuketim_miktari'].mean()
                
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
        anomali_1 = kis_dusukluk_anomalisi(df_temiz, kis_tuketim_esigi)
        
        status_text.text("🔍 Bina ortalamasından düşük tüketim anomalileri tespit ediliyor...")
        progress_bar.progress(50)
        anomali_2 = bina_ortalamasindan_dusuk_anomali(df_temiz, bina_ort_dusuk_oran)
        
        status_text.text("🔍 Ani düşüş anomalileri tespit ediliyor...")
        progress_bar.progress(75)
        anomali_3 = ani_dusus_anomalisi(df_temiz, ani_dusus_orani, min_onceki_kis_tuketim)
        
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
            
            # Aynı tesisat için anomali özetleme (tüm ayları birleştirme)
            def tesisat_anomali_ozeti(group):
                ozet = group.iloc[0].copy()
                
                # Anomali türlerini birleştir
                anomali_turleri = group['anomali_tipi'].unique()
                ozet['anomali_tipi'] = ' + '.join(anomali_turleri)
                
                # Tarih aralığını belirle
                tarihler = group['tarih_str'].unique()
                if len(tarihler) == 1:
                    ozet['tarih_str'] = tarihler[0]
                else:
                    ozet['tarih_str'] = f"{min(tarihler)} - {max(tarihler)}"
                
                # Tüketim istatistikleri
                ozet['tuketim_miktari'] = group['tuketim_miktari'].mean()  # Ortalama tüketim
                ozet['min_tuketim'] = group['tuketim_miktari'].min()
                ozet['max_tuketim'] = group['tuketim_miktari'].max()
                ozet['anomali_sayisi'] = len(group)
                
                # Açıklamayı güncelle
                ozet['aciklama'] = f"Toplam {len(group)} anomali - {', '.join(anomali_turleri)}"
                
                return ozet
            
            # Tesisat bazında anomalileri özetleme
            anomali_df = anomali_df.groupby('tuketim_noktasi').apply(tesisat_anomali_ozeti).reset_index(drop=True)
            
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
            aylik_dag = anomali_df.groupby(['yil', 'ay']).size().reset_index(name='count')
            aylik_dag['ay_yil'] = aylik_dag['ay'].astype(str).str.zfill(2) + '/' + aylik_dag['yil'].astype(str)
            
            fig2 = px.bar(
                aylik_dag.sort_values(['yil', 'ay']),
                x='ay_yil', y='count', color='yil',
                title="Aylık Anomali Dağılımı",
                labels={'ay_yil': 'Ay/Yıl', 'count': 'Anomali Sayısı'}
            )
            st.plotly_chart(fig2, use_container_width=True)
            
            # Bina bazlı anomali dağılımı
            bina_dag = anomali_df.groupby('baglanti_nesnesi').size().reset_index(name='count')
            bina_dag = bina_dag.sort_values('count', ascending=False).head(20)
            
            if len(bina_dag) > 1:
                fig3 = px.bar(
                    bina_dag,
                    x='baglanti_nesnesi', y='count',
                    title="En Çok Anomaliye Sahip Binalar (İlk 20)",
                    labels={'baglanti_nesnesi': 'Bağlantı Nesnesi', 'count': 'Anomali Sayısı'}
                )
                st.plotly_chart(fig3, use_container_width=True)
            
            # Anomalili tesisatların detaylı listesi
            with st.expander("📋 Anomalili Tesisatlar Detayı"):
                # Filtre seçenekleri
                col1, col2 = st.columns(2)
                with col1:
                    secili_anomali_tip = st.selectbox(
                        "Anomali Türü",
                        ['Tümü'] + list(anomali_df['anomali_tipi'].unique())
                    )
                with col2:
                    secili_bina = st.selectbox(
                        "Bağlantı Nesnesi",
                        ['Tümü'] + sorted(list(anomali_df['baglanti_nesnesi'].unique()))
                    )
                
                # Filtreleme
                filtered_df = anomali_df.copy()
                if secili_anomali_tip != 'Tümü':
                    filtered_df = filtered_df[filtered_df['anomali_tipi'] == secili_anomali_tip]
                if secili_bina != 'Tümü':
                    filtered_df = filtered_df[filtered_df['baglanti_nesnesi'] == secili_bina]
                
                # Detay tablosu
                detay_sutunlar = ['tuketim_noktasi', 'baglanti_nesnesi', 'tarih_str', 
                                'tuketim_miktari', 'anomali_tipi', 'aciklama']
                st.dataframe(filtered_df[detay_sutunlar], use_container_width=True)
                
            # Excel indirme
            def convert_df_to_excel(df):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # Ana anomali verileri
                    df_export = df.copy()
                    df_export = df_export[['tuketim_noktasi', 'baglanti_nesnesi', 'belge_tarihi', 
                                         'tarih_str', 'tuketim_miktari', 'anomali_tipi', 'aciklama']]
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
                    
                    # Bina bazlı özet
                    bina_ozet = anomali_df.groupby('baglanti_nesnesi').agg({
                        'tuketim_noktasi': 'nunique',
                        'anomali_tipi': lambda x: ', '.join(x.unique()),
                        'tuketim_miktari': ['count', 'mean']
                    }).round(2)
                    bina_ozet.columns = ['Tesisat_Sayısı', 'Anomali_Türleri', 'Toplam_Anomali', 'Ortalama_Tüketim']
                    bina_ozet.to_excel(writer, sheet_name='Bina_Özeti')
                    
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
        'Tüketim Noktası': ['10843655', '10843655', '10843656', '10843656', '10843657'],
        'Bağlantı Nesnesi': ['100000612', '100000612', '100000612', '100000612', '100000613'],
        'Belge Tarihi': ['2023-01-15', '2023-02-15', '2023-01-15', '2023-02-15', '2023-01-15'],
        'SM3': [285, 275, 190, 15, 220]  # Son kayıt anomali örneği
    }
    
    ornek_df = pd.DataFrame(ornek_data)
    st.dataframe(ornek_df)
    
    st.markdown("""
    **Veri Formatı Açıklaması:**
    - **Tüketim Noktası**: Her tesisatın benzersiz numarası
    - **Bağlantı Nesnesi**: Tesisatın bağlı olduğu bina numarası  
    - **Belge Tarihi**: Tüketim okuma tarihi (Excel tarih formatında)
    - **SM3**: Aylık doğalgaz tüketimi (standart metreküp)
    
    **Özellikler:**
    - ✅ Her satır bir tüketim kaydı
    - ✅ Aynı tesisat farklı aylarda birden fazla kayda sahip olabilir
    - ✅ Tarih formatı esnek (Excel'in tanıdığı herhangi bir tarih formatı)
    - ✅ Otomatik sütun ismi eşleştirme
    - ✅ Veri temizleme ve doğrulama
    """)
