import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import warnings
from io import BytesIO

warnings.filterwarnings('ignore')

# -------------------- Sayfa konfigürasyonu --------------------
st.set_page_config(
    page_title="Doğalgaz Tüketim Anomali Tespit",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 Doğalgaz Tüketim Anomali Tespit Sistemi")
st.markdown("---")

# -------------------- Yan panel - Dosya yükleme --------------------
st.sidebar.header("📁 Dosya Yükleme")
uploaded_file = st.sidebar.file_uploader(
    "CSV veya Excel dosyası seçin",
    type=['csv', 'xlsx', 'xls'],
    help="Tesisat numarası, bina numarası ve aylık tüketim verilerini içeren dosya"
)

# -------------------- Parametreler --------------------
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

# -------------------- Yardımcılar --------------------
def load_data(file):
    """Dosyayı yükle ve temizle"""
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, encoding='utf-8')
        else:
            df = pd.read_excel(file)
        df.columns = df.columns.str.strip()
        return df
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(file, encoding='latin1')
            df.columns = df.columns.str.strip()
            return df
        except Exception as e:
            st.error(f"Dosya yükleme hatası: {str(e)}")
            return None
    except Exception as e:
        st.error(f"Dosya yükleme hatası: {str(e)}")
        return None

def detect_data_format(df):
    """Veri formatını tespit et"""
    columns = [col.lower().strip() for col in df.columns]
    raw_indicators = ['belge tarihi', 'tüketim noktası', 'bağlantı nesnesi', 'sm3']
    pivot_indicators = ['tesisat', 'bina']
    raw_score = sum(1 for indicator in raw_indicators if any(indicator in col for col in columns))
    pivot_score = sum(1 for indicator in pivot_indicators if any(indicator in col for col in columns))
    date_format_score = sum(
        1 for col in df.columns
        if isinstance(col, str) and '/' in col and len(col.split('/')) == 2
    )
    if raw_score >= 3:
        return 'raw'
    elif pivot_score >= 1 or date_format_score >= 3:
        return 'pivot'
    else:
        return 'unknown'

def _safe_sort_date_cols(cols):
    def keyf(x):
        try:
            y, m = x.split('/')
            return (int(y), int(m))
        except Exception:
            return (9999, 99)
    return sorted(cols, key=keyf)

