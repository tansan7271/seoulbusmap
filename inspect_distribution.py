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

def inspect_distribution():
    print("Fetching data...")
    df = get_analysis_data()
    
    if df.empty:
        print("No data.")
        return

    # Filter valid data
    valid_df = df[(df['population'] > 0) & (df['busstop_count'] > 0)].copy()
    
    index_values = valid_df['weekend_intensity_index']
    
    print("\n--- Weekend Intensity Index Distribution ---")
    print(index_values.describe())
    
    print("\n--- Percentiles ---")
    print(f"10%: {np.percentile(index_values, 10):.4f}")
    print(f"25%: {np.percentile(index_values, 25):.4f}")
    print(f"50% (Median): {np.percentile(index_values, 50):.4f}")
    print(f"75%: {np.percentile(index_values, 75):.4f}")
    print(f"90%: {np.percentile(index_values, 90):.4f}")
    print(f"95%: {np.percentile(index_values, 95):.4f}")
    print(f"99%: {np.percentile(index_values, 99):.4f}")
    
    print("\n--- Top 10 Districts by Index ---")
    print(valid_df.sort_values('weekend_intensity_index', ascending=False)[['name', 'weekend_intensity_index']].head(10))

if __name__ == '__main__':
    inspect_distribution()
