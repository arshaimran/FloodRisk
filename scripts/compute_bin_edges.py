"""Compute percentile-based bin edges for riverine/pluvial score bins.
Run: python scripts/compute_bin_edges.py
"""
from pathlib import Path
import pandas as pd

P = Path(__file__).resolve().parent.parent / 'outputs' / 'sites_with_cities.csv'
df = pd.read_csv(P)

for col in ['RP100_depth', 'monsoon_p95_rainfall_mm']:
    s = df.loc[df[col] > 0, col].dropna()
    print(f"\n--- {col} (nonzero, N={len(s)}) ---")
    if len(s) == 0:
        print('No nonzero values')
        continue
    print(s.describe(percentiles=[0.5, 0.75, 0.85, 0.9, 0.95, 0.97, 0.99]))

print('\nFinished compute_bin_edges.py')
