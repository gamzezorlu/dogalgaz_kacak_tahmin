import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from io import BytesIO
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment

st.set_page_config(page_title="Doğalgaz Kaçak Tespit", layout="wide", page_icon="🔥")

st.title("🔥 Doğalgaz Kaçak Kullanım Tespit Sistemi")
st.markdown("### Akıllı Anomali Tespiti")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("⚙️ Tespit Kriterleri")
    
    st.markdown("### 🎯 Temel Parametreler")
    
    ani_dusus_esigi = st.slider("Ani Düşüş (%)", 60, 95, 75, 5)
    min_normal_tuketim = st.number_input("Min Normal Tüketim", 10, 50, 20)
    bina_fark_esigi = st.slider("Bina Fark Eşiği (%)", 50, 90, 65, 5)
    min_dusuk_ay = st.slider("Min Düşük Tüketim Süresi (Ay)", 3, 8, 4)
    min_bina_daire = st.number_input("Min Bina Daire Sayısı", 2, 10, 3)
    
    st.markdown("---")
    st.markdown("### ✅ Kaçak Kriterleri")
    st.markdown("""
    **Aşağıdakilerden EN AZ 2'si olmalı:**
    
    1. **Bina Anomalisi**: 4+ ay binadan %65+ düşük
    2. **Ani Düşüş**: 2+ kez %75+ düşüş  
    3. **Sürekli Düşük**: 4+ ay <20 birim
    4. **Sıfır Dönem**: 3+ ay sıfır tüketim
    
    **+ Minimum Risk Puanı: 80**
    """)

