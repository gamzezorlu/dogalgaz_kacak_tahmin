import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from io import BytesIO
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment

st.set_page_config(page_title="Doğalgaz Kaçak Tespit", layout="wide", page_icon="🔥")

st.title("🔥 Doğalgaz Kaçak Kullanım Tespit Sistemi")
st.markdown("### Basit, Etkili, Güvenilir")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("⚙️ Tespit Kriterleri")
    
    st.markdown("### 🎯 Ana Kriterler")
    
    dusus_esigi = st.slider("Ani Düşüş Eşiği (%)", 40, 90, 65, 5,
                            help="Bu %'den fazla düşüş kaçak şüphesi yaratır")
    
    min_tuketim = st.number_input("Minimum Normal Tüketim", 5, 100, 15,
                                   help="Bu değerin altı çok düşük sayılır")
    
    bina_fark_orani = st.slider("Bina Farkı Eşiği (%)", 30, 80, 50, 5,
                                 help="Bina ortalamasından bu kadar az tüketim şüpheli")
    
    ardisik_dusuk = st.slider("Ardışık Düşük Tüketim (Ay)", 2, 8, 3,
                              help="Bu kadar ay üst üste düşük tüketim şüpheli")
    
    st.markdown("---")
    st.markdown("### 📋 Tespit Mantığı")
    st.markdown("""
    **1. Bina Karşılaştırma**
    - Aynı binadaki komşularla karşılaştır
    - Normal ortalamadan %50+ az tüketim = ŞÜPHELİ
    
    **2. Ani Düşüş**
    - Bir aydan diğerine %65+ düşüş = ŞÜPHELİ
    - Özellikle yüksek tüketimden aniden düşük
    
    **3. Sürekli Düşük Tüketim**
    - 3+ ay boyunca çok düşük tüketim = ŞÜPHELİ
    - Sıfır veya minimum düzeyde
    
    **4. Ters Patern**
    - Herkes yükselirken düşüyor = ŞÜPHELİ
    - Kış aylarında anormal düşük
    """)

