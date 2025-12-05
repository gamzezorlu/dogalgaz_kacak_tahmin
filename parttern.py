import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io

st.set_page_config(page_title="Doğalgaz Kaçak Tespit", page_icon="🔥", layout="wide")

# Başlık
st.title("🔥 Doğalgaz Kaçak Kullanım Tespit Sistemi")
st.markdown("---")

# Sidebar - Açıklamalar
with st.sidebar:
    st.header("📋 Kullanım Kılavuzu")
    st.markdown("""
    ### Excel Formatı:
    - **Abone_ID**: Abone numarası
    - **Tarife**: Isınma/Mutfak
    - **Ocak, Şubat, ... Aralık**: Aylık tüketim (m³)
    
    ### Tespit Kuralları:
    1. ❄️ Kışın Yaz Modu
    2. 📉 Ani Düşüş
    3. 🚫 Sıfır Tüketim
    4. 📊 Volatilite (Zikzak)
    5. ⚡ Baz Yük Altı
    6. 🌡️ Yaz-Kış Oranı
    7. 📏 Sabit Tüketim
    8. 📅 Yıllık Karşılaştırma
    9. 💥 Geri Dönüş Patlaması
    10. 📍 Komşu Sapması
    11. ❄️ Kış Düşük
    12. 📈 Trend Kırılması
    """)
    
    st.markdown("---")
    st.info("💡 Risk Skoru >60: Yüksek Riskli")

# Dosya yükleme
uploaded_file = st.file_uploader("📁 Excel Dosyası Yükleyin", type=['xlsx', 'xls'])

