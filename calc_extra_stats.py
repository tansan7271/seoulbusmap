import os
import django
import sys
import pandas as pd
import numpy as np

# Setup Django environment
sys.path.append('/Users/kdg/PATHDirectory/Git Repositories/seoulbusmap')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'busmap.settings')
django.setup()

from main.analysis import get_analysis_data

def calc_extra_stats():
    print("Fetching data...")
    df = get_analysis_data()
    
    if df.empty:
        print("No data.")
        return

    # Filter valid data
    valid_df = df[(df['population'] > 0) & (df['busstop_count'] > 0)].copy()
    
    print("\n--- General Stats ---")
    print(f"Total Districts: {len(valid_df)}")
    print(f"Avg Population: {valid_df['population'].mean():.2f}")
    print(f"Avg Bus Stops: {valid_df['busstop_count'].mean():.2f}")
    
    # Stops per Capita (per 10,000 people)
    valid_df['stops_per_10k'] = (valid_df['busstop_count'] / valid_df['population']) * 10000
    print(f"Avg Stops per 10k people: {valid_df['stops_per_10k'].mean():.2f}")
    print(f"Max Stops per 10k: {valid_df['stops_per_10k'].max():.2f}")
    print(f"Min Stops per 10k: {valid_df['stops_per_10k'].min():.2f}")
    
    # Correlations
    print("\n--- Correlations ---")
    corr_pop_stops = np.corrcoef(valid_df['population'], valid_df['busstop_count'])[0, 1]
    print(f"Population vs Stops: {corr_pop_stops:.4f}")
    
    corr_pop_weekday = np.corrcoef(valid_df['population'], valid_df['avg_weekday'])[0, 1]
    print(f"Population vs Weekday Usage: {corr_pop_weekday:.4f}")
    
    corr_stops_weekday = np.corrcoef(valid_df['busstop_count'], valid_df['avg_weekday'])[0, 1]
    print(f"Stops vs Weekday Usage: {corr_stops_weekday:.4f}")

if __name__ == '__main__':
    calc_extra_stats()