def convert_raw_to_pivot(df):
    """Raw veriyi pivot formata dönüştür - Fixed version"""
    try:
        # Kolon isimlerini normalize et
        column_mapping = {}
        for col in df.columns:
            col_lower = str(col).lower().strip()
            if 'belge tarihi' in col_lower or col_lower == 'tarih':
                column_mapping[col] = 'belge_tarihi'
            elif 'tüketim noktası' in col_lower or 'tesisat' in col_lower:
                column_mapping[col] = 'tesisat_no'
            elif 'bağlantı nesnesi' in col_lower or 'bina' in col_lower:
                column_mapping[col] = 'bina_no'
            elif 'sm3' in col_lower or 'tüketim' in col_lower:
                column_mapping[col] = 'tuketim'

        df_renamed = df.rename(columns=column_mapping)

        # Gerekli kolon kontrolü
        required = ['belge_tarihi', 'tesisat_no', 'bina_no', 'tuketim']
        missing = [c for c in required if c not in df_renamed.columns]
        if missing:
            st.error(f"Eksik kolonlar: {missing}")
            st.info(f"Mevcut kolonlar: {list(df_renamed.columns)}")
            return None

        # Veri temizleme ve tip dönüşümleri
        df_clean = df_renamed.copy()
        
        # Tarih sütununu temizle
        df_clean['belge_tarihi'] = pd.to_datetime(
            df_clean['belge_tarihi'], errors='coerce', dayfirst=True
        )
        
        # Tüketim değerlerini sayısal yap
        df_clean['tuketim'] = pd.to_numeric(
            df_clean['tuketim'], errors='coerce'
        )
        
        # String sütunları temizle
        df_clean['tesisat_no'] = df_clean['tesisat_no'].astype(str).str.strip()
        df_clean['bina_no'] = df_clean['bina_no'].astype(str).str.strip()
        
        # Geçersiz kayıtları temizle
        df_clean = df_clean.dropna(subset=['belge_tarihi', 'tesisat_no', 'bina_no'])
        df_clean['tuketim'] = df_clean['tuketim'].fillna(0)
        
        # Yıl/ay sütunu oluştur
        df_clean['yil_ay'] = df_clean['belge_tarihi'].dt.strftime('%Y/%m')
        
        # Boş kayıtları temizle
        df_clean = df_clean[
            (df_clean['tesisat_no'] != 'nan') & 
            (df_clean['bina_no'] != 'nan') & 
            (df_clean['yil_ay'].notna())
        ]
        
        if df_clean.empty:
            st.error("Temizleme sonrası veri kalmadı!")
            return None
        
        # Veriyi grupla ve topla
        grouped_df = df_clean.groupby(
            ['tesisat_no', 'bina_no', 'yil_ay'], as_index=False
        )['tuketim'].sum()
        
        # Manuel pivot işlemi (pivot_table problemi için)
        pivot_data = []
        
        # Tüm benzersiz tarih değerlerini al
        all_dates = sorted(grouped_df['yil_ay'].unique())
        
        # Her tesisat-bina çifti için bir satır oluştur
        for (tesisat, bina), group in grouped_df.groupby(['tesisat_no', 'bina_no']):
            row_data = {'tesisat_no': tesisat, 'bina_no': bina}
            
            # Her tarih için tüketim değerini ekle
            for date in all_dates:
                date_data = group[group['yil_ay'] == date]['tuketim']
                row_data[date] = date_data.iloc[0] if not date_data.empty else 0
            
            pivot_data.append(row_data)
        
        # DataFrame'e dönüştür
        final_df = pd.DataFrame(pivot_data)
        
        # Tarih sütunlarını sırala
        date_cols = [c for c in final_df.columns if c not in ['tesisat_no', 'bina_no']]
        date_cols = _safe_sort_date_cols(date_cols)
        final_df = final_df[['tesisat_no', 'bina_no'] + date_cols]
        
        return final_df

    except Exception as e:
        st.error(f"Veri dönüştürme hatası: {str(e)}")
        st.info("Hata detayları için debug bilgileri:")
        if 'df_clean' in locals():
            st.write(f"Temizlenmiş veri boyutu: {df_clean.shape}")
            st.write(f"Benzersiz yil_ay değerleri: {df_clean['yil_ay'].nunique()}")
            st.write(f"Benzersiz tesisat sayısı: {df_clean['tesisat_no'].nunique()}")
        return None

def parse_date_columns(df):
    """Tarih sütunlarını (YYYY/MM) tespit et ve sırala"""
    date_columns = []
    other_columns = []
    for col in df.columns:
        if isinstance(col, str) and '/' in col:
            parts = col.split('/')
            if len(parts) == 2 and len(parts[0]) == 4:
                try:
                    int(parts[0]); int(parts[1])
                    date_columns.append(col)
                    continue
                except Exception:
                    pass
        other_columns.append(col)
    date_columns = _safe_sort_date_cols(date_columns)
    return date_columns, other_columns

def get_season(month):
    """Ayı mevsime göre kategorize et"""
    if month in [12, 1, 2]:
        return "Kış"
    elif month in [3, 4, 5]:
        return "İlkbahar"
    elif month in [6, 7, 8]:
        return "Yaz"
    else:
        return "Sonbahar"

