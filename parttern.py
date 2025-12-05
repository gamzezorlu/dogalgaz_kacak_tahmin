import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io

st.set_page_config(page_title="Doğalgaz Kaçak Tespit", page_icon="🔥", layout="wide")

# Başlık
st.title("🔥 Doğalgaz Kaçak Kullanım Tespit Sistemi - Gelişmiş Pattern Analizi")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("📋 Kullanım Kılavuzu")
    st.markdown("""
    ### Excel Formatı:
    - **tn** veya **Abone_ID**: Abone numarası
    - **2021/01, 2021/02...**: Aylık tüketim (m³)
    
    ### 15 Gelişmiş Tespit Kuralı:
    1. 🚫 **Uzun Süreli Sıfır**: 6+ ay sıfır (DÜŞÜK ÖNCELİK)
    2. 💥 **Ani Patlama**: Sıfırdan yüksek tüketime geçiş (YÜKSEK ÖNCELİK)
    3. 📉 **Dramatik Düşüş**: %90+ azalma (YÜKSEK ÖNCELİK)
    4. ❄️ **Kış Anomalisi**: Kışın çok düşük tüketim (YÜKSEK ÖNCELİK)
    5. 🔄 **On-Off Pattern**: Aşırı dalgalanma (YÜKSEK ÖNCELİK)
    6. 📍 **Tek Ay İstisna**: Bir ay çok yüksek, diğerleri düşük
    7. 🎯 **Kaçak Sonrası Patlama**: Düşük periyot + ani yükselme
    8. 📊 **Aşırı Volatilite**: CV >150%
    9. 🌡️ **Ters Sezonluk**: Yazın kıştan fazla tüketim
    10. ⚡ **Mikro Tüketim**: Sürekli <5 m³
    11. 🔥 **Hayalet Tüketim**: Aralıklı çok düşük değerler
    12. 📈 **Trend Kırılması**: Z-score <-3
    13. 💤 **Uzun Süre Sessizlik**: 12+ ay sıfır (DÜŞÜK ÖNCELİK)
    14. 🎲 **Kaotik Desen**: Tahmin edilemez pattern
    15. 🔍 **Anormal Düşük Toplam**: Genel tüketim çok düşük
    
    **Not:** Uzun süre sıfır olanlar düşük öncelikli kabul edilir.
    Kaçak tespitinde aktif kullanım sırasındaki anomaliler önemlidir.
    """)
    
    st.markdown("---")
    st.info("⚠️ Risk Skoru >80: Yüksek Şüpheli")
    st.warning("📊 PDF pattern analizi ile optimize edilmiş kurallar")