uploaded_file = st.file_uploader("📁 Excel Dosyası Yükleyin", type=['xlsx', 'xls'])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        df.columns = df.columns.str.strip()
        
        ay_cols = [col for col in df.columns if col not in ['tn', 'bn']]
        
        for col in ay_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        st.success(f"✅ {len(df)} tesisat yüklendi ({len(ay_cols)} ay)")
        st.markdown("---")
        
        with st.spinner("🔍 Detaylı analiz yapılıyor..."):
            
            kariddat_list = []
            
            for idx, row in df.iterrows():
                tn = row['tn']
                bn = row['bn']
                tuketim = row[ay_cols].values
                
                # Bina kontrolü
                bina_df = df[df['bn'] == bn]
                if len(bina_df) < min_bina_daire:
                    continue
                
                bina_ort = bina_df[ay_cols].mean()
                
                # KRİTER 1: Bina Anomalisi
                bina_dusuk_aylar = []
                for i, ay in enumerate(ay_cols):
                    b_ort = bina_ort[ay]
                    t_val = tuketim[i]
                    
                    if b_ort > min_normal_tuketim:
                        fark_pct = ((b_ort - t_val) / b_ort) * 100
                        if fark_pct > bina_fark_esigi:
                            bina_dusuk_aylar.append({
                                'ay': ay,
                                'tuketim': t_val,
                                'bina_ort': b_ort,
                                'fark': fark_pct
                            })
                
                kriter1 = len(bina_dusuk_aylar) >= 4
                
                # KRİTER 2: Ani Düşüş
                ani_dusus_list = []
                for i in range(1, len(tuketim)):
                    onceki = tuketim[i-1]
                    simdiki = tuketim[i]
                    
                    if onceki > min_normal_tuketim:
                        dusus_pct = ((onceki - simdiki) / onceki) * 100
                        if dusus_pct > ani_dusus_esigi:
                            ani_dusus_list.append({
                                'ay': ay_cols[i],
                                'onceki': onceki,
                                'simdiki': simdiki,
                                'dusus': dusus_pct
                            })
                
                kriter2 = len(ani_dusus_list) >= 2
                
                # KRİTER 3: Sürekli Düşük Tüketim
                dusuk_seri = 0
                max_dusuk_seri = 0
                for val in tuketim:
                    if val < min_normal_tuketim:
                        dusuk_seri += 1
                        max_dusuk_seri = max(max_dusuk_seri, dusuk_seri)
                    else:
                        dusuk_seri = 0
                
                kriter3 = max_dusuk_seri >= min_dusuk_ay
                
                # KRİTER 4: Sıfır Dönem
                sifir_seri = 0
                max_sifir_seri = 0
                for val in tuketim:
                    if val == 0:
                        sifir_seri += 1
                        max_sifir_seri = max(max_sifir_seri, sifir_seri)
                    else:
                        sifir_seri = 0
                
                kriter4 = max_sifir_seri >= 3
                
                # Kriterleri say
                kriter_sayisi = sum([kriter1, kriter2, kriter3, kriter4])
                
                # Risk puanı hesapla
                risk_puan = 0
                if kriter1:
                    risk_puan += len(bina_dusuk_aylar) * 15
                if kriter2:
                    risk_puan += len(ani_dusus_list) * 20
                if kriter3:
                    risk_puan += max_dusuk_seri * 10
                if kriter4:
                    risk_puan += max_sifir_seri * 12
                
                # KARAR: En az 2 kriter VE 80+ puan
                if kriter_sayisi >= 2 and risk_puan >= 80:
                    
                    # Sebepler
                    sebepler = []
                    if kriter1:
                        sebepler.append(f"🏢 {len(bina_dusuk_aylar)} ay binadan %{bina_fark_esigi}+ düşük")
                    if kriter2:
                        sebepler.append(f"📉 {len(ani_dusus_list)} kez %{ani_dusus_esigi}+ ani düşüş")
                    if kriter3:
                        sebepler.append(f"⬇️ {max_dusuk_seri} ay sürekli düşük tüketim")
                    if kriter4:
                        sebepler.append(f"⭕ {max_sifir_seri} ay sıfır tüketim")
                    
                    # Ortalamalar
                    pozitif_tuketim = tuketim[tuketim > 0]
                    ort_tuketim = np.mean(pozitif_tuketim) if len(pozitif_tuketim) > 0 else 0
                    
                    kariddat_list.append({
                        'tn': tn,
                        'bn': bn,
                        'risk_puan': risk_puan,
                        'kriter_sayisi': kriter_sayisi,
                        'sebepler': sebepler,
                        'bina_daire': len(bina_df),
                        'ort_tuketim': ort_tuketim,
                        'bina_ort_genel': bina_ort.mean(),
                        'bina_anomali': bina_dusuk_aylar,
                        'ani_dusus': ani_dusus_list,
                        'max_dusuk_seri': max_dusuk_seri if kriter3 else 0,
                        'max_sifir_seri': max_sifir_seri if kriter4 else 0
                    })
            
            # Sırala
            kariddat_list.sort(key=lambda x: x['risk_puan'], reverse=True)
        
        # Sonuçlar
        st.success(f"✅ Analiz tamamlandı!")
        st.markdown("---")
        st.header("📊 Tespit Sonuçları")
        
        if kariddat_list:
            # Risk kategorileri
            kritik = [k for k in kariddat_list if k['risk_puan'] >= 150]
            yuksek = [k for k in kariddat_list if 100 <= k['risk_puan'] < 150]
            orta = [k for k in kariddat_list if 80 <= k['risk_puan'] < 100]
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("🚨 Toplam Şüpheli", len(kariddat_list))
            with col2:
                st.metric("🔴 Kritik (150+)", len(kritik))
            with col3:
                st.metric("🟠 Yüksek (100-149)", len(yuksek))
            with col4:
                st.metric("🟡 Orta (80-99)", len(orta))
            
            st.markdown("---")
            
            # Filtre
            st.subheader("🔍 Şüpheli Tesisatlar")
            risk_filter = st.multiselect(
                "Risk Seviyesi",
                ["Kritik (150+)", "Yüksek (100-149)", "Orta (80-99)"],
                default=["Kritik (150+)", "Yüksek (100-149)"]
            )
            
            filtered = []
            if "Kritik (150+)" in risk_filter:
                filtered.extend(kritik)
            if "Yüksek (100-149)" in risk_filter:
                filtered.extend(yuksek)
            if "Orta (80-99)" in risk_filter:
                filtered.extend(orta)
            
            filtered.sort(key=lambda x: x['risk_puan'], reverse=True)
            
            st.info(f"📋 Gösterilen: {len(filtered)} tesisat")
            
            for i, item in enumerate(filtered[:50], 1):
                
                # Risk rengi
                if item['risk_puan'] >= 150:
                    emoji = "🔴"
                    risk_label = "KRİTİK"
                elif item['risk_puan'] >= 100:
                    emoji = "🟠"
                    risk_label = "YÜKSEK"
                else:
                    emoji = "🟡"
                    risk_label = "ORTA"
                
                with st.expander(f"{i}. {emoji} Tesisat: {item['tn']} | Bina: {item['bn']} | Puan: {item['risk_puan']} ({risk_label})"):
                    
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        # Grafik
                        t_data = df[df['tn'] == item['tn']][ay_cols].values[0]
                        b_data = df[df['bn'] == item['bn']][ay_cols].mean().values
                        
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=ay_cols, y=t_data,
                            name='Tesisat',
                            mode='lines+markers',
                            line=dict(color='red', width=3),
                            marker=dict(size=8)
                        ))
                        fig.add_trace(go.Scatter(
                            x=ay_cols, y=b_data,
                            name=f'Bina Ort. ({item["bina_daire"]} daire)',
                            mode='lines',
                            line=dict(color='blue', width=2, dash='dash')
                        ))
                        
                        fig.update_layout(
                            title=f'Tesisat {item["tn"]} Tüketim Analizi',
                            height=300,
                            hovermode='x unified'
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        st.markdown("### 📋 Tespit Detayları")
                        st.markdown(f"**Kriter Sayısı:** {item['kriter_sayisi']}/4")
                        st.markdown(f"**Risk Puanı:** {item['risk_puan']}")
                        st.markdown("")
                        
                        for sebep in item['sebepler']:
                            st.markdown(sebep)
                        
                        st.markdown("---")
                        st.markdown("### 📊 İstatistikler")
                        st.markdown(f"**Ort. Tüketim:** {item['ort_tuketim']:.1f}")
                        st.markdown(f"**Bina Ort.:** {item['bina_ort_genel']:.1f}")
                        if item['bina_ort_genel'] > 0:
                            fark = ((item['bina_ort_genel'] - item['ort_tuketim']) / item['bina_ort_genel']) * 100
                            st.markdown(f"**Fark:** %{fark:.1f} düşük")
                    
                    # Detaylı bulgular
                    if item['bina_anomali'] or item['ani_dusus']:
                        st.markdown("---")
                        st.markdown("### 🔎 Detaylı Bulgular")
                        
                        tab1, tab2 = st.tabs(["Bina Anomalisi", "Ani Düşüşler"])
                        
                        with tab1:
                            if item['bina_anomali']:
                                rows = []
                                for b in item['bina_anomali'][:8]:
                                    rows.append({
                                        'Ay': b['ay'],
                                        'Tüketim': f"{b['tuketim']:.1f}",
                                        'Bina Ort.': f"{b['bina_ort']:.1f}",
                                        'Fark': f"%{b['fark']:.1f}"
                                    })
                                st.dataframe(pd.DataFrame(rows), use_container_width=True)
                        
                        with tab2:
                            if item['ani_dusus']:
                                rows = []
                                for a in item['ani_dusus'][:8]:
                                    rows.append({
                                        'Ay': a['ay'],
                                        'Önceki': f"{a['onceki']:.1f}",
                                        'Sonraki': f"{a['simdiki']:.1f}",
                                        'Düşüş': f"%{a['dusus']:.1f}"
                                    })
                                st.dataframe(pd.DataFrame(rows), use_container_width=True)
            
            # Excel
            st.markdown("---")
            st.subheader("📥 Excel Raporu")
            
            def create_excel(kariddat_list, df, ay_cols):
                output = BytesIO()
                
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    rows = []
                    for k in kariddat_list:
                        t_row = df[df['tn'] == k['tn']].iloc[0]
                        
                        row = {
                            'Tesisat No': k['tn'],
                            'Bina No': k['bn'],
                            'Risk Puanı': k['risk_puan'],
                            'Kriter Sayısı': k['kriter_sayisi'],
                            'Bina Daire': k['bina_daire'],
                            'Ort Tüketim': round(k['ort_tuketim'], 2),
                            'Bina Ort': round(k['bina_ort_genel'], 2),
                            'Tespit Sebepleri': ' | '.join(k['sebepler'])
                        }
                        
                        for ay in ay_cols:
                            row[ay] = t_row[ay]
                        
                        rows.append(row)
                    
                    pd.DataFrame(rows).to_excel(writer, sheet_name='Şüpheli Tesisatlar', index=False)
                
                output.seek(0)
                wb = openpyxl.load_workbook(output)
                ws = wb.active
                
                # Stil
                header_fill = PatternFill(start_color='1a237e', end_color='1a237e', fill_type='solid')
                for cell in ws[1]:
                    cell.fill = header_fill
                    cell.font = Font(color='FFFFFF', bold=True)
                    cell.alignment = Alignment(horizontal='center')
                
                # Renklendirme
                for row in range(2, ws.max_row + 1):
                    puan = ws.cell(row=row, column=3).value
                    if puan >= 150:
                        fill = PatternFill(start_color='ffcdd2', end_color='ffcdd2', fill_type='solid')
                    elif puan >= 100:
                        fill = PatternFill(start_color='ffe0b2', end_color='ffe0b2', fill_type='solid')
                    else:
                        fill = PatternFill(start_color='fff9c4', end_color='fff9c4', fill_type='solid')
                    
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).fill = fill
                
                ws.column_dimensions['A'].width = 15
                ws.column_dimensions['H'].width = 50
                
                output2 = BytesIO()
                wb.save(output2)
                output2.seek(0)
                return output2.getvalue()
            
            excel_data = create_excel(kariddat_list, df, ay_cols)
            st.download_button(
                "📊 Excel Raporu İndir",
                data=excel_data,
                file_name=f"kacak_raporu_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        else:
            st.success("✅ Kriterlere uyan şüpheli tesisat bulunamadı!")
            st.info("💡 Parametreleri ayarlayarak daha fazla sonuç görebilirsiniz.")
    
    except Exception as e:
        st.error(f"❌ Hata: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

else:
    st.info("👆 Excel dosyanızı yükleyin")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### ✅ Tespit Mantığı")
        st.markdown("""
        **ZORUNLU ŞARTLAR:**
        - En az 2 kriter sağlanmalı
        - Minimum 80 risk puanı
        - En az 3 daire olan binalar
        
        **4 KRİTER:**
        1. Bina Anomalisi (4+ ay)
        2. Ani Düşüş (2+ kez)
        3. Sürekli Düşük (4+ ay)
        4. Sıfır Dönem (3+ ay)
        """)
    
    with col2:
        st.markdown("### 📝 Dosya Formatı")
        st.markdown("""
        | tn | bn | 2023/07 | 2023/08 | ... |
        |----|----|---------|---------| --- |
        | 100001 | 5001 | 25.3 | 26.1 | ... |
        """)