def analyze_consumption_patterns(df, date_columns, tesisat_col, bina_col):
    """Tüketim paternlerini analiz et"""
    results = []

    for _, row in df.iterrows():
        tesisat_no = row[tesisat_col]
        bina_no = row[bina_col]

        # Aylık tüketim verilerini al
        consumption_data = []
        for date_col in date_columns:
            try:
                value = row[date_col]
                if pd.notna(value) and value != '':
                    year, month = date_col.split('/')
                    consumption_data.append({
                        'year': int(year),
                        'month': int(month),
                        'consumption': float(value) if value != 0 else 0,
                        'season': get_season(int(month)),
                        'date_str': date_col
                    })
            except Exception:
                continue

        if not consumption_data:
            continue

        cons_df = pd.DataFrame(consumption_data).sort_values(['year', 'month'])

        # Mevsimsel ortalamalar (sıfır olmayan)
        nonzero = cons_df[cons_df['consumption'] > 0]
        seasonal_avg = nonzero.groupby('season')['consumption'].mean() if not nonzero.empty else pd.Series(dtype=float)

        kis_tuketim = float(seasonal_avg.get('Kış', 0) or 0)
        yaz_tuketim = float(seasonal_avg.get('Yaz', 0) or 0)

        anomalies = []

        # 1) Kış düşük tüketim
        if 0 < kis_tuketim < kis_tuketim_esigi:
            anomalies.append(f"Kış ayı düşük tüketim: {kis_tuketim:.1f} m³/ay")

        # 2) Kış-yaz farkı az
        if kis_tuketim > 0 and yaz_tuketim > 0:
            if abs(kis_tuketim - yaz_tuketim) < 10:
                anomalies.append(f"Kış-yaz tüketim farkı az: Kış {kis_tuketim:.1f}, Yaz {yaz_tuketim:.1f}")

        # 3) Toplam çok düşük
        total_consumption = cons_df['consumption'].sum()
        if total_consumption < 100:
            anomalies.append(f"Toplam tüketim çok düşük: {total_consumption:.1f} m³")

        # 4) Çok fazla sıfır
        zero_months = int((cons_df['consumption'] == 0).sum())
        if zero_months > 6:
            anomalies.append(f"Çok fazla sıfır tüketim: {zero_months} ay")

        # 5) Kış aylarında ani düşüş
        kis_aylari = cons_df[cons_df['season'] == 'Kış'].copy()
        if len(kis_aylari) >= 4:
            kis_yillik = kis_aylari.groupby('year')['consumption'].mean()
            yillik_ort = kis_yillik[kis_yillik > 0]
            if len(yillik_ort) >= 2:
                yillar = sorted(yillik_ort.index)
                for i in range(1, len(yillar)):
                    oy, my = yillar[i-1], yillar[i]
                    onceki, mevcut = yillik_ort[oy], yillik_ort[my]
                    if (onceki >= min_onceki_kis_tuketim and
                        mevcut < onceki * (1 - ani_dusus_orani/100)):
                        dus = ((onceki - mevcut) / onceki) * 100
                        anomalies.append(
                            f"Ani kış düşüşü: {oy} ({onceki:.1f}) → {my} ({mevcut:.1f}), %{dus:.1f} düşüş"
                        )

                if len(yillar) >= 2:
                    oy, my = yillar[-2], yillar[-1]
                    onceki, mevcut = yillik_ort[oy], yillik_ort[my]
                    if (onceki >= min_onceki_kis_tuketim and
                        mevcut < onceki * (1 - ani_dusus_orani/100)):
                        dus = ((onceki - mevcut) / onceki) * 100
                        anomalies.append(f"Son yıl ani düşüş: {oy} → {my}, %{dus:.1f} düşüş")

        # 6) Bina ortalaması karşılaştırma
        bina_tesisatlari = df[df[bina_col] == bina_no]
        if len(bina_tesisatlari) > 1:
            bina_tuketimleri = []
            for _, br in bina_tesisatlari.iterrows():
                vals = []
                for dc in date_columns:
                    v = br.get(dc, np.nan)
                    if pd.notna(v) and float(v) > 0:
                        vals.append(float(v))
                if vals:
                    bina_tuketimleri.append(np.mean(vals))

            if len(bina_tuketimleri) > 1:
                bina_ort = float(np.mean(bina_tuketimleri))
                mevcut_ort = float(nonzero['consumption'].mean()) if not nonzero.empty else 0
                if mevcut_ort > 0 and mevcut_ort < bina_ort * (1 - bina_ort_dusuk_oran/100):
                    anomalies.append(f"Bina ortalamasından %{bina_ort_dusuk_oran} düşük: {mevcut_ort:.1f} vs {bina_ort:.1f}")

        # Kış trend etiketi
        kis_trend = "Stabil"
        if len(kis_aylari) >= 4:
            kis_yillik = kis_aylari.groupby('year')['consumption'].mean()
            yillik_ort = kis_yillik[kis_yillik > 0]
            if len(yillik_ort) >= 2:
                yillar = sorted(yillik_ort.index)
                ilk_yil = yillik_ort[yillar[0]]
                son_yil = yillik_ort[yillar[-1]]
                if son_yil < ilk_yil * 0.5:
                    kis_trend = "Şiddetli Düşüş"
                elif son_yil < ilk_yil * 0.7:
                    kis_trend = "Orta Düşüş"
                elif son_yil > ilk_yil * 1.5:
                    kis_trend = "Artış"

        results.append({
            'tesisat_no': tesisat_no,
            'bina_no': bina_no,
            'kis_tuketim': kis_tuketim,
            'yaz_tuketim': yaz_tuketim,
            'toplam_tuketim': total_consumption,
            'ortalama_tuketim': float(nonzero['consumption'].mean()) if not nonzero.empty else 0,
            'kis_trend': kis_trend,
            'anomali_sayisi': len(anomalies),
            'anomaliler': '; '.join(anomalies) if anomalies else 'Normal',
            'suspicion_level': 'Şüpheli' if anomalies else 'Normal'
        })

    return pd.DataFrame(results)

