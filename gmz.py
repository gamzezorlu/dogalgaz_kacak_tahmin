import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows

st.set_page_config(page_title="Doğalgaz Kaçak Tespit", layout="wide", page_icon="🔥")

# Başlık
st.title("🔥 Doğalgaz Kaçak Kullanım Tespit Sistemi")
st.markdown("---")

# Sidebar - Parametreler
with st.sidebar:
    st.header("⚙️ Analiz Parametreleri")
    
    dusus_esigi = st.slider("Ani Düşüş Eşiği (%)", 0, 100, 70, 5,
                            help="Bir aydan diğerine bu %'den fazla düşüş şüpheli sayılır")
    
    sifir_ay = st.slider("Min. Sıfır Tüketim (Ay)", 1, 12, 3,
                         help="Bu kadar ay üst üste sıfır tüketim şüpheli sayılır")
    
    bina_sapma_carpan = st.slider("Bina Sapma Çarpanı", 1.0, 5.0, 2.5, 0.5,
                                   help="Bina ortalamasından bu kadar std sapma uzak olanlar şüpheli")
    
    min_bina_daire = st.number_input("Min. Daire Sayısı (Bina Analizi)", 2, 50, 3,
                                      help="Bina analizinde en az bu kadar daire olmalı")
    
    st.markdown("---")
    st.markdown("### 📊 Tespit Yöntemleri")
    st.markdown("""
    - **Ani Düşüş**: Tüketimde keskin düşüş
    - **Sıfır Tüketim**: Uzun süre sıfır kayıt
    - **Bina Anomalisi**: Aynı binadaki diğer dairelere göre anormal tüketim
    - **Yüksek Varyasyon**: Düzensiz tüketim paterni
    """)

# Dosya yükleme
uploaded_file = st.file_uploader("📁 Excel Dosyası Yükleyin", type=['xlsx', 'xls'])

