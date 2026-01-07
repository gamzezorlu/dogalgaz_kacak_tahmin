import pandas as pd
import numpy as np
from datetime import datetime
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from sklearn.preprocessing import StandardScaler
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

class GazSayacAnaliz:
    def __init__(self):
        self.season_months = {
            'kış': [11, 12, 1, 2, 3],
            'yaz': [6, 7, 8, 9],
            'geçiş': [4, 5, 10]
        }
    
    def detect_manipulation(self, df, tesisat_no):
        """
        Her tesisat için manipülasyon şüphesi analizi
        """
        tesisat_df = df[df['tesisat_no'] == tesisat_no].copy()
        tesisat_df = tesisat_df.sort_values('tarih')
        
        # 1. Rekor kırılma tespiti
        max_consumption_idx = tesisat_df['tuketim'].idxmax()
        max_date = tesisat_df.loc[max_consumption_idx, 'tarih']
        
        # 2. Öncesi ve sonrası dönemler
        before_period = tesisat_df[tesisat_df['tarih'] < max_date]
        after_period = tesisat_df[tesisat_df['tarih'] > max_date]
        
        if len(before_period) < 6 or len(after_period) < 6:
            return None
        
        # 3. Mevsimsel düzeltme
        before_seasonal = self._seasonal_adjustment(before_period)
        after_seasonal = self._seasonal_adjustment(after_period)
        
        # 4. İstatistiksel testler
        results = {
            'tesisat_no': tesisat_no,
            'rekor_tarihi': max_date,
            'rekor_degeri': tesisat_df.loc[max_consumption_idx, 'tuketim'],
            'bina_no': tesisat_df['bina_no'].iloc[0],
            'süphe_puani': 0,
            'manipulasyon_olasiligi': 'DÜŞÜK'
        }
        
        # Test 1: Ortalama değişim
        mean_before = before_seasonal.mean()
        mean_after = after_seasonal.mean()
        mean_change = ((mean_after - mean_before) / mean_before) * 100
        
        # Test 2: T-test (istatistiksel anlamlılık)
        if len(before_seasonal) > 1 and len(after_seasonal) > 1:
            t_stat, p_value = stats.ttest_ind(before_seasonal, after_seasonal)
            results['t_test_p_value'] = p_value
            
            if p_value < 0.05 and mean_change < -30:
                results['süphe_puani'] += 30
        
        # Test 3: Sürekli düşüş analizi
        if self._check_continuous_decline(after_period):
            results['süphe_puani'] += 40
        
        # Test 4: Mevsim normallerine göre analiz
        seasonal_deviation = self._check_seasonal_deviation(after_period)
        if seasonal_deviation > 50:  # %50'den fazla sapma
            results['süphe_puani'] += 20
        
        # Test 5: Ani düşüş tespiti
        if self._check_sudden_drop(tesisat_df, max_date):
            results['süphe_puani'] += 10
        
        # Toplam puan değerlendirmesi
        if results['süphe_puani'] >= 70:
            results['manipulasyon_olasiligi'] = 'YÜKSEK'
        elif results['süphe_puani'] >= 40:
            results['manipulasyon_olasiligi'] = 'ORTA'
        
        results['ortalama_degisim'] = mean_change
        results['analiz_edilen_aylar'] = len(tesisat_df)
        
        return results
    
    def _seasonal_adjustment(self, df):
        """
        Mevsimsel etkileri düzelt
        """
        adjusted = []
        for _, row in df.iterrows():
            month = row['tarih'].month
            season = self._get_season(month)
            # Mevsimsel katsayılar (gerçek veriye göre ayarlanmalı)
            seasonal_factors = {'kış': 1.2, 'yaz': 0.7, 'geçiş': 1.0}
            adjusted.append(row['tuketim'] / seasonal_factors[season])
        return np.array(adjusted)
    
    def _get_season(self, month):
        for season, months in self.season_months.items():
            if month in months:
                return season
        return 'geçiş'
    
    def _check_continuous_decline(self, df):
        """
        Sürekli düşüş kontrolü
        """
        if len(df) < 3:
            return False
        
        # 3 aylık hareketli ortalama
        df['rolling_avg'] = df['tuketim'].rolling(window=3, min_periods=1).mean()
        
        # Düşüş trendi kontrolü
        trend = np.polyfit(range(len(df)), df['rolling_avg'].values, 1)[0]
        
        return trend < -0.1  # Negatif eğim
    
    def _check_seasonal_deviation(self, df):
        """
        Mevsim normallerinden sapma kontrolü
        """
        if len(df) < 12:
            return 0
        
        # Aylık ortalamaları hesapla
        monthly_avg = df.groupby(df['tarih'].dt.month)['tuketim'].mean()
        
        # Tarihsel normaller (bu veri setinize göre ayarlanmalı)
        historical_norms = {
            1: 150, 2: 140, 3: 120, 4: 80, 5: 60,
            6: 40, 7: 35, 8: 38, 9: 55, 10: 70,
            11: 100, 12: 130
        }
        
        deviations = []
        for month, avg in monthly_avg.items():
            if month in historical_norms:
                deviation = abs(avg - historical_norms[month]) / historical_norms[month] * 100
                deviations.append(deviation)
        
        return np.mean(deviations) if deviations else 0
    
    def _check_sudden_drop(self, df, max_date):
        """
        Ani düşüş kontrolü
        """
        # Rekor sonrası 3 ay
        after_months = df[df['tarih'] > max_date].head(3)
        
        if len(after_months) < 3:
            return False
        
        # İlk 3 aydaki düşüş oranı
        drop_rate = ((after_months['tuketim'].mean() - df[df['tarih'] == max_date]['tuketim'].iloc[0]) / 
                    df[df['tarih'] == max_date]['tuketim'].iloc[0]) * 100
        
        return drop_rate < -50  # %50'den fazla ani düşüş