def create_visualizations(results_df, original_df, date_columns):
    """Görselleştirmeler oluştur"""

    # 1) Anomali dağılımı
    fig1 = px.histogram(
        results_df,
        x='anomali_sayisi',
        title="Anomali Sayısı Dağılımı",
        color_discrete_sequence=['#FF6B6B']
    )
    st.plotly_chart(fig1, use_container_width=True)

    # 2) Şüpheli vs Normal
    suspicion_counts = results_df['suspicion_level'].value_counts()
    fig2 = px.pie(
        values=suspicion_counts.values,
        names=suspicion_counts.index,
        title="Şüpheli vs Normal Tesisatlar",
        color_discrete_map={'Şüpheli': '#FF6B6B', 'Normal': '#4ECDC4'}
    )
    st.plotly_chart(fig2, use_container_width=True)

    # 3) Kış Trend Analizi
    trend_counts = results_df['kis_trend'].value_counts()
    fig3 = px.bar(
        x=trend_counts.index,
        y=trend_counts.values,
        title="Kış Ayı Tüketim Trend Analizi",
        color=trend_counts.values,
        color_continuous_scale='Reds'
    )
    fig3.update_layout(showlegend=False)
    st.plotly_chart(fig3, use_container_width=True)

    # 4) Kış vs Yaz
    fig4 = px.scatter(
        results_df,
        x='yaz_tuketim',
        y='kis_tuketim',
        color='suspicion_level',
        size='anomali_sayisi',
        title="Kış vs Yaz Tüketim Karşılaştırması",
        labels={'yaz_tuketim': 'Yaz Tüketimi (m³)', 'kis_tuketim': 'Kış Tüketimi (m³)'},
        color_discrete_map={'Şüpheli': '#FF6B6B', 'Normal': '#4ECDC4'},
        hover_data=['kis_trend']
    )

    max_val = max(float(results_df['yaz_tuketim'].max() or 0),
                  float(results_df['kis_tuketim'].max() or 0))
    if max_val > 0:
        fig4.add_trace(go.Scatter(
            x=[0, max_val],
            y=[0, max_val],
            mode='lines',
            name='Eşit Tüketim Çizgisi',
            line=dict(dash='dash', color='gray')
        ))
    st.plotly_chart(fig4, use_container_width=True)

    # 5) Trend x Durum
    trend_anomali = results_df.groupby(['kis_trend', 'suspicion_level']).size().reset_index(name='count')
    fig5 = px.bar(
        trend_anomali,
        x='kis_trend',
        y='count',
        color='suspicion_level',
        title="Trend Bazında Anomali Dağılımı",
        color_discrete_map={'Şüpheli': '#FF6B6B', 'Normal': '#4ECDC4'}
    )
    st.plotly_chart(fig5, use_container_width=True)