if uploaded_file is not None:
    try:
        # Excel'i oku
        df = pd.read_excel(uploaded_file)
        
        # Kolon isimlerini normalize et (boşlukları temizle, küçük harfe çevir)
        df.columns = df.columns.str.strip()
        
        st.success(f"✅ Dosya başarıyla yüklendi! {len(df)} abone analiz edilecek.")
        
        # Veri önizleme
        with st.expander("📊 Veri Önizleme"):
            st.dataframe(df.head(10))
        
        # Kolon kontrolü - Flexible ay isimleri
        required_cols = ['Abone_ID']
        month_cols_original = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 
                      'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
        
        # Alternatif ay isimleri
        month_variations = {
            'Ocak': ['ocak', 'OCAK', 'Ocak', 'January', 'JAN'],
            'Şubat': ['şubat', 'ŞUBAT', 'Şubat', 'Subat', 'February', 'FEB'],
            'Mart': ['mart', 'MART', 'Mart', 'March', 'MAR'],
            'Nisan': ['nisan', 'NİSAN', 'NISAN', 'Nisan', 'April', 'APR'],
            'Mayıs': ['mayıs', 'MAYIS', 'Mayıs', 'Mayis', 'May', 'MAY'],
            'Haziran': ['haziran', 'HAZİRAN', 'HAZIRAN', 'Haziran', 'June', 'JUN'],
            'Temmuz': ['temmuz', 'TEMMUZ', 'Temmuz', 'July', 'JUL'],
            'Ağustos': ['ağustos', 'AĞUSTOS', 'Ağustos', 'Agustos', 'August', 'AUG'],
            'Eylül': ['eylül', 'EYLÜL', 'Eylül', 'Eylul', 'September', 'SEP'],
            'Ekim': ['ekim', 'EKİM', 'EKIM', 'Ekim', 'October', 'OCT'],
            'Kasım': ['kasım', 'KASIM', 'Kasım', 'Kasim', 'November', 'NOV'],
            'Aralık': ['aralık', 'ARALIK', 'Aralık', 'Aralik', 'December', 'DEC']
        }
        
        # Excel'deki kolonları eşleştir
        month_cols = []
        missing_months = []
        
        for standard_month in month_cols_original:
            found = False
            for col in df.columns:
                if col == standard_month or col in month_variations.get(standard_month, []):
                    month_cols.append(col)
                    found = True
                    break
            
            if not found:
                missing_months.append(standard_month)
        
        # Eksik kolonları kontrol et
        if missing_months:
            st.error(f"❌ Eksik ay kolonları: {', '.join(missing_months)}")
            st.info("💡 Excel dosyanızda şu kolon isimlerinin bulunduğundan emin olun:")
            st.write(df.columns.tolist())
            st.stop()
        
        # Tarife kontrolü (yoksa varsayılan)
        if 'Tarife' not in df.columns:
            df['Tarife'] = 'Isınma'
            st.warning("⚠️ 'Tarife' kolonu bulunamadı, tüm aboneler 'Isınma' olarak varsayıldı.")
        
        # Analiz butonu
        if st.button("🚀 Analizi Başlat", type="primary"):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Sonuç dataframe'i
            results = []
            
            for idx, row in df.iterrows():
                progress_bar.progress((idx + 1) / len(df))
                status_text.text(f"Analiz ediliyor: {row['Abone_ID']} ({idx+1}/{len(df)})")
                
                # Aylık tüketim değerlerini al
                consumption = []
                for month in month_cols:
                    val = row[month]
                    if pd.isna(val):
                        consumption.append(0)
                    else:
                        try:
                            consumption.append(float(val))
                        except:
                            consumption.append(0)
                
                abone_id = row['Abone_ID']
                tarife = row.get('Tarife', 'Isınma')
                
                # İSTATİSTİKLER
                winter_months = [consumption[11], consumption[0], consumption[1]]  # Ara, Oca, Şub
                summer_months = [consumption[5], consumption[6], consumption[7]]  # Haz, Tem, Ağu
                
                winter_avg = np.mean(winter_months)
                summer_avg = np.mean(summer_months)
                winter_summer_ratio = winter_avg / summer_avg if summer_avg > 0 else 0
                
                total_consumption = sum(consumption)
                mean_consumption = np.mean(consumption)
                std_dev = np.std(consumption)
                cv = (std_dev / mean_consumption * 100) if mean_consumption > 0 else 0
                
                non_zero = [c for c in consumption if c > 0]
                max_consumption = max(consumption) if consumption else 0
                min_consumption = min(non_zero) if non_zero else 0
                volatility = max_consumption / min_consumption if min_consumption > 0 else 0
                
                zero_months = sum(1 for c in consumption if c == 0)
                low_months = sum(1 for c in consumption if 0 < c < 5)
                
                # ANİ DÜŞÜŞ SAYISI
                sudden_drops = 0
                for i in range(1, len(consumption)):
                    if consumption[i-1] > 0 and consumption[i] < consumption[i-1] * 0.3:
                        sudden_drops += 1
                
                # SABİT TÜKETİM (son 3 ay)
                last_3_months = consumption[-3:]
                last_3_std = np.std(last_3_months) if last_3_months else 0
                is_flatline = last_3_std < 5 and np.mean(last_3_months) > 0
                
                # GERİ DÖNÜŞ PATLAMASI
                if len(consumption) >= 4:
                    prev_3_avg = np.mean(consumption[-4:-1])
                    current_month = consumption[-1]
                    is_spike = (prev_3_avg < 25) and (current_month > 100)
                else:
                    is_spike = False
                
                # Z-SKORU
                z_scores = [(c - mean_consumption) / std_dev if std_dev > 0 else 0 for c in consumption]
                min_z_score = min(z_scores) if z_scores else 0
                
                # ANOMALI TESPİTİ VE SKORLAMA
                risk_score = 0
                anomalies = []
                
                # KURAL 1: Kışın Yaz Modu
                if tarife == 'Isınma' and winter_avg < 30 and summer_avg > 0:
                    if winter_avg <= summer_avg * 1.2:
                        risk_score += 20
                        anomalies.append(f"❄️ Kışın Yaz Modu: Kış ort. {winter_avg:.1f} m³, Yaz ort. {summer_avg:.1f} m³")
                
                # KURAL 2: Ani Düşüş
                if sudden_drops >= 2:
                    risk_score += 25
                    anomalies.append(f"📉 Ani Düşüş: {sudden_drops} kez %70+ düşüş tespit edildi")
                
                # KURAL 3: Sıfır Tüketim
                if zero_months > 0 and tarife == 'Isınma':
                    winter_zero = sum(1 for c in winter_months if c == 0)
                    if winter_zero > 0:
                        risk_score += 30
                        anomalies.append(f"🚫 Sıfır Tüketim: Kış aylarında {winter_zero} ay sıfır")
                    else:
                        risk_score += 15
                        anomalies.append(f"🚫 Sıfır Tüketim: {zero_months} ay sıfır")
                
                # KURAL 4: Volatilite (Zikzak)
                if volatility > 20:
                    risk_score += 10
                    anomalies.append(f"📊 Yüksek Volatilite: {volatility:.1f}x (Max/Min oranı)")
                
                # KURAL 5: Baz Yük Altı
                if low_months > 3:
                    risk_score += 15
                    anomalies.append(f"⚡ Baz Yük Altı: {low_months} ay <5 m³ tüketim")
                
                # KURAL 6: Yaz-Kış Oranı
                if tarife == 'Isınma' and 0 < winter_summer_ratio < 2.5:
                    risk_score += 20
                    anomalies.append(f"🌡️ Düşük Kış/Yaz Oranı: {winter_summer_ratio:.2f} (Normal: 5-10)")
                
                # KURAL 7: Sabit Tüketim
                if is_flatline:
                    risk_score += 15
                    anomalies.append(f"📏 Sabit Tüketim: Son 3 ay standart sapma {last_3_std:.1f} m³")
                
                # KURAL 9: Geri Dönüş Patlaması
                if is_spike:
                    risk_score += 20
                    anomalies.append(f"💥 Ani Artış: Önceki 3 ay ort. {prev_3_avg:.1f} → Bu ay {current_month:.1f} m³")
                
                # KURAL 11: Kış Düşük
                if tarife == 'Isınma':
                    winter_low_count = sum(1 for c in winter_months if c < 30)
                    if winter_low_count == 3:
                        risk_score += 30
                        anomalies.append(f"❄️ Kış Ayları Düşük: 3 kış ayının hepsi <30 m³")
                
                # KURAL 12: Trend Kırılması (Z-skoru)
                if min_z_score < -2.5:
                    risk_score += 20
                    anomalies.append(f"📈 Trend Kırılması: Minimum Z-skoru {min_z_score:.2f}")
                
                # Risk seviyesi
                if risk_score > 60:
                    risk_level = "🔴 YÜKSEK RİSK"
                elif risk_score > 30:
                    risk_level = "🟡 ORTA RİSK"
                else:
                    risk_level = "🟢 DÜŞÜK RİSK"
                
                # Sonuçları kaydet
                results.append({
                    'Abone_ID': abone_id,
                    'Tarife': tarife,
                    'Risk_Skoru': risk_score,
                    'Risk_Seviyesi': risk_level,
                    'Kış_Ortalama': round(winter_avg, 2),
                    'Yaz_Ortalama': round(summer_avg, 2),
                    'Kış_Yaz_Oranı': round(winter_summer_ratio, 2),
                    'Toplam_Tüketim': round(total_consumption, 2),
                    'Ortalama_Tüketim': round(mean_consumption, 2),
                    'Standart_Sapma': round(std_dev, 2),
                    'Volatilite': round(volatility, 2),
                    'Sıfır_Ay_Sayısı': zero_months,
                    'Düşük_Ay_Sayısı': low_months,
                    'Ani_Düşüş_Sayısı': sudden_drops,
                    'Tespit_Edilen_Anomaliler': ' | '.join(anomalies) if anomalies else 'Anomali tespit edilmedi',
                    'Anomali_Sayısı': len(anomalies)
                })
            
            # DataFrame'e çevir
            results_df = pd.DataFrame(results)
            
            # Sıralama (Risk skoruna göre)
            results_df = results_df.sort_values('Risk_Skoru', ascending=False).reset_index(drop=True)
            
            progress_bar.empty()
            status_text.empty()
            
            st.success("✅ Analiz tamamlandı!")
            
            # İSTATİSTİKLER
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                high_risk = len(results_df[results_df['Risk_Skoru'] > 60])
                st.metric("🔴 Yüksek Risk", high_risk, 
                         delta=f"%{(high_risk/len(results_df)*100):.1f}")
            
            with col2:
                medium_risk = len(results_df[(results_df['Risk_Skoru'] > 30) & (results_df['Risk_Skoru'] <= 60)])
                st.metric("🟡 Orta Risk", medium_risk,
                         delta=f"%{(medium_risk/len(results_df)*100):.1f}")
            
            with col3:
                avg_ratio_df = results_df[results_df['Kış_Yaz_Oranı'] > 0]
                avg_ratio = avg_ratio_df['Kış_Yaz_Oranı'].mean() if len(avg_ratio_df) > 0 else 0
                st.metric("🌡️ Ort. Kış/Yaz Oranı", f"{avg_ratio:.2f}",
                         delta="Normal: 5-10")
            
            with col4:
                total_anomalies = results_df['Anomali_Sayısı'].sum()
                st.metric("⚠️ Toplam Anomali", total_anomalies)
            
            st.markdown("---")
            
            # Filtreleme seçenekleri
            st.subheader("🔍 Sonuçları Filtrele")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                risk_filter = st.multiselect(
                    "Risk Seviyesi",
                    options=['🔴 YÜKSEK RİSK', '🟡 ORTA RİSK', '🟢 DÜŞÜK RİSK'],
                    default=['🔴 YÜKSEK RİSK', '🟡 ORTA RİSK']
                )
            
            with col2:
                min_score = st.slider("Minimum Risk Skoru", 0, 150, 30)
            
            with col3:
                min_anomalies = st.slider("Minimum Anomali Sayısı", 0, 10, 1)
            
            # Filtreleme uygula
            filtered_df = results_df[
                (results_df['Risk_Seviyesi'].isin(risk_filter)) &
                (results_df['Risk_Skoru'] >= min_score) &
                (results_df['Anomali_Sayısı'] >= min_anomalies)
            ]
            
            st.info(f"📊 Gösterilen abone sayısı: {len(filtered_df)} / {len(results_df)}")
            
            # Sonuçları göster
            st.dataframe(
                filtered_df[['Abone_ID', 'Risk_Skoru', 'Risk_Seviyesi', 
                            'Kış_Ortalama', 'Yaz_Ortalama', 'Kış_Yaz_Oranı',
                            'Anomali_Sayısı', 'Tespit_Edilen_Anomaliler']],
                use_container_width=True,
                height=400
            )
            
            # EXCEL İNDİRME
            st.markdown("---")
            st.subheader("📥 Rapor İndir")
            
            # Excel buffer oluştur
            output = io.BytesIO()
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Ana rapor
                filtered_df.to_excel(writer, sheet_name='Anomali Raporu', index=False)
                
                # Özet istatistikler
                summary = pd.DataFrame({
                    'Metrik': [
                        'Toplam Abone',
                        'Yüksek Riskli',
                        'Orta Riskli',
                        'Düşük Riskli',
                        'Toplam Anomali',
                        'Ortalama Risk Skoru',
                        'Ortalama Kış/Yaz Oranı'
                    ],
                    'Değer': [
                        len(results_df),
                        high_risk,
                        medium_risk,
                        len(results_df) - high_risk - medium_risk,
                        total_anomalies,
                        round(results_df['Risk_Skoru'].mean(), 2),
                        round(avg_ratio, 2)
                    ]
                })
                summary.to_excel(writer, sheet_name='Özet', index=False)
                
                # Anomali türleri istatistiği
                anomaly_types = []
                for anomalies in results_df['Tespit_Edilen_Anomaliler']:
                    if anomalies != 'Anomali tespit edilmedi':
                        anomaly_types.extend([a.split(':')[0].strip() for a in anomalies.split('|')])
                
                if anomaly_types:
                    anomaly_counts = pd.Series(anomaly_types).value_counts().reset_index()
                    anomaly_counts.columns = ['Anomali Türü', 'Tespit Sayısı']
                    anomaly_counts.to_excel(writer, sheet_name='Anomali Türleri', index=False)
            
            output.seek(0)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.download_button(
                    label="📊 Detaylı Rapor İndir (Excel)",
                    data=output,
                    file_name=f"dogalgaz_kacak_raporu_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with col2:
                # CSV olarak da indir
                csv = filtered_df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📄 Filtrelenmiş Rapor İndir (CSV)",
                    data=csv,
                    file_name=f"dogalgaz_kacak_filtrelenmiş_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            # En riskli 10 abone
            st.markdown("---")
            st.subheader("🎯 En Yüksek Riskli 10 Abone")
            
            top_10 = results_df.head(10)
            
            for idx, row in top_10.iterrows():
                with st.expander(f"#{idx+1} - Abone: {row['Abone_ID']} | Risk Skoru: {row['Risk_Skoru']} | {row['Risk_Seviyesi']}"):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Kış Ortalama", f"{row['Kış_Ortalama']:.1f} m³")
                        st.metric("Yaz Ortalama", f"{row['Yaz_Ortalama']:.1f} m³")
                    
                    with col2:
                        st.metric("Kış/Yaz Oranı", f"{row['Kış_Yaz_Oranı']:.2f}")
                        st.metric("Volatilite", f"{row['Volatilite']:.1f}x")
                    
                    with col3:
                        st.metric("Sıfır Ay", row['Sıfır_Ay_Sayısı'])
                        st.metric("Ani Düşüş", row['Ani_Düşüş_Sayısı'])
                    
                    st.markdown("**🔍 Tespit Edilen Anomaliler:**")
                    anomalies_list = row['Tespit_Edilen_Anomaliler'].split('|')
                    for anomaly in anomalies_list:
                        st.markdown(f"- {anomaly.strip()}")
    
    except Exception as e:
        st.error(f"❌ Hata oluştu: {str(e)}")
        st.exception(e)

else:
    # Örnek format göster
    st.info("👆 Lütfen yukarıdan bir Excel dosyası yükleyin")
    
    st.subheader("📋 Excel Dosya Formatı Örneği")
    
    example_df = pd.DataFrame({
        'Abone_ID': [10004494, 10011908, 10025351],
        'Tarife': ['Isınma', 'Isınma', 'Mutfak'],
        'Ocak': [165.80, 209.90, 4.63],
        'Şubat': [166.64, 168.49, 18.59],
        'Mart': [186.68, 286.03, 19.11],
        'Nisan': [72.18, 63.47, 15.29],
        'Mayıs': [55.69, 54.09, 18.73],
        'Haziran': [35.35, 22.29, 18.95],
        'Temmuz': [19.16, 9.09, 77.30],
        'Ağustos': [20.69, 1.79, 141.76],
        'Eylül': [24.07, 1.78, 145.52],
        'Ekim': [18.89, 20.82, 152.78],
        'Kasım': [293.68, 61.88, 144.13],
        'Aralık': [28.26, 76.77, 110.17]
    })
    
    st.dataframe(example_df)
    
    # Örnek dosya indir
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        example_df.to_excel(writer, index=False, sheet_name='Veri')
    buffer.seek(0)
    
    st.download_button(
        label="📥 Örnek Excel Şablonu İndir",
        data=buffer,
        file_name="dogalgaz_sablonu.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray;'>
    <p>🔥 Doğalgaz Kaçak Tespit Sistemi v1.1 | 12 Kural ile Anomali Tespiti</p>
</div>
""", unsafe_allow_html=True)