if uploaded_file is not None:
    try:
        # Excel dosyasını oku
        df = pd.read_excel(uploaded_file)
        
        # Sütun isimlerini temizle
        df.columns = df.columns.str.strip()
        
        st.success(f"✅ {len(df)} satır veri yüklendi")
        
        # Ay sütunlarını bul (2019/1, 2023/07 formatında)
        ay_sutunlari = [col for col in df.columns if '/' in str(col) or col.isdigit()]
        
        # Veriyi numerik yap
        for col in ay_sutunlari:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        st.markdown("---")
        
        # Genel istatistikler
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Toplam Tesisat", len(df))
        with col2:
            st.metric("Toplam Bina", df['bn'].nunique())
        with col3:
            st.metric("Analiz Ayı", len(ay_sutunlari))
        with col4:
            toplam_tuketim = df[ay_sutunlari].sum().sum()
            st.metric("Toplam Tüketim", f"{toplam_tuketim:,.0f}")
        
        st.markdown("---")
        
        # Analiz fonksiyonları
        def bina_analizi(df, bn_col, ay_cols):
            """Bina bazında anomali tespiti"""
            bina_anomaliler = []
            
            for bina in df[bn_col].unique():
                bina_df = df[df[bn_col] == bina].copy()
                
                if len(bina_df) < min_bina_daire:
                    continue
                
                # Her ay için bina ortalaması ve std sapma
                for ay in ay_cols:
                    bina_ort = bina_df[ay].mean()
                    bina_std = bina_df[ay].std()
                    
                    if bina_std == 0 or pd.isna(bina_std):
                        continue
                    
                    # Her daire için kontrol
                    for idx, row in bina_df.iterrows():
                        deger = row[ay]
                        z_score = abs((deger - bina_ort) / bina_std) if bina_std > 0 else 0
                        
                        if z_score > bina_sapma_carpan and bina_ort > 10:
                            bina_anomaliler.append({
                                'tn': row['tn'],
                                'bn': bina,
                                'ay': ay,
                                'deger': deger,
                                'bina_ort': bina_ort,
                                'bina_std': bina_std,
                                'z_score': z_score,
                                'sapma_tipi': 'Düşük' if deger < bina_ort else 'Yüksek'
                            })
            
            return pd.DataFrame(bina_anomaliler)
        
        def ani_dusus_tespiti(df, ay_cols):
            """Ani düşüş tespiti"""
            sonuclar = []
            
            for idx, row in df.iterrows():
                for i in range(1, len(ay_cols)):
                    onceki = row[ay_cols[i-1]]
                    simdiki = row[ay_cols[i]]
                    
                    if onceki > 0 and simdiki >= 0:
                        dusus_orani = ((onceki - simdiki) / onceki) * 100
                        
                        if dusus_orani >= dusus_esigi:
                            sonuclar.append({
                                'tn': row['tn'],
                                'bn': row['bn'],
                                'onceki_ay': ay_cols[i-1],
                                'simdiki_ay': ay_cols[i],
                                'onceki_deger': onceki,
                                'simdiki_deger': simdiki,
                                'dusus_orani': dusus_orani
                            })
            
            return pd.DataFrame(sonuclar)
        
        def sifir_tuketim_tespiti(df, ay_cols):
            """Sıfır tüketim tespiti"""
            sonuclar = []
            
            for idx, row in df.iterrows():
                sifir_sayaci = 0
                baslangic_ay = None
                
                for ay in ay_cols:
                    if row[ay] == 0:
                        if sifir_sayaci == 0:
                            baslangic_ay = ay
                        sifir_sayaci += 1
                    else:
                        if sifir_sayaci >= sifir_ay:
                            sonuclar.append({
                                'tn': row['tn'],
                                'bn': row['bn'],
                                'baslangic': baslangic_ay,
                                'bitis': ay_cols[ay_cols.index(ay) - 1] if ay_cols.index(ay) > 0 else ay,
                                'sure_ay': sifir_sayaci
                            })
                        sifir_sayaci = 0
                        baslangic_ay = None
                
                # Son ay sıfırsa
                if sifir_sayaci >= sifir_ay:
                    sonuclar.append({
                        'tn': row['tn'],
                        'bn': row['bn'],
                        'baslangic': baslangic_ay,
                        'bitis': ay_cols[-1],
                        'sure_ay': sifir_sayaci
                    })
            
            return pd.DataFrame(sonuclar)
        
        def varyasyon_analizi(df, ay_cols):
            """Varyasyon katsayısı analizi"""
            sonuclar = []
            
            for idx, row in df.iterrows():
                degerler = [row[ay] for ay in ay_cols if row[ay] > 0]
                
                if len(degerler) >= 3:
                    ortalama = np.mean(degerler)
                    std_sapma = np.std(degerler)
                    cv = (std_sapma / ortalama * 100) if ortalama > 0 else 0
                    
                    if cv > 80:
                        sonuclar.append({
                            'tn': row['tn'],
                            'bn': row['bn'],
                            'ortalama': ortalama,
                            'std_sapma': std_sapma,
                            'cv': cv
                        })
            
            return pd.DataFrame(sonuclar)
        
        # Analizleri çalıştır
        with st.spinner("🔍 Anomaliler tespit ediliyor..."):
            bina_anom = bina_analizi(df, 'bn', ay_sutunlari)
            ani_dusus = ani_dusus_tespiti(df, ay_sutunlari)
            sifir_tuketim = sifir_tuketim_tespiti(df, ay_sutunlari)
            varyasyon = varyasyon_analizi(df, ay_sutunlari)
        
        # Risk skoru hesapla
        def risk_skoru_hesapla(tn, bn):
            skor = 0
            
            # Bina anomalisi (en önemli)
            if len(bina_anom) > 0:
                bina_say = len(bina_anom[(bina_anom['tn'] == tn) & (bina_anom['sapma_tipi'] == 'Düşük')])
                skor += bina_say * 40
            
            # Ani düşüş
            if len(ani_dusus) > 0:
                dusus_say = len(ani_dusus[ani_dusus['tn'] == tn])
                skor += dusus_say * 30
            
            # Sıfır tüketim
            if len(sifir_tuketim) > 0:
                sifir_say = len(sifir_tuketim[sifir_tuketim['tn'] == tn])
                skor += sifir_say * 25
            
            # Varyasyon
            if len(varyasyon) > 0 and tn in varyasyon['tn'].values:
                cv_deger = varyasyon[varyasyon['tn'] == tn]['cv'].values[0]
                skor += min(cv_deger / 10, 20)
            
            return skor
        
        # Şüpheli tesisatları topla
        tum_supheliler = set()
        if len(bina_anom) > 0:
            tum_supheliler.update(bina_anom['tn'].unique())
        if len(ani_dusus) > 0:
            tum_supheliler.update(ani_dusus['tn'].unique())
        if len(sifir_tuketim) > 0:
            tum_supheliler.update(sifir_tuketim['tn'].unique())
        if len(varyasyon) > 0:
            tum_supheliler.update(varyasyon['tn'].unique())
        
        # Risk skorları ile sırala
        skor_listesi = []
        for tn in tum_supheliler:
            bn = df[df['tn'] == tn]['bn'].values[0]
            skor = risk_skoru_hesapla(tn, bn)
            skor_listesi.append({'tn': tn, 'bn': bn, 'risk_skoru': skor})
        
        skor_df = pd.DataFrame(skor_listesi).sort_values('risk_skoru', ascending=False)
        
        # Sonuçlar
        st.header("📊 Analiz Sonuçları")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🏢 Bina Anomalisi", len(bina_anom['tn'].unique()) if len(bina_anom) > 0 else 0)
        with col2:
            st.metric("📉 Ani Düşüş", len(ani_dusus['tn'].unique()) if len(ani_dusus) > 0 else 0)
        with col3:
            st.metric("⭕ Sıfır Tüketim", len(sifir_tuketim['tn'].unique()) if len(sifir_tuketim) > 0 else 0)
        with col4:
            st.metric("📊 Yüksek Varyasyon", len(varyasyon) if len(varyasyon) > 0 else 0)
        
        st.markdown("---")
        
        if len(skor_df) > 0:
            st.subheader(f"🚨 Toplam {len(skor_df)} Şüpheli Tesisat Tespit Edildi")
            
            # Risk dağılımı
            yuksek_risk = len(skor_df[skor_df['risk_skoru'] >= 100])
            orta_risk = len(skor_df[(skor_df['risk_skoru'] >= 50) & (skor_df['risk_skoru'] < 100)])
            dusuk_risk = len(skor_df[skor_df['risk_skoru'] < 50])
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("🔴 Yüksek Risk (≥100)", yuksek_risk)
            with col2:
                st.metric("🟡 Orta Risk (50-99)", orta_risk)
            with col3:
                st.metric("🟢 Düşük Risk (<50)", dusuk_risk)
            
            st.markdown("---")
            
            # Detaylı sonuçlar
            for idx, row in skor_df.head(20).iterrows():
                tn = row['tn']
                bn = row['bn']
                skor = row['risk_skoru']
                
                # Risk seviyesi
                if skor >= 100:
                    risk_renk = "🔴"
                    risk_etiket = "YÜKSEK RİSK"
                elif skor >= 50:
                    risk_renk = "🟡"
                    risk_etiket = "ORTA RİSK"
                else:
                    risk_renk = "🟢"
                    risk_etiket = "DÜŞÜK RİSK"
                
                with st.expander(f"{risk_renk} **Tesisat: {tn}** | Bina: {bn} | Risk: {skor:.0f} - {risk_etiket}"):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        # Tüketim grafiği
                        tesisat_data = df[df['tn'] == tn][ay_sutunlari].values[0]
                        bina_data = df[df['bn'] == bn][ay_sutunlari].mean().values
                        
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=ay_sutunlari, y=tesisat_data, 
                                                name='Tesisat', mode='lines+markers',
                                                line=dict(color='red', width=2)))
                        fig.add_trace(go.Scatter(x=ay_sutunlari, y=bina_data, 
                                                name='Bina Ortalaması', mode='lines',
                                                line=dict(color='blue', width=2, dash='dash')))
                        
                        fig.update_layout(title=f'Tesisat {tn} - Bina {bn} Karşılaştırması',
                                        xaxis_title='Ay', yaxis_title='Tüketim',
                                        height=300, hovermode='x unified')
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        st.markdown("### 📋 Tespit Detayları")
                        
                        # Bina anomalisi
                        if len(bina_anom) > 0:
                            tn_bina_anom = bina_anom[bina_anom['tn'] == tn]
                            if len(tn_bina_anom) > 0:
                                st.markdown(f"**🏢 Bina Anomalisi:** {len(tn_bina_anom)} ay")
                                dusuk_anom = tn_bina_anom[tn_bina_anom['sapma_tipi'] == 'Düşük']
                                if len(dusuk_anom) > 0:
                                    for _, anom in dusuk_anom.head(3).iterrows():
                                        st.markdown(f"- {anom['ay']}: {anom['deger']:.0f} (Bina ort: {anom['bina_ort']:.0f})")
                        
                        # Ani düşüş
                        if len(ani_dusus) > 0:
                            tn_dusus = ani_dusus[ani_dusus['tn'] == tn]
                            if len(tn_dusus) > 0:
                                st.markdown(f"**📉 Ani Düşüş:** {len(tn_dusus)} kez")
                                for _, d in tn_dusus.head(3).iterrows():
                                    st.markdown(f"- {d['simdiki_ay']}: %{d['dusus_orani']:.1f} düşüş")
                        
                        # Sıfır tüketim
                        if len(sifir_tuketim) > 0:
                            tn_sifir = sifir_tuketim[sifir_tuketim['tn'] == tn]
                            if len(tn_sifir) > 0:
                                st.markdown(f"**⭕ Sıfır Tüketim:** {len(tn_sifir)} dönem")
                                for _, s in tn_sifir.head(2).iterrows():
                                    st.markdown(f"- {s['baslangic']} - {s['bitis']}: {s['sure_ay']} ay")
                        
                        # Varyasyon
                        if len(varyasyon) > 0 and tn in varyasyon['tn'].values:
                            tn_var = varyasyon[varyasyon['tn'] == tn].iloc[0]
                            st.markdown(f"**📊 Varyasyon:** CV = %{tn_var['cv']:.1f}")
            
            # Excel export
            st.markdown("---")
            st.subheader("📥 Rapor İndir")
            
            # Tüm şüpheli tesisatların detaylı raporu
            rapor_data = []
            for _, row in skor_df.iterrows():
                tn = row['tn']
                bn = row['bn']
                
                # Tesisat verisini al
                tesisat_row = df[df['tn'] == tn].iloc[0]
                
                detay = {
                    'Tesisat No': tn,
                    'Bina No': bn,
                    'Risk Skoru': round(row['risk_skoru'], 2)
                }
                
                # Anomali detayları
                bina_anom_count = len(bina_anom[bina_anom['tn'] == tn]) if len(bina_anom) > 0 else 0
                ani_dusus_count = len(ani_dusus[ani_dusus['tn'] == tn]) if len(ani_dusus) > 0 else 0
                sifir_count = len(sifir_tuketim[sifir_tuketim['tn'] == tn]) if len(sifir_tuketim) > 0 else 0
                
                detay['Bina Anomali Sayısı'] = bina_anom_count
                detay['Ani Düşüş Sayısı'] = ani_dusus_count
                detay['Sıfır Tüketim Dönem'] = sifir_count
                
                # Varyasyon
                if len(varyasyon) > 0 and tn in varyasyon['tn'].values:
                    cv_val = varyasyon[varyasyon['tn'] == tn]['cv'].values[0]
                    detay['Varyasyon Katsayısı (%)'] = round(cv_val, 2)
                else:
                    detay['Varyasyon Katsayısı (%)'] = 0
                
                # Risk kategorisi
                if row['risk_skoru'] >= 100:
                    detay['Risk Seviyesi'] = 'YÜKSEK'
                elif row['risk_skoru'] >= 50:
                    detay['Risk Seviyesi'] = 'ORTA'
                else:
                    detay['Risk Seviyesi'] = 'DÜŞÜK'
                
                # Aylık tüketim verilerini ekle
                for ay in ay_sutunlari:
                    detay[ay] = tesisat_row[ay]
                
                rapor_data.append(detay)
            
            rapor_df = pd.DataFrame(rapor_data)
            
            # Excel oluştur
            def create_excel_report(df_rapor, df_bina_anom, df_dusus, df_sifir, df_var):
                output = BytesIO()
                writer = pd.ExcelWriter(output, engine='openpyxl')
                
                # Sheet 1: Ana Rapor
                df_rapor.to_excel(writer, sheet_name='Şüpheli Tesisatlar', index=False)
                
                # Sheet 2: Bina Anomalileri
                if len(df_bina_anom) > 0:
                    df_bina_anom.to_excel(writer, sheet_name='Bina Anomalileri', index=False)
                
                # Sheet 3: Ani Düşüşler
                if len(df_dusus) > 0:
                    df_dusus.to_excel(writer, sheet_name='Ani Düşüşler', index=False)
                
                # Sheet 4: Sıfır Tüketim
                if len(df_sifir) > 0:
                    df_sifir.to_excel(writer, sheet_name='Sıfır Tüketim', index=False)
                
                # Sheet 5: Varyasyon
                if len(df_var) > 0:
                    df_var.to_excel(writer, sheet_name='Yüksek Varyasyon', index=False)
                
                writer.close()
                
                # Stil ekle
                output.seek(0)
                wb = openpyxl.load_workbook(output)
                
                # Ana rapor sayfası stil
                ws = wb['Şüpheli Tesisatlar']
                
                # Başlık satırı stil
                header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
                header_font = Font(color='FFFFFF', bold=True, size=11)
                
                for cell in ws[1]:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                
                # Risk seviyesine göre renklendirme
                red_fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
                yellow_fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')
                green_fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
                
                risk_col = None
                for idx, cell in enumerate(ws[1], 1):
                    if cell.value == 'Risk Seviyesi':
                        risk_col = idx
                        break
                
                if risk_col:
                    for row in range(2, ws.max_row + 1):
                        risk_cell = ws.cell(row=row, column=risk_col)
                        if risk_cell.value == 'YÜKSEK':
                            for col in range(1, ws.max_column + 1):
                                ws.cell(row=row, column=col).fill = red_fill
                        elif risk_cell.value == 'ORTA':
                            for col in range(1, ws.max_column + 1):
                                ws.cell(row=row, column=col).fill = yellow_fill
                        elif risk_cell.value == 'DÜŞÜK':
                            for col in range(1, ws.max_column + 1):
                                ws.cell(row=row, column=col).fill = green_fill
                
                # Sütun genişliklerini ayarla
                for column in ws.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    ws.column_dimensions[column_letter].width = adjusted_width
                
                # Diğer sayfalar için de stil ekle
                for sheet_name in wb.sheetnames:
                    if sheet_name != 'Şüpheli Tesisatlar':
                        ws_other = wb[sheet_name]
                        for cell in ws_other[1]:
                            cell.fill = header_fill
                            cell.font = header_font
                            cell.alignment = Alignment(horizontal='center', vertical='center')
                        
                        for column in ws_other.columns:
                            max_length = 0
                            column_letter = column[0].column_letter
                            for cell in column:
                                try:
                                    if len(str(cell.value)) > max_length:
                                        max_length = len(str(cell.value))
                                except:
                                    pass
                            adjusted_width = min(max_length + 2, 50)
                            ws_other.column_dimensions[column_letter].width = adjusted_width
                
                output = BytesIO()
                wb.save(output)
                output.seek(0)
                
                return output.getvalue()
            
            excel_data = create_excel_report(rapor_df, bina_anom, ani_dusus, sifir_tuketim, varyasyon)
            
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="📊 Detaylı Excel Raporu İndir",
                    data=excel_data,
                    file_name="dogalgaz_kacak_detayli_rapor.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with col2:
                # Basit CSV de sunalım
                csv = rapor_df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📄 CSV Raporu İndir",
                    data=csv,
                    file_name="dogalgaz_kacak_raporu.csv",
                    mime="text/csv"
                )
            
        else:
            st.success("✅ Belirlenen kriterlere göre şüpheli tesisat bulunamadı!")
            
    except Exception as e:
        st.error(f"❌ Hata: {str(e)}")
        st.info("Dosya formatını kontrol edin. İlk sütunlar 'tn' ve 'bn' olmalı, sonra ay kolonları gelmelidir.")
else:
    st.info("👆 Lütfen yukarıdan CSV dosyanızı yükleyin.")
    
    st.markdown("---")
    st.markdown("### 📝 Dosya Formatı")
    st.markdown("""
    CSV dosyanız şu formatta olmalıdır:
    - İlk sütun: **tn** (Tesisat numarası)
    - İkinci sütun: **bn** (Bina numarası)
    - Sonraki sütunlar: Ay verileri (2023/07, 2023/08, vb.)
    
    Örnek:
    ```
    tn,bn,2023/07,2023/08,2023/09,...
    10009832,100003724,18.4914,18.4316,8.18468,...
    ```
    """)
