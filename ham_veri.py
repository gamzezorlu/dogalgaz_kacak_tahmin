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
    """Raw veriyi pivot formata dönüştür - Completely Fixed version"""
    try:
        st.info("🔍 Veri dönüştürme başlıyor...")
        
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
        st.write(f"✓ Kolon eşleştirmesi: {column_mapping}")

        # Gerekli kolon kontrolü
        required = ['belge_tarihi', 'tesisat_no', 'bina_no', 'tuketim']
        missing = [c for c in required if c not in df_renamed.columns]
        if missing:
            st.error(f"❌ Eksik kolonlar: {missing}")
            st.info(f"Mevcut kolonlar: {list(df_renamed.columns)}")
            return None

        # Veri temizleme ve tip dönüşümleri
        st.info("🧹 Veri temizleniyor...")
        df_clean = df_renamed.copy()
        
        # Önce boyutu kaydet
        original_size = len(df_clean)
        
        # Tüketim sütununu önce kontrol et ve temizle
        st.write(f"🔍 Tüketim sütunu kontrol ediliyor...")
        st.write(f"Tüketim sütunu tipi: {type(df_clean['tuketim'])}")
        st.write(f"Tüketim sütunu sample: {df_clean['tuketim'].head()}")
        
        # Tüketim sütununu string'e çevir ve temizle
        df_clean['tuketim'] = df_clean['tuketim'].astype(str)
        
        # Virgül ile nokta değişimi (Türkçe decimal)
        df_clean['tuketim'] = df_clean['tuketim'].str.replace(',', '.')
        
        # Sadece sayısal karakterleri tut
        df_clean['tuketim'] = df_clean['tuketim'].str.replace(r'[^\d.-]', '', regex=True)
        
        # Boş string'leri NaN yap
        df_clean['tuketim'] = df_clean['tuketim'].replace('', np.nan)
        df_clean['tuketim'] = df_clean['tuketim'].replace('nan', np.nan)
        
        # Şimdi sayısal dönüşüm yap
        df_clean['tuketim'] = pd.to_numeric(df_clean['tuketim'], errors='coerce')
        
        # Tarih sütununu temizle
        df_clean['belge_tarihi'] = pd.to_datetime(
            df_clean['belge_tarihi'], errors='coerce', dayfirst=True
        )
        
        # String sütunları temizle
        df_clean['tesisat_no'] = df_clean['tesisat_no'].astype(str).str.strip()
        df_clean['bina_no'] = df_clean['bina_no'].astype(str).str.strip()
        
        # Geçersiz kayıtları temizle
        df_clean = df_clean.dropna(subset=['belge_tarihi'])
        after_date_clean = len(df_clean)
        
        # NaN tüketimleri 0 yap
        df_clean['tuketim'] = df_clean['tuketim'].fillna(0)
        
        # Negatif değerleri 0 yap
        df_clean['tuketim'] = df_clean['tuketim'].clip(lower=0)
        
        # Yıl/ay sütunu oluştur
        df_clean['yil_ay'] = df_clean['belge_tarihi'].dt.strftime('%Y/%m')
        
        # 'nan' string değerlerini ve boş değerleri temizle
        df_clean = df_clean[
            (df_clean['tesisat_no'] != 'nan') & 
            (df_clean['bina_no'] != 'nan') & 
            (df_clean['yil_ay'].notna()) &
            (df_clean['tesisat_no'] != '') & 
            (df_clean['bina_no'] != '') &
            (df_clean['tesisat_no'] != 'None') & 
            (df_clean['bina_no'] != 'None')
        ]
        
        final_clean_size = len(df_clean)
        
        st.write(f"📊 Veri temizleme raporu:")
        st.write(f"   • Başlangıç: {original_size:,} kayıt")
        st.write(f"   • Tarih temizleme sonrası: {after_date_clean:,} kayıt")
        st.write(f"   • Son temizlik sonrası: {final_clean_size:,} kayıt")
        
        if df_clean.empty:
            st.error("❌ Temizleme sonrası veri kalmadı!")
            st.info("💡 Veri formatını kontrol edin:")
            st.write("- Tarih formatının doğru olduğundan emin olun")
            st.write("- Tüketim değerlerinin sayısal olduğundan emin olun")
            st.write("- Tesisat ve bina numaralarının boş olmadığından emin olun")
            return None
        
        # Temel istatistikler
        st.write(f"✅ Temizlenmiş veri özeti:")
        st.write(f"   • Benzersiz tesisat: {df_clean['tesisat_no'].nunique()}")
        st.write(f"   • Benzersiz bina: {df_clean['bina_no'].nunique()}")
        st.write(f"   • Tarih aralığı: {df_clean['yil_ay'].min()} - {df_clean['yil_ay'].max()}")
        st.write(f"   • Toplam tüketim: {df_clean['tuketim'].sum():,.0f} m³")
        
        # Duplicate kontrolü ve birleştirme
        st.info("🔄 Veriler gruplandırılıyor...")
        
        # Önce duplicate kontrolü yapalım
        duplicates = df_clean.groupby(['tesisat_no', 'bina_no', 'yil_ay']).size()
        duplicate_count = (duplicates > 1).sum()
        if duplicate_count > 0:
            st.write(f"⚠️ {duplicate_count} adet duplicate grup bulundu, toplamları alınacak")
        
        # Gruplama ve toplama işlemi
        grouped_df = df_clean.groupby(
            ['tesisat_no', 'bina_no', 'yil_ay'], as_index=False
        )['tuketim'].sum()
        
        st.write(f"✓ Gruplandırma tamamlandı: {len(grouped_df):,} benzersiz kayıt")
        
        # Manuel pivot işlemi - Dictionary tabanlı
        st.info("📊 Pivot table oluşturuluyor...")
        
        # Tüm benzersiz değerleri al
        unique_tesisats = sorted(grouped_df['tesisat_no'].unique())
        unique_binas = sorted(grouped_df['bina_no'].unique())  
        unique_dates = sorted(grouped_df['yil_ay'].unique())
        
        st.write(f"📈 Pivot boyutları:")
        st.write(f"   • Tesisat sayısı: {len(unique_tesisats)}")
        st.write(f"   • Bina sayısı: {len(unique_binas)}")
        st.write(f"   • Tarih sayısı: {len(unique_dates)}")
        
        # Pivot dictionary'si oluştur
        pivot_dict = {}
        
        # Her grup için pivot dictionary'yi doldur
        for _, row in grouped_df.iterrows():
            key = (row['tesisat_no'], row['bina_no'])
            date = row['yil_ay']
            value = row['tuketim']
            
            if key not in pivot_dict:
                pivot_dict[key] = {'tesisat_no': row['tesisat_no'], 'bina_no': row['bina_no']}
                # Tüm tarihleri 0 ile başlat
                for d in unique_dates:
                    pivot_dict[key][d] = 0
            
            # Değeri güncelle
            pivot_dict[key][date] = value
        
        # Dictionary'yi DataFrame'e çevir
        pivot_rows = list(pivot_dict.values())
        final_df = pd.DataFrame(pivot_rows)
        
        # Sütun sırasını düzenle
        date_cols = [col for col in final_df.columns if col not in ['tesisat_no', 'bina_no']]
        date_cols = _safe_sort_date_cols(date_cols)
        final_df = final_df[['tesisat_no', 'bina_no'] + date_cols]
        
        st.write(f"✅ Pivot table oluşturuldu: {len(final_df)} satır x {len(final_df.columns)} sütun")
        
        return final_df

    except Exception as e:
        st.error(f"❌ Veri dönüştürme hatası: {str(e)}")
        st.info("🔍 Hata detayları:")
        
        # Hata durumunda debug bilgileri göster
        try:
            if 'df_renamed' in locals():
                st.write("**df_renamed bilgileri:**")
                st.write(f"- Shape: {df_renamed.shape}")
                st.write(f"- Columns: {list(df_renamed.columns)}")
                st.write("- İlk 3 satır:")
                st.dataframe(df_renamed.head(3))
                
                # Tüketim sütunu özel kontrolü
                if 'tuketim' in df_renamed.columns:
                    st.write("**Tüketim sütunu analizi:**")
                    st.write(f"- Tip: {df_renamed['tuketim'].dtype}")
                    st.write(f"- Benzersiz değer sayısı: {df_renamed['tuketim'].nunique()}")
                    st.write(f"- Null sayısı: {df_renamed['tuketim'].isnull().sum()}")
                    st.write("- İlk 10 değer:")
                    st.write(df_renamed['tuketim'].head(10).tolist())
                    
                    # Problematik değerleri tespit et
                    problematic = df_renamed['tuketim'][~df_renamed['tuketim'].apply(lambda x: str(x).replace('.', '').replace('-', '').isdigit() if pd.notna(x) else True)]
                    if not problematic.empty:
                        st.write("**Problematik değerler:**")
                        st.write(problematic.head(10).tolist())
                        
            if 'df_clean' in locals():
                st.write("**df_clean bilgileri:**")
                st.write(f"- Shape: {df_clean.shape}")
                st.write(f"- Columns: {list(df_clean.columns)}")
                if not df_clean.empty:
                    st.write("- İlk 3 satır:")
                    st.dataframe(df_clean.head(3))
                    
            if 'grouped_df' in locals():
                st.write("**grouped_df bilgileri:**")
                st.write(f"- Shape: {grouped_df.shape}")
                st.write("- Sample:")
                st.dataframe(grouped_df.head(3))
                
        except Exception as debug_error:
            st.write(f"Debug bilgileri alınamadı: {debug_error}")
            
        # Traceback göster
        import traceback
        st.text("**Full Traceback:**")
        st.code(traceback.format_exc())
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

                        # Tüm Sonuçlar
                        st.subheader("📋 Tüm Sonuçlar")

                        filter_col1, filter_col2 = st.columns(2)
                        with filter_col1:
                            suspicion_filter = st.selectbox("Şüpheli Durumu", options=['Tümü', 'Şüpheli', 'Normal'], index=0)
                        with filter_col2:
                            bina_list = sorted(results_df['bina_no'].dropna().astype(str).unique().tolist()) if not results_df.empty else []
                            bina_filter = st.selectbox("Bina Numarası", options=['Tümü'] + bina_list, index=0)

                        filtered_df = results_df.copy()
                        if suspicion_filter != 'Tümü':
                            filtered_df = filtered_df[filtered_df['suspicion_level'] == suspicion_filter]
                        if bina_filter != 'Tümü':
                            filtered_df = filtered_df[filtered_df['bina_no'] == bina_filter]

                        if not filtered_df.empty:
                            display_cols = ['tesisat_no', 'bina_no', 'kis_tuketim', 'yaz_tuketim',
                                            'ortalama_tuketim', 'kis_trend', 'suspicion_level', 'anomaliler']
                            filtered_display = filtered_df[display_cols].copy()
                            filtered_display.columns = ['Tesisat No', 'Bina No', 'Kış Tüketim',
                                                        'Yaz Tüketim', 'Ortalama Tüketim', 'Kış Trend',
                                                        'Durum', 'Anomaliler']
                            for col in ['Kış Tüketim', 'Yaz Tüketim', 'Ortalama Tüketim']:
                                filtered_display[col] = filtered_display[col].round(1)

                            st.dataframe(filtered_display, use_container_width=True, hide_index=True)

                            buffer_all = BytesIO()
                            with pd.ExcelWriter(buffer_all, engine='openpyxl') as writer:
                                filtered_display.to_excel(writer, index=False, sheet_name='Tüm Sonuçlar')
                            st.download_button(
                                label="📥 Filtrelenmiş Sonuçları İndir (Excel)",
                                data=buffer_all.getvalue(),
                                file_name="dogalgaz_analiz_sonuclari.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.warning("Filtreye uygun veri bulunamadı.")
                    else:
                        st.warning("⚠️ Analiz sonucunda veri oluşmadı. Lütfen veri formatını kontrol edin.")

else:
    st.info("👈 Lütfen sol panelden bir dosya yükleyin")

    # Örnek dosya formatı
    st.subheader("📄 Beklenen Dosya Formatı")
    st.write("Dosyanızda aşağıdaki sütunlar bulunmalıdır:")

    example_data = {
        'tesisat_no': ['T001', 'T002', 'T003'],
        'bina_no': ['B001', 'B001', 'B002'],
        'Belge tarihi': ['2024-01-01', '2024-01-15', '2024-02-01'],
        'sm3': [110, 20, 140],
    }
    example_df = pd.DataFrame(example_data)
    st.dataframe(example_df, use_container_width=True)

# -------------------- Bilgi paneli --------------------
st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 Tespit Kriterleri")
st.sidebar.markdown(f"""
- **Kış Düşük Tüketim**: < {kis_tuketim_esigi} m³/ay
- **Bina Ortalaması**: %{bina_ort_dusuk_oran} düşük
- **Ani Düşüş**: %{ani_dusus_orani} düşüş
- **Kış-Yaz Farkı**: Çok az fark
- **Toplam Tüketim**: Çok düşük
- **Sıfır Tüketim**: 6+ ay sıfır
""")

st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ Kullanım Bilgileri")
st.sidebar.markdown("""
1. CSV veya Excel dosyasını yükleyin
2. Tesisat ve bina sütunlarını seçin
3. Parametreleri ayarlayın
4. Analizi başlatın
5. Sonuçları inceleyin ve Excel olarak indirin
""")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🛠️ Teknik Bilgiler")
st.sidebar.markdown("""
**Desteklenen Formatlar:**
- Raw veri (belge tarihi, tesisat, bina, tüketim)
- Pivot veri (tesisat, bina, YYYY/MM sütunları)

**Anomali Tespiti:**
- Kış ayı düşük tüketim
- Kış-yaz farkının az olması
- Toplam tüketimin çok düşük olması
- Çok fazla sıfır tüketim
- Ani tüketim düşüşü
- Bina ortalamasından düşük tüketim
""")

# -------------------- Gelişmiş Özellikler --------------------
if uploaded_file is not None and 'df' in locals():
    st.sidebar.markdown("---")
    st.sidebar.header("🔧 Gelişmiş Özellikler")
    
    # Veri kalitesi raporu
    if st.sidebar.button("📊 Veri Kalitesi Raporu"):
        st.subheader("📊 Veri Kalitesi Raporu")
        
        # Genel istatistikler
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Toplam Kayıt", len(df))
        with col2:
            if 'tesisat_col' in locals() and tesisat_col:
                unique_tesisat = df[tesisat_col].nunique()
                st.metric("Benzersiz Tesisat", unique_tesisat)
        with col3:
            if 'bina_col' in locals() and bina_col:
                unique_bina = df[bina_col].nunique()
                st.metric("Benzersiz Bina", unique_bina)
        
        # Tarih sütunları analizi
        if 'date_columns' in locals() and date_columns:
            st.write("**Tarih Sütunları Analizi:**")
            
            date_stats = []
            for date_col in date_columns:
                non_zero = (df[date_col] > 0).sum()
                zero_count = (df[date_col] == 0).sum()
                nan_count = df[date_col].isna().sum()
                mean_val = df[date_col].mean()
                
                date_stats.append({
                    'Tarih': date_col,
                    'Sıfır Olmayan': non_zero,
                    'Sıfır': zero_count,
                    'Boş': nan_count,
                    'Ortalama': round(mean_val, 2) if not pd.isna(mean_val) else 0
                })
            
            date_stats_df = pd.DataFrame(date_stats)
            st.dataframe(date_stats_df, use_container_width=True)
    
    # Tesisat bazında detay analiz
    if st.sidebar.button("🔍 Tesisat Detay Analizi"):
        if 'results_df' in locals() and not results_df.empty:
            st.subheader("🔍 Tesisat Detay Analizi")
            
            # Tesisat seçimi
            selected_tesisat = st.selectbox(
                "Analiz edilecek tesisatı seçin:",
                options=results_df['tesisat_no'].unique()
            )
            
            # Seçilen tesisatın detayları
            tesisat_data = results_df[results_df['tesisat_no'] == selected_tesisat].iloc[0]
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Temel Bilgiler:**")
                st.write(f"- Tesisat No: {tesisat_data['tesisat_no']}")
                st.write(f"- Bina No: {tesisat_data['bina_no']}")
                st.write(f"- Durum: {tesisat_data['suspicion_level']}")
                st.write(f"- Anomali Sayısı: {tesisat_data['anomali_sayisi']}")
                
            with col2:
                st.write("**Tüketim Verileri:**")
                st.write(f"- Kış Ortalama: {tesisat_data['kis_tuketim']:.1f} m³")
                st.write(f"- Yaz Ortalama: {tesisat_data['yaz_tuketim']:.1f} m³")
                st.write(f"- Genel Ortalama: {tesisat_data['ortalama_tuketim']:.1f} m³")
                st.write(f"- Kış Trend: {tesisat_data['kis_trend']}")
            
            # Anomali detayları
            if tesisat_data['anomaliler'] != 'Normal':
                st.write("**🚨 Tespit Edilen Anomaliler:**")
                for anomali in tesisat_data['anomaliler'].split('; '):
                    st.write(f"- {anomali}")
            
            # Grafik gösterimi
            if 'date_columns' in locals() and date_columns:
                tesisat_row = df[df[tesisat_col] == selected_tesisat].iloc[0]
                
                # Aylık tüketim verilerini hazırla
                monthly_data = []
                for date_col in date_columns:
                    try:
                        value = tesisat_row[date_col]
                        if pd.notna(value):
                            year, month = date_col.split('/')
                            monthly_data.append({
                                'Tarih': date_col,
                                'Yıl': int(year),
                                'Ay': int(month),
                                'Tüketim': float(value),
                                'Mevsim': get_season(int(month))
                            })
                    except:
                        continue
                
                if monthly_data:
                    monthly_df = pd.DataFrame(monthly_data)
                    
                    # Zaman serisi grafiği
                    fig = px.line(
                        monthly_df, 
                        x='Tarih', 
                        y='Tüketim',
                        title=f"{selected_tesisat} - Aylık Tüketim Trendi",
                        color='Mevsim',
                        markers=True
                    )
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Mevsimsel box plot
                    fig2 = px.box(
                        monthly_df, 
                        x='Mevsim', 
                        y='Tüketim',
                        title=f"{selected_tesisat} - Mevsimsel Tüketim Dağılımı"
                    )
                    st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Önce anomali analizini çalıştırın.")
    
    # Bina bazında karşılaştırma
    if st.sidebar.button("🏢 Bina Karşılaştırması"):
        if 'results_df' in locals() and not results_df.empty:
            st.subheader("🏢 Bina Bazında Karşılaştırma")
            
            # Bina seçimi
            selected_bina = st.selectbox(
                "Karşılaştırılacak binayı seçin:",
                options=results_df['bina_no'].unique()
            )
            
            # Seçilen binadaki tesisatlar
            bina_tesisatlari = results_df[results_df['bina_no'] == selected_bina]
            
            st.write(f"**{selected_bina} Binasındaki Tesisatlar ({len(bina_tesisatlari)} adet):**")
            
            # Özet istatistikler
            col1, col2, col3 = st.columns(3)
            with col1:
                supheli_sayi = (bina_tesisatlari['suspicion_level'] == 'Şüpheli').sum()
                st.metric("Şüpheli Tesisat", supheli_sayi)
            with col2:
                ort_kis_tuketim = bina_tesisatlari['kis_tuketim'].mean()
                st.metric("Ort. Kış Tüketim", f"{ort_kis_tuketim:.1f}")
            with col3:
                ort_yaz_tuketim = bina_tesisatlari['yaz_tuketim'].mean()
                st.metric("Ort. Yaz Tüketim", f"{ort_yaz_tuketim:.1f}")
            
            # Detay tablo
            display_cols = ['tesisat_no', 'kis_tuketim', 'yaz_tuketim', 
                           'ortalama_tuketim', 'suspicion_level', 'anomali_sayisi']
            bina_display = bina_tesisatlari[display_cols].copy()
            bina_display.columns = ['Tesisat', 'Kış', 'Yaz', 'Ortalama', 'Durum', 'Anomali']
            
            for col in ['Kış', 'Yaz', 'Ortalama']:
                bina_display[col] = bina_display[col].round(1)
                
            st.dataframe(bina_display, use_container_width=True, hide_index=True)
            
            # Görselleştirme
            fig = px.scatter(
                bina_tesisatlari,
                x='yaz_tuketim',
                y='kis_tuketim', 
                color='suspicion_level',
                size='anomali_sayisi',
                hover_name='tesisat_no',
                title=f"{selected_bina} Binası - Tesisat Karşılaştırması",
                color_discrete_map={'Şüpheli': '#FF6B6B', 'Normal': '#4ECDC4'}
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Önce anomali analizini çalıştırın.")
    
    # Excel rapor oluşturucu
    if st.sidebar.button("📄 Detaylı Excel Raporu"):
        if 'results_df' in locals() and not results_df.empty and 'df' in locals():
            st.subheader("📄 Detaylı Excel Raporu Oluşturuluyor...")
            
            with st.spinner("Rapor hazırlanıyor..."):
                # Çoklu sayfa Excel raporu
                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    
                    # Sayfa 1: Özet
                    ozet_data = {
                        'Metrik': [
                            'Toplam Tesisat Sayısı',
                            'Şüpheli Tesisat Sayısı', 
                            'Normal Tesisat Sayısı',
                            'Şüpheli Oranı (%)',
                            'Toplam Anomali Sayısı',
                            'Ortalama Kış Tüketimi',
                            'Ortalama Yaz Tüketimi'
                        ],
                        'Değer': [
                            len(results_df),
                            (results_df['suspicion_level'] == 'Şüpheli').sum(),
                            (results_df['suspicion_level'] == 'Normal').sum(),
                            round(((results_df['suspicion_level'] == 'Şüpheli').sum() / len(results_df)) * 100, 1),
                            results_df['anomali_sayisi'].sum(),
                            round(results_df['kis_tuketim'].mean(), 1),
                            round(results_df['yaz_tuketim'].mean(), 1)
                        ]
                    }
                    ozet_df = pd.DataFrame(ozet_data)
                    ozet_df.to_excel(writer, sheet_name='Özet', index=False)
                    
                    # Sayfa 2: Şüpheli tesisatlar
                    supheli_df = results_df[results_df['suspicion_level'] == 'Şüpheli'].copy()
                    if not supheli_df.empty:
                        supheli_df.to_excel(writer, sheet_name='Şüpheli Tesisatlar', index=False)
                    
                    # Sayfa 3: Tüm sonuçlar
                    results_df.to_excel(writer, sheet_name='Tüm Sonuçlar', index=False)
                    
                    # Sayfa 4: Ham veriler (ilk 1000 satır)
                    df.head(1000).to_excel(writer, sheet_name='Ham Veriler', index=False)
                    
                    # Sayfa 5: Bina bazında özet
                    bina_ozet = results_df.groupby('bina_no').agg({
                        'tesisat_no': 'count',
                        'kis_tuketim': 'mean',
                        'yaz_tuketim': 'mean',
                        'anomali_sayisi': 'sum',
                        'suspicion_level': lambda x: (x == 'Şüpheli').sum()
                    }).round(1)
                    bina_ozet.columns = ['Tesisat_Sayısı', 'Ort_Kış_Tüketim', 'Ort_Yaz_Tüketim', 'Toplam_Anomali', 'Şüpheli_Sayısı']
                    bina_ozet.to_excel(writer, sheet_name='Bina Bazında Özet')
                
                st.success("✅ Detaylı rapor hazırlandı!")
                st.download_button(
                    label="📥 Detaylı Excel Raporunu İndir",
                    data=buffer.getvalue(),
                    file_name=f"dogalgaz_detayli_rapor_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.info("Önce anomali analizini çalıştırın.")

# -------------------- Alt bilgi --------------------
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
<p>🔥 Doğalgaz Tüketim Anomali Tespit Sistemi v2.0</p>
<p>Gelişmiş analiz özellikleri ile şüpheli tüketim paternlerini tespit eder</p>
</div>
""", unsafe_allow_html=True)
