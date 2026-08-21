"""
eda.py
Exploratory Data Analysis for the IGI Flood Risk Project.
Run: python scripts/eda.py
"""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd
import matplotlib.pyplot as plt
from project_paths import OUTPUTS_DIR

INPUT_FILE = OUTPUTS_DIR / "sites_with_cities.csv"
OUTPUT_DIR = OUTPUTS_DIR / "eda_figures_claude"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(INPUT_FILE)

print("=" * 70)
print("IGI FLOOD RISK - EXPLORATORY DATA ANALYSIS")
print("=" * 70)
print(f"\nTotal insured sites: {len(df)}")

print("\n========== MISSING VALUES ==========\n")
print(df.isnull().sum())

hazard_cols = [
    "RP100_depth", "RP10_depth", "RP500_depth",
    "elevation_m", "hand_m", "historical_flood_hits",
    "monsoon_p95_rainfall_mm", "monsoon_max_rainfall_mm"
]

# ---- FIX 1: exclude -9999 sentinel (coastal/no-data) sites from plots/stats ----
sentinel_mask = (df[["elevation_m", "hand_m"]] == -9999).any(axis=1)
print(f"\nCoastal/no-data sites excluded from plots below: {sentinel_mask.sum()}")
df_clean = df.loc[~sentinel_mask].copy()

print("\n========== SUMMARY STATISTICS (excl. coastal/no-data) ==========\n")
print(df_clean[hazard_cols].describe(percentiles=[0.25, 0.50, 0.75, 0.90, 0.95, 0.99]))

print("\n========== CORRELATION MATRIX ==========\n")
corr = df_clean[hazard_cols].corr().round(2)
print(corr)
corr.to_csv(OUTPUT_DIR / "correlation_matrix.csv")

print("\n========== TOP 20 CITIES ==========\n")
print(df["city"].value_counts().head(20))
print("\n========== PROVINCES ==========\n")
print(df["province"].value_counts())


def save_bar(series, title, ylabel, filename):
    plt.figure(figsize=(11, 5))
    series.plot(kind="bar")
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / filename, dpi=200)
    plt.close()


# ---- FIX 2: zero-heavy columns get a nonzero-only histogram, so the
#      real spread is visible instead of one giant bar at 0 ----
zero_heavy = ["RP100_depth", "RP10_depth", "RP500_depth", "historical_flood_hits"]

print("\nCreating histograms...")
for col in hazard_cols:
    data = df_clean[col]
    if col in zero_heavy:
        zero_pct = (data == 0).mean() * 100
        print(f"{col}: {zero_pct:.1f}% of sites at 0 (plotting nonzero only)")
        data = data[data > 0]
        if len(data) < 2:
            continue
    plt.figure(figsize=(6, 4))
    plt.hist(data, bins=30)
    plt.title(col + (" (nonzero only)" if col in zero_heavy else ""))
    plt.xlabel(col)
    plt.ylabel("Frequency")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f"{col}_histogram.png", dpi=200)
    plt.close()

# ---- FIX 3: one combined boxplot grid instead of 8 separate tiny files ----
print("Creating boxplot grid...")
fig, axes = plt.subplots(2, 4, figsize=(16, 8))
for ax, col in zip(axes.flat, hazard_cols):
    ax.boxplot(df_clean[col].dropna())
    ax.set_title(col, fontsize=10)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "boxplots_grid.png", dpi=200)
plt.close()

# ---- City-level bar charts (unchanged logic, using df_clean where terrain-based) ----
rainfall = df_clean.groupby("city")["monsoon_p95_rainfall_mm"].mean().sort_values(ascending=False)
save_bar(rainfall.head(20), "Average Extreme Monsoon Rainfall by City", "Rainfall (mm)", "rainfall_by_city.png")

depth = df_clean.groupby("city")["RP100_depth"].mean().sort_values(ascending=False)
save_bar(depth.head(20), "Average RP100 Flood Depth by City", "Flood Depth (m)", "rp100_depth_by_city.png")

hand = df_clean.groupby("city")["hand_m"].mean().sort_values(ascending=False)
save_bar(hand.head(20), "Average HAND by City", "HAND (m)", "hand_by_city.png")

elevation = df_clean.groupby("city")["elevation_m"].mean().sort_values(ascending=False)
save_bar(elevation.head(20), "Average Elevation by City", "Elevation (m)", "elevation_by_city.png")

# sum insured uses full df - coastal sites still count as real exposure
insured = (df.groupby("city")["net_sum_insured"].sum() / 1e9).sort_values(ascending=False)
save_bar(insured.head(20), "Total Sum Insured by City", "PKR (Billions)", "sum_insured_by_city.png")

site_count = df["city"].value_counts()
save_bar(site_count.head(20), "Number of Insured Sites by City", "Number of Sites", "sites_by_city.png")

# ---- Scatter plots (unchanged, just using df_clean so -9999 doesn't distort the axes) ----
plt.figure(figsize=(7, 5))
plt.scatter(df_clean["monsoon_p95_rainfall_mm"], df_clean["RP100_depth"], alpha=0.6)
plt.xlabel("Monsoon P95 Rainfall (mm)")
plt.ylabel("RP100 Flood Depth (m)")
plt.title("Rainfall vs Flood Depth")
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "rainfall_vs_flood_depth.png", dpi=200)
plt.close()

plt.figure(figsize=(7, 5))
plt.scatter(df_clean["hand_m"], df_clean["RP100_depth"], alpha=0.6)
plt.xlabel("HAND (m)")
plt.ylabel("RP100 Flood Depth (m)")
plt.title("HAND vs Flood Depth")
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "hand_vs_flood_depth.png", dpi=200)
plt.close()

print("\n" + "=" * 70)
print("EDA COMPLETE")
print("=" * 70)
print(f"\nFigures saved to:\n{OUTPUT_DIR}")
print("\nReview these visualisations before creating risk_score.py.")