# Dosya yükleme
uploaded_file = st.file_uploader("📁 Excel Dosyası Yükleyin", type=['xlsx', 'xls'])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        df.columns = df.columns.str.strip()
        
        st.success(f"✅ Dosya başarıyla yüklendi! {len(df)} abone analiz edilecek.")
        
        with st.expander("📊 Veri Önizleme"):
            st.dataframe(df.head(10))
        
        # Abone ID kolonunu bul
        abone_col = None
        bina_col = None
        
        for col in ['tesisat no', 'Tesisat No', 'TESISAT NO', 'tesisat_no', 'TesisatNo',
                    'tn', 'Abone_ID', 'abone_id', 'TN', 'ABONE_ID']:
            if col in df.columns:
                abone_col = col
                break
        
        for col in ['bina no', 'Bina No', 'BINA NO', 'bina_no', 'BinaNo', 'BINA_NO']:
            if col in df.columns:
                bina_col = col
                break
        
        if not abone_col:
            st.error("❌ 'tesisat no' veya 'tn' kolonu bulunamadı!")
            st.info("💡 Bulunan kolonlar:")
            st.write(df.columns.tolist())
            st.stop()
        
        if bina_col:
            st.success(f"✅ Bina No kolonu bulundu: '{bina_col}'")
        else:
            st.warning("⚠️ 'bina no' kolonu bulunamadı, sadece tesisat bazlı analiz yapılacak")
        
        # Ay kolonlarını bul (tarih formatında)
        month_cols = []
        for col in df.columns:
            col_str = str(col)
            # 2021/01, 2022/01 gibi formatları yakala
            if '/' in col_str and any(str(y) in col_str for y in range(2021, 2026)):
                month_cols.append(col)
        
        # Alternatif: Türkçe ay isimleri
        if len(month_cols) < 12:
            turkish_months = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
                            'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
            for month in turkish_months:
                if month in df.columns:
                    month_cols.append(month)
        
        if len(month_cols) < 12:
            st.error(f"❌ Yeterli ay kolonu bulunamadı! Bulunan: {len(month_cols)} adet")
            st.info("💡 Bulunan kolonlar:")
            st.write(df.columns.tolist())
            st.stop()
        
        # Ay kolonlarını sırala (tarih formatına göre)
        month_cols = sorted(month_cols)[:48]  # Maksimum 48 ay (4 yıl)
        
        st.info(f"📅 Analiz edilecek dönem: {month_cols[0]} → {month_cols[-1]} ({len(month_cols)} ay)")
        
        if st.button("🚀 Kaçak Analizi Başlat", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            results = []
            
            for idx, row in df.iterrows():
                progress_bar.progress((idx + 1) / len(df))
                status_text.text(f"Analiz ediliyor: {row[abone_col]} ({idx+1}/{len(df)})")
                
                # Tüketim değerlerini al
                consumption = []
                for month in month_cols:
                    val = row[month]
                    if pd.isna(val):
                        consumption.append(0)
                    else:
                        try:
                            # Virgüllü sayıları düzelt
                            if isinstance(val, str):
                                val = val.replace(',', '.')
                            consumption.append(float(val))
                        except:
                            consumption.append(0)
                
                abone_id = row[abone_col]
                bina_no = row[bina_col] if bina_col else None
                
                # İSTATİSTİKLER
                total_consumption = sum(consumption)
                mean_consumption = np.mean(consumption)
                std_dev = np.std(consumption)
                cv = (std_dev / mean_consumption * 100) if mean_consumption > 0 else 0
                
                non_zero = [c for c in consumption if c > 0]
                max_consumption = max(consumption) if consumption else 0
                min_non_zero = min(non_zero) if non_zero else 0
                
                zero_months = sum(1 for c in consumption if c == 0)
                very_low_months = sum(1 for c in consumption if 0 < c < 5)
                
                # PATTERN ANALİZİ - SADECE AKTİF TÜKETİM DÖNEMLERİ
                risk_score = 0
                anomalies = []
                
                # Sıfır olmayan ayları filtrele
                active_consumption = [c for c in consumption if c > 0]
                active_indices = [i for i, c in enumerate(consumption) if c > 0]
                
                # Eğer hiç aktif tüketim yoksa analiz yapma
                if len(active_consumption) < 3:
                    anomalies.append("ℹ️ Yeterli aktif tüketim verisi yok (3 aydan az)")
                    risk_score = 0
                    
                    results.append({
                        'Tesisat_No': abone_id,
                        'Bina_No': bina_no if bina_no else '-',
                        'Risk_Skoru': 0,
                        'Risk_Seviyesi': '⚪ ANALİZ DIŞI',
                        'Toplam_Tüketim': round(total_consumption, 2),
                        'Ortalama_Tüketim': 0,
                        'Standart_Sapma': 0,
                        'CV_%': 0,
                        'Sıfır_Ay': zero_months,
                        'Çok_Düşük_Ay': 0,
                        'Max_Ardışık_Sıfır': 0,
                        'Max_Tüketim': 0,
                        'Min_Tüketim': 0,
                        'Anomali_Sayısı': 0,
                        'Tespit_Edilen_Anomaliler': 'Yeterli aktif tüketim yok'
                    })
                    continue
                
                # Aktif dönem istatistikleri
                active_mean = np.mean(active_consumption)
                active_std = np.std(active_consumption)
                active_cv = (active_std / active_mean * 100) if active_mean > 0 else 0
                active_max = max(active_consumption)
                active_min = min(active_consumption)
                
                # KURAL 1: Dramatik Düşüş (%90+) - SADECE AKTİF DÖNEMLER ARASI
                for i in range(1, len(active_consumption)):
                    if active_consumption[i-1] > 50 and active_consumption[i] < active_consumption[i-1] * 0.1:
                        risk_score += 35
                        anomalies.append(f"📉 Dramatik Düşüş: {active_consumption[i-1]:.1f} → {active_consumption[i]:.1f} m³ (%{((1-active_consumption[i]/active_consumption[i-1])*100):.0f})")
                        break
                
                # KURAL 2: Kış Anomalisi - SADECE AKTİF KIŞ AYLARINDAKİ DÜŞÜK TÜKETİM
                winter_active = []
                summer_active = []
                
                for i in active_indices:
                    month = month_cols[i]
                    if '/12' in month or '/01' in month or '/02' in month or \
                       month in ['Aralık', 'Ocak', 'Şubat']:
                        winter_active.append(consumption[i])
                    elif '/06' in month or '/07' in month or '/08' in month or \
                         month in ['Haziran', 'Temmuz', 'Ağustos']:
                        summer_active.append(consumption[i])
                
                if len(winter_active) >= 2:
                    winter_avg = np.mean(winter_active)
                    if winter_avg < 30:
                        risk_score += 40
                        anomalies.append(f"❄️ Kış Anomalisi: Aktif kış ayları ortalaması {winter_avg:.1f} m³ (Isınma beklentisinin altında)")
                
                # KURAL 3: Ters Sezonluk - Yazın kıştan fazla tüketim
                if len(winter_active) >= 2 and len(summer_active) >= 2:
                    summer_avg = np.mean(summer_active)
                    winter_avg = np.mean(winter_active)
                    if summer_avg > winter_avg * 1.2:
                        risk_score += 30
                        anomalies.append(f"🌡️ Ters Sezonluk: Yaz ort. {summer_avg:.1f} > Kış ort. {winter_avg:.1f} m³")
                
                # KURAL 4: On-Off Pattern - SADECE AKTİF AYLAR ARASI
                transitions = 0
                for i in range(1, len(active_consumption)):
                    if (active_consumption[i-1] < 20 and active_consumption[i] > 100) or \
                       (active_consumption[i-1] > 100 and active_consumption[i] < 20):
                        transitions += 1
                
                if transitions >= 3:
                    risk_score += 30
                    anomalies.append(f"🔄 On-Off Pattern: {transitions} kez aşırı dalgalanma (aktif dönemde)")
                
                # KURAL 5: Tek Ay İstisna
                if active_max > 150 and len(active_consumption) > 3:
                    other_active = [c for c in active_consumption if c != active_max]
                    if other_active and np.mean(other_active) < 50:
                        risk_score += 25
                        anomalies.append(f"📍 Tek Ay İstisna: Max {active_max:.1f} m³, diğer aktif aylar ort. {np.mean(other_active):.1f} m³")
                
                # KURAL 6: Kaçak Sonrası Patlama
                if len(active_consumption) >= 4:
                    for i in range(3, len(active_consumption)):
                        prev_avg = np.mean(active_consumption[i-3:i])
                        if prev_avg < 40 and active_consumption[i] > 200:
                            risk_score += 40
                            anomalies.append(f"🎯 Kaçak Sonrası Patlama: Önceki 3 aktif ay ort. {prev_avg:.1f} → {active_consumption[i]:.1f} m³")
                            break
                
                # KURAL 7: Aşırı Volatilite
                if active_cv > 150:
                    risk_score += 25
                    anomalies.append(f"📊 Aşırı Volatilite: CV = {active_cv:.1f}% (aktif dönemde)")
                
                # KURAL 8: Mikro Tüketim - Çoğu aktif ay <5 m³
                micro_months = sum(1 for c in active_consumption if c < 5)
                if micro_months > len(active_consumption) * 0.5:
                    risk_score += 20
                    anomalies.append(f"⚡ Mikro Tüketim: {micro_months}/{len(active_consumption)} aktif ay <5 m³")
                
                # KURAL 9: Hayalet Tüketim
                ghost_months = sum(1 for c in active_consumption if 0.5 < c < 3)
                if ghost_months >= 4:
                    risk_score += 25
                    anomalies.append(f"🔥 Hayalet Tüketim: {ghost_months} aktif ay 0.5-3 m³ arası")
                
                # KURAL 10: Trend Kırılması - Aktif dönemde
                z_scores = [(c - active_mean) / active_std if active_std > 0 else 0 for c in active_consumption]
                min_z = min(z_scores) if z_scores else 0
                if min_z < -2.5:
                    risk_score += 25
                    anomalies.append(f"📈 Trend Kırılması: Min Z-score = {min_z:.2f} (aktif dönemde)")
                
                # KURAL 11: Kaotik Desen - Aktif dönemde
                if len(active_consumption) >= 3:
                    direction_changes = 0
                    for i in range(2, len(active_consumption)):
                        trend1 = active_consumption[i-1] - active_consumption[i-2]
                        trend2 = active_consumption[i] - active_consumption[i-1]
                        if abs(trend1) > 10 and abs(trend2) > 10:  # Anlamlı değişimler
                            if (trend1 > 0 and trend2 < 0) or (trend1 < 0 and trend2 > 0):
                                direction_changes += 1
                    
                    if direction_changes > len(active_consumption) * 0.5:
                        risk_score += 20
                        anomalies.append(f"🎲 Kaotik Desen: {direction_changes} yön değişimi (aktif dönemde)")
                
                # KURAL 12: Anormal Düşük Ortalama - Aktif dönemde
                if active_mean < 15 and len(active_consumption) >= 6:
                    risk_score += 30
                    anomalies.append(f"⚠️ Anormal Düşük Ortalama: {active_mean:.1f} m³/ay (aktif dönemde)")
                
                # Risk seviyesi
                if risk_score > 80:
                    risk_level = "🔴 ÇOK YÜKSEK ŞÜPHELİ"
                elif risk_score > 60:
                    risk_level = "🟠 YÜKSEK ŞÜPHELİ"
                elif risk_score > 40:
                    risk_level = "🟡 ORTA ŞÜPHELİ"
                else:
                    risk_level = "🟢 DÜŞÜK RİSK"
                
                results.append({
                    'Tesisat_No': abone_id,
                    'Bina_No': bina_no if bina_no else '-',
                    'Risk_Skoru': risk_score,
                    'Risk_Seviyesi': risk_level,
                    'Toplam_Tüketim': round(total_consumption, 2),
                    'Ortalama_Tüketim': round(mean_consumption, 2),
                    'Standart_Sapma': round(std_dev, 2),
                    'CV_%': round(cv, 1),
                    'Sıfır_Ay': zero_months,
                    'Çok_Düşük_Ay': very_low_months,
                    'Max_Ardışık_Sıfır': max_consecutive_zeros,
                    'Max_Tüketim': round(max_consumption, 2),
                    'Min_Tüketim': round(min_non_zero, 2) if min_non_zero > 0 else 0,
                    'Anomali_Sayısı': len(anomalies),
                    'Tespit_Edilen_Anomaliler': ' | '.join(anomalies) if anomalies else 'Anomali tespit edilmedi'
                })
            
            results_df = pd.DataFrame(results)
            results_df = results_df.sort_values('Risk_Skoru', ascending=False).reset_index(drop=True)
            
            progress_bar.empty()
            status_text.empty()
            
            st.success("✅ Analiz tamamlandı!")
            
            # İSTATİSTİKLER
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                very_high = len(results_df[results_df['Risk_Skoru'] > 80])
                st.metric("🔴 Çok Yüksek Şüpheli", very_high,
                         delta=f"%{(very_high/len(results_df)*100):.1f}")
            
            with col2:
                high_risk = len(results_df[(results_df['Risk_Skoru'] > 60) & (results_df['Risk_Skoru'] <= 80)])
                st.metric("🟠 Yüksek Şüpheli", high_risk,
                         delta=f"%{(high_risk/len(results_df)*100):.1f}")
            
            with col3:
                medium_risk = len(results_df[(results_df['Risk_Skoru'] > 40) & (results_df['Risk_Skoru'] <= 60)])
                st.metric("🟡 Orta Şüpheli", medium_risk,
                         delta=f"%{(medium_risk/len(results_df)*100):.1f}")
            
            with col4:
                total_anomalies = results_df['Anomali_Sayısı'].sum()
                st.metric("⚠️ Toplam Anomali", total_anomalies)
            
            st.markdown("---")
            
            # Filtreleme
            st.subheader("🔍 Sonuçları Filtrele")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                risk_filter = st.multiselect(
                    "Risk Seviyesi",
                    options=['🔴 ÇOK YÜKSEK ŞÜPHELİ', '🟠 YÜKSEK ŞÜPHELİ', '🟡 ORTA ŞÜPHELİ', '🟢 DÜŞÜK RİSK'],
                    default=['🔴 ÇOK YÜKSEK ŞÜPHELİ', '🟠 YÜKSEK ŞÜPHELİ']
                )
            
            with col2:
                min_score = st.slider("Minimum Risk Skoru", 0, 200, 40)
            
            with col3:
                min_anomalies = st.slider("Minimum Anomali Sayısı", 0, 10, 2)
            
            filtered_df = results_df[
                (results_df['Risk_Seviyesi'].isin(risk_filter)) &
                (results_df['Risk_Skoru'] >= min_score) &
                (results_df['Anomali_Sayısı'] >= min_anomalies)
            ]
            
            st.info(f"📊 Gösterilen abone sayısı: {len(filtered_df)} / {len(results_df)}")
            
            st.dataframe(
                filtered_df[['Tesisat_No', 'Bina_No', 'Risk_Skoru', 'Risk_Seviyesi',
                            'Toplam_Tüketim', 'Sıfır_Ay', 'Max_Ardışık_Sıfır',
                            'Anomali_Sayısı', 'Tespit_Edilen_Anomaliler']],
                use_container_width=True,
                height=500
            )
            
            # Excel İndirme
            st.markdown("---")
            st.subheader("📥 Rapor İndir")
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                filtered_df.to_excel(writer, sheet_name='Kaçak Şüpheli Aboneler', index=False)
                
                summary = pd.DataFrame({
                    'Metrik': ['Toplam Abone', 'Çok Yüksek Şüpheli', 'Yüksek Şüpheli',
                              'Orta Şüpheli', 'Düşük Risk', 'Toplam Anomali'],
                    'Değer': [len(results_df), very_high, high_risk, medium_risk,
                             len(results_df) - very_high - high_risk - medium_risk,
                             total_anomalies]
                })
                summary.to_excel(writer, sheet_name='Özet', index=False)
            
            output.seek(0)
            
            st.download_button(
                label="📊 Kaçak Şüpheli Aboneler Raporu İndir (Excel)",
                data=output,
                file_name=f"kacak_supheli_raporu_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            # En şüpheli 20 abone
            st.markdown("---")
            st.subheader("🎯 En Şüpheli 20 Abone")
            
            top_20 = results_df.head(20)
            
            for idx, row in top_20.iterrows():
                with st.expander(f"#{idx+1} - Tesisat: {row['Tesisat_No']} | Bina: {row['Bina_No']} | Risk: {row['Risk_Skoru']} | {row['Risk_Seviyesi']}"):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Toplam Tüketim", f"{row['Toplam_Tüketim']:.1f} m³")
                        st.metric("Sıfır Ay", row['Sıfır_Ay'])
                    
                    with col2:
                        st.metric("Max Ardışık Sıfır", row['Max_Ardışık_Sıfır'])
                        st.metric("CV %", f"{row['CV_%']:.1f}")
                    
                    with col3:
                        st.metric("Max Tüketim", f"{row['Max_Tüketim']:.1f} m³")
                        st.metric("Anomali Sayısı", row['Anomali_Sayısı'])
                    
                    st.markdown("**🔍 Tespit Edilen Anomaliler:**")
                    for anomaly in row['Tespit_Edilen_Anomaliler'].split('|'):
                        st.markdown(f"- {anomaly.strip()}")
    
    except Exception as e:
        st.error(f"❌ Hata oluştu: {str(e)}")
        st.exception(e)

else:
    st.info("👆 Lütfen yukarıdan bir Excel dosyası yükleyin")
    
    st.subheader("📋 Excel Dosya Formatı Örneği")
    
    example_df = pd.DataFrame({
        'tesisat no': [10004494, 10011908, 10025351],
        'bina no': ['A101', 'B205', 'C310'],
        '2021/01': [165.80, 209.90, 4.63],
        '2021/02': [166.64, 168.49, 18.59],
        '2021/03': [186.68, 286.03, 19.11],
        '2021/04': [72.18, 63.47, 15.29],
        '2021/05': [55.69, 54.09, 18.73],
        '2021/06': [35.35, 22.29, 18.95]
    })
    
    st.dataframe(example_df)
    
    st.markdown("""
    ### 📝 Excel Formatı Gereksinimleri:
    - **tesisat no**: Tesisat numarası (zorunlu)
    - **bina no**: Bina numarası (opsiyonel)
    - **2021/01, 2021/02, ...**: Aylık tüketim değerleri
    - Virgüllü sayılar desteklenir (örn: 165,80)
    - Maksimum 48 ay (4 yıl) analiz edilebilir
    """)

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray;'>
    <p>🔥 Doğalgaz Kaçak Kullanım Tespit Sistemi v2.0 | PDF Pattern Analizi</p>
    <p>15 Gelişmiş Kural ile Kaçak Şüphesi Tespiti</p>
</div>
""", unsafe_allow_html=True)