# -------------------- Ana uygulama --------------------
if uploaded_file is not None:
    df = load_data(uploaded_file)

    if df is not None:
        st.success("✅ Dosya başarıyla yüklendi!")

        data_format = detect_data_format(df)

        if data_format == 'raw':
            st.info("🔄 Raw veri formatı tespit edildi. Pivot formata dönüştürülüyor...")
            df_pivot = convert_raw_to_pivot(df)

            if df_pivot is not None:
                st.success("✅ Veri başarıyla pivot formata dönüştürüldü!")
                c1, c2 = st.columns(2)
                with c1: st.metric("Orijinal Satır Sayısı", len(df))
                with c2: st.metric("Pivot Sonrası Tesisat Sayısı", len(df_pivot))
                df = df_pivot
            else:
                st.error("❌ Veri dönüştürme başarısız!")
                st.stop()

        elif data_format == 'pivot':
            st.success("✅ Pivot veri formatı tespit edildi!")
        else:
            st.warning("⚠️ Veri formatı tanınamadı. Manuel sütun seçimi yapmanız gerekebilir.")

        # Veri önizleme
        st.subheader("📊 Veri Önizleme")
        st.dataframe(df.head())

        # Sütun seçimi
        st.subheader("🔧 Sütun Seçimi")
        date_columns, other_columns = parse_date_columns(df)

        c1, c2 = st.columns(2)
        with c1:
            tesisat_col = st.selectbox(
                "Tesisat Numarası Sütunu",
                options=other_columns,
                help="Tesisat numarasını içeren sütunu seçin"
            )
        with c2:
            bina_col = st.selectbox(
                "Bina Numarası Sütunu",
                options=other_columns,
                help="Bina numarasını içeren sütunu seçin"
            )

        if date_columns:
            rng = _safe_sort_date_cols(date_columns)
            st.write(f"**Tespit edilen tarih sütunları:** {len(date_columns)} adet")
            st.write(f"Tarih aralığı: {rng[0]} - {rng[-1]}")

        # Analiz butonu
        if st.button("🔍 Anomali Analizini Başlat", type="primary"):
            if not date_columns:
                st.error("❌ Tarih sütunları bulunamadı! Lütfen dosya formatını kontrol edin.")
            elif not tesisat_col or not bina_col:
                st.error("❌ Lütfen tesisat ve bina sütunlarını seçin!")
            else:
                with st.spinner("Analiz yapılıyor..."):
                    results_df = analyze_consumption_patterns(df, date_columns, tesisat_col, bina_col)

                    if not results_df.empty:
                        st.subheader("📈 Analiz Sonuçları")
                        c1, c2, c3, c4 = st.columns(4)
                        with c1: st.metric("Toplam Tesisat", len(results_df))
                        with c2:
                            suspicious_count = int((results_df['suspicion_level'] == 'Şüpheli').sum())
                            st.metric("Şüpheli Tesisat", suspicious_count)
                        with c3:
                            if len(results_df) > 0:
                                suspicious_rate = (suspicious_count / len(results_df)) * 100
                                st.metric("Şüpheli Oran", f"{suspicious_rate:.1f}%")
                        with c4:
                            total_anomalies = int(results_df['anomali_sayisi'].sum())
                            st.metric("Toplam Anomali", total_anomalies)

                        # Görselleştirmeler
                        st.subheader("📊 Görselleştirmeler")
                        create_visualizations(results_df, df, date_columns)

                        # Şüpheli tesisatlar
                        st.subheader("🚨 Şüpheli Tesisatlar")
                        suspicious_df = results_df[results_df['suspicion_level'] == 'Şüpheli'].copy()

                        if not suspicious_df.empty:
                            display_cols = ['tesisat_no', 'bina_no', 'kis_tuketim', 'yaz_tuketim',
                                            'ortalama_tuketim', 'kis_trend', 'anomali_sayisi', 'anomaliler']
                            suspicious_display = suspicious_df[display_cols].copy()
                            suspicious_display.columns = ['Tesisat No', 'Bina No', 'Kış Tüketim',
                                                          'Yaz Tüketim', 'Ortalama Tüketim', 'Kış Trend',
                                                          'Anomali Sayısı', 'Anomaliler']
                            for col in ['Kış Tüketim', 'Yaz Tüketim', 'Ortalama Tüketim']:
                                suspicious_display[col] = suspicious_display[col].round(1)

                            st.dataframe(suspicious_display, use_container_width=True, hide_index=True)

                            buffer = BytesIO()
                            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                                suspicious_display.to_excel(writer, index=False, sheet_name='Şüpheli Tesisatlar')
                            st.download_button(
                                label="📥 Şüpheli Tesisatları İndir (Excel)",
                                data=buffer.getvalue(),
                                file_name="supheli_tesisatlar.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.success("🎉 Şüpheli tesisat bulunamadı!")