uploaded_file = st.file_uploader("📁 Excel Dosyası Yükleyin", type=['xlsx', 'xls'])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        df.columns = df.columns.str.strip()
        
        # Ay sütunları
        ay_sutunlari = [col for col in df.columns if col not in ['tn', 'bn']]
        
        for col in ay_sutunlari:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        st.success(f"✅ {len(df)} tesisat, {len(ay_sutunlari)} ay verisi yüklendi")
        st.markdown("---")
        
        # Analiz
        with st.spinner("🔍 Analiz yapılıyor..."):
            
            supheliler = []
            
            # Her tesisat için analiz
            for idx, row in df.iterrows():
                tn = row['tn']
                bn = row['bn']
                tuketimler = row[ay_sutunlari].values
                
                # Bina bilgileri
                bina_df = df[df['bn'] == bn]
                bina_daire_sayisi = len(bina_df)
                
                # Yeterli daire yoksa atla
                if bina_daire_sayisi < 2:
                    continue
                
                # Her ay için bina ortalaması
                bina_ortalamalar = bina_df[ay_sutunlari].mean()
                
                # Şüphe puanı
                suphe_puani = 0
                sebepler = []
                detaylar = []
                
                # 1. Bina Karşılaştırması (EN ÖNEMLİ)
                bina_dusuk_sayisi = 0
                for i, ay in enumerate(ay_sutunlari):
                    bina_ort = bina_ortalamalar[ay]
                    tuketim = tuketimler[i]
                    
                    # Bina ortalaması yeterince yüksek ve bu tesisat çok düşükse
                    if bina_ort > 20:
                        fark_orani = (bina_ort - tuketim) / bina_ort * 100
                        
                        if fark_orani > bina_fark_orani:
                            bina_dusuk_sayisi += 1
                            detaylar.append({
                                'tip': 'Bina Anomalisi',
                                'ay': ay,
                                'tuketim': tuketim,
                                'bina_ort': bina_ort,
                                'fark': fark_orani
                            })
                
                if bina_dusuk_sayisi >= 3:
                    suphe_puani += 50
                    sebepler.append(f"✗ Binadan {bina_dusuk_sayisi} ay boyunca %{bina_fark_orani}+ düşük")
                
                # 2. Ani Düşüş Kontrolü
                ani_dususler = []
                for i in range(1, len(tuketimler)):
                    onceki = tuketimler[i-1]
                    simdiki = tuketimler[i]
                    
                    if onceki > 20 and simdiki >= 0:
                        dusus = (onceki - simdiki) / onceki * 100
                        if dusus >= dusus_esigi:
                            ani_dususler.append({
                                'ay': ay_sutunlari[i],
                                'onceki': onceki,
                                'simdiki': simdiki,
                                'dusus': dusus
                            })
                            detaylar.append({
                                'tip': 'Ani Düşüş',
                                'ay': ay_sutunlari[i],
                                'tuketim': simdiki,
                                'onceki': onceki,
                                'dusus': dusus
                            })
                
                if len(ani_dususler) > 0:
                    suphe_puani += len(ani_dususler) * 25
                    sebepler.append(f"✗ {len(ani_dususler)} kez ani düşüş (%{dusus_esigi}+)")
                
                # 3. Sürekli Düşük Tüketim
                dusuk_sayac = 0
                max_dusuk_seri = 0
                for tuketim in tuketimler:
                    if tuketim < min_tuketim:
                        dusuk_sayac += 1
                        max_dusuk_seri = max(max_dusuk_seri, dusuk_sayac)
                    else:
                        dusuk_sayac = 0
                
                if max_dusuk_seri >= ardisik_dusuk:
                    suphe_puani += 30
                    sebepler.append(f"✗ {max_dusuk_seri} ay üst üste çok düşük tüketim (<{min_tuketim})")
                    detaylar.append({
                        'tip': 'Sürekli Düşük',
                        'sure': max_dusuk_seri
                    })
                
                # 4. Ters Patern (Kış düşük, yaz yüksek)
                # Son 12 ayda mevsimsel kontrol
                if len(tuketimler) >= 12:
                    son_12 = tuketimler[-12:]
                    # Kış ayları: 11,12,1,2,3 (indeks: 10,11,0,1,2)
                    # Basitleştirilmiş: İlk 6 ay vs son 6 ay
                    ilk_6_ort = np.mean(son_12[:6])
                    son_6_ort = np.mean(son_12[6:])
                    
                    if ilk_6_ort > 10 and son_6_ort > 10:
                        if son_6_ort < ilk_6_ort * 0.5:
                            suphe_puani += 20
                            sebepler.append("✗ Ters mevsimsel patern (kış düşük)")
                
                # Şüpheliyse kaydet
                if suphe_puani >= 50:
                    
                    # Risk seviyesi
                    if suphe_puani >= 100:
                        risk = "KRİTİK"
                    elif suphe_puani >= 70:
                        risk = "YÜKSEK"
                    else:
                        risk = "ORTA"
                    
                    supheliler.append({
                        'tn': tn,
                        'bn': bn,
                        'risk_puani': suphe_puani,
                        'risk_seviye': risk,
                        'sebepler': sebepler,
                        'detaylar': detaylar,
                        'bina_daire_sayisi': bina_daire_sayisi,
                        'ortalama_tuketim': np.mean(tuketimler[tuketimler > 0]) if np.any(tuketimler > 0) else 0,
                        'bina_ortalama': bina_ortalamalar.mean()
                    })
            
            # Sırala
            supheliler.sort(key=lambda x: x['risk_puani'], reverse=True)
        
        # Sonuçlar
        st.markdown("---")
        st.header("📊 Tespit Sonuçları")
        
        col1, col2, col3, col4 = st.columns(4)
        kritik = sum(1 for s in supheliler if s['risk_seviye'] == 'KRİTİK')
        yuksek = sum(1 for s in supheliler if s['risk_seviye'] == 'YÜKSEK')
        orta = sum(1 for s in supheliler if s['risk_seviye'] == 'ORTA')
        
        with col1:
            st.metric("🚨 Toplam Şüpheli", len(supheliler))
        with col2:
            st.metric("🔴 Kritik Risk", kritik)
        with col3:
            st.metric("🟠 Yüksek Risk", yuksek)
        with col4:
            st.metric("🟡 Orta Risk", orta)
        
        if supheliler:
            st.markdown("---")
            
            # Filtre
            risk_filtre = st.multiselect(
                "Risk Seviyesi Filtrele",
                ["KRİTİK", "YÜKSEK", "ORTA"],
                default=["KRİTİK", "YÜKSEK"]
            )
            
            filtered = [s for s in supheliler if s['risk_seviye'] in risk_filtre]
            
            st.subheader(f"🔍 {len(filtered)} Şüpheli Tesisat")
            
            for i, s in enumerate(filtered[:30], 1):
                
                if s['risk_seviye'] == 'KRİTİK':
                    color = "🔴"
                    bg_color = "#ffebee"
                elif s['risk_seviye'] == 'YÜKSEK':
                    color = "🟠"
                    bg_color = "#fff3e0"
                else:
                    color = "🟡"
                    bg_color = "#fffde7"
                
                with st.expander(f"{i}. {color} **Tesisat {s['tn']}** | Bina: {s['bn']} | Puan: {s['risk_puani']} - {s['risk_seviye']} RİSK"):
                    
                    col1, col2 = st.columns([3, 2])
                    
                    with col1:
                        # Grafik
                        tesisat_data = df[df['tn'] == s['tn']][ay_sutunlari].values[0]
                        bina_data = df[df['bn'] == s['bn']][ay_sutunlari].mean().values
                        
                        fig = go.Figure()
                        
                        # Tesisat çizgisi
                        fig.add_trace(go.Scatter(
                            x=ay_sutunlari,
                            y=tesisat_data,
                            name='Bu Tesisat',
                            mode='lines+markers',
                            line=dict(color='red', width=3),
                            marker=dict(size=8)
                        ))
                        
                        # Bina ortalaması
                        fig.add_trace(go.Scatter(
                            x=ay_sutunlari,
                            y=bina_data,
                            name=f'Bina Ortalaması ({s["bina_daire_sayisi"]} daire)',
                            mode='lines',
                            line=dict(color='blue', width=2, dash='dash')
                        ))
                        
                        fig.update_layout(
                            title=f'Tesisat {s["tn"]} vs Bina {s["bn"]} Ortalaması',
                            xaxis_title='Ay',
                            yaxis_title='Tüketim',
                            height=300,
                            hovermode='x unified'
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        st.markdown("### 🎯 Tespit Sebepleri")
                        st.markdown(f"**Risk Puanı:** {s['risk_puani']}")
                        st.markdown(f"**Risk Seviyesi:** {s['risk_seviye']}")
                        st.markdown("")
                        
                        for sebep in s['sebepler']:
                            st.markdown(sebep)
                        
                        st.markdown("---")
                        st.markdown("### 📈 İstatistikler")
                        st.markdown(f"**Bina Daire Sayısı:** {s['bina_daire_sayisi']}")
                        st.markdown(f"**Tesisat Ort. Tüketim:** {s['ortalama_tuketim']:.1f}")
                        st.markdown(f"**Bina Ort. Tüketim:** {s['bina_ortalama']:.1f}")
                        
                        if s['bina_ortalama'] > 0:
                            fark_genel = (s['bina_ortalama'] - s['ortalama_tuketim']) / s['bina_ortalama'] * 100
                            st.markdown(f"**Genel Fark:** %{fark_genel:.1f} düşük")
                    
                    # Detaylar
                    if s['detaylar']:
                        st.markdown("---")
                        st.markdown("### 📋 Detaylı Bulgular")
                        
                        # Tabloya dönüştür
                        detay_rows = []
                        for d in s['detaylar'][:10]:
                            if d['tip'] == 'Bina Anomalisi':
                                detay_rows.append({
                                    'Tip': 'Binadan Düşük',
                                    'Ay': d['ay'],
                                    'Tüketim': f"{d['tuketim']:.1f}",
                                    'Bina Ort.': f"{d['bina_ort']:.1f}",
                                    'Fark': f"%{d['fark']:.1f}"
                                })
                            elif d['tip'] == 'Ani Düşüş':
                                detay_rows.append({
                                    'Tip': 'Ani Düşüş',
                                    'Ay': d['ay'],
                                    'Önceki': f"{d['onceki']:.1f}",
                                    'Sonraki': f"{d['tuketim']:.1f}",
                                    'Düşüş': f"%{d['dusus']:.1f}"
                                })
                        
                        if detay_rows:
                            st.table(pd.DataFrame(detay_rows))
            
            # Excel export
            st.markdown("---")
            st.subheader("📥 Rapor İndir")
            
            def create_excel(supheliler, df, ay_sutunlari):
                output = BytesIO()
                
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # Ana rapor
                    rapor_data = []
                    for s in supheliler:
                        row = {
                            'Tesisat No': s['tn'],
                            'Bina No': s['bn'],
                            'Risk Seviyesi': s['risk_seviye'],
                            'Risk Puanı': s['risk_puani'],
                            'Bina Daire Sayısı': s['bina_daire_sayisi'],
                            'Ortalama Tüketim': round(s['ortalama_tuketim'], 2),
                            'Bina Ortalaması': round(s['bina_ortalama'], 2),
                            'Fark (%)': round((s['bina_ortalama'] - s['ortalama_tuketim']) / s['bina_ortalama'] * 100, 1) if s['bina_ortalama'] > 0 else 0,
                            'Tespit Sebepleri': ' | '.join(s['sebepler'])
                        }
                        
                        # Aylık veriler
                        tesisat_row = df[df['tn'] == s['tn']].iloc[0]
                        for ay in ay_sutunlari:
                            row[ay] = tesisat_row[ay]
                        
                        rapor_data.append(row)
                    
                    rapor_df = pd.DataFrame(rapor_data)
                    rapor_df.to_excel(writer, sheet_name='Şüpheli Tesisatlar', index=False)
                
                output.seek(0)
                
                # Stil
                wb = openpyxl.load_workbook(output)
                ws = wb['Şüpheli Tesisatlar']
                
                # Başlık
                header_fill = PatternFill(start_color='1a237e', end_color='1a237e', fill_type='solid')
                header_font = Font(color='FFFFFF', bold=True, size=11)
                
                for cell in ws[1]:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal='center')
                
                # Risk renklendirme
                for row in range(2, ws.max_row + 1):
                    risk = ws.cell(row=row, column=3).value
                    if risk == 'KRİTİK':
                        fill = PatternFill(start_color='ffcdd2', end_color='ffcdd2', fill_type='solid')
                    elif risk == 'YÜKSEK':
                        fill = PatternFill(start_color='ffe0b2', end_color='ffe0b2', fill_type='solid')
                    else:
                        fill = PatternFill(start_color='fff9c4', end_color='fff9c4', fill_type='solid')
                    
                    for col in range(1, 10):
                        ws.cell(row=row, column=col).fill = fill
                
                # Sütun genişlikleri
                ws.column_dimensions['A'].width = 15
                ws.column_dimensions['B'].width = 15
                ws.column_dimensions['C'].width = 12
                ws.column_dimensions['D'].width = 10
                ws.column_dimensions['I'].width = 60
                
                output2 = BytesIO()
                wb.save(output2)
                output2.seek(0)
                
                return output2.getvalue()
            
            excel_data = create_excel(supheliler, df, ay_sutunlari)
            
            st.download_button(
                label="📊 Excel Raporu İndir (Tüm Şüpheliler)",
                data=excel_data,
                file_name=f"dogalgaz_kacak_raporu_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        else:
            st.success("✅ Hiç şüpheli tesisat bulunamadı!")
            st.info("💡 Parametreleri gevşeterek daha hassas arama yapabilirsiniz.")
    
    except Exception as e:
        st.error(f"❌ Hata: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

else:
    st.info("👆 Excel dosyanızı yükleyin")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 💡 Nasıl Çalışır?")
        st.markdown("""
        **Basit ve Etkili Mantık:**
        
        1. **Komşularla Karşılaştır**
           - Aynı binadaki diğer dairelerle karşılaştırır
           - %50+ düşük tüketim = Şüpheli
        
        2. **Ani Değişim Ara**
           - Bir aydan diğerine %65+ düşüş = Şüpheli
        
        3. **Sürekli Düşük Tüketim**
           - 3+ ay çok düşük = Şüpheli
        
        4. **Net Risk Puanı**
           - 100+ Kritik
           - 70-99 Yüksek
           - 50-69 Orta
        """)
    
    with col2:
        st.markdown("### 📝 Dosya Formatı")
        st.markdown("""
        Excel dosyanız şu sütunları içermeli:
        
        | tn | bn | 2023/07 | 2023/08 | ... |
        |----|----|---------|---------| --- |
        | 100001 | 5001 | 25.3 | 26.1 | ... |
        | 100002 | 5001 | 1.2 | 0.8 | ... |
        
        - **tn**: Tesisat numarası
        - **bn**: Bina numarası
        - Diğer sütunlar: Aylık tüketim değerleri
        """)
