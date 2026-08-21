"""Fit Gumbel rainfall return periods from CHIRPS annual daily maxima.

With about 35 annual maxima, the RP500 estimate is a substantial extrapolation
beyond the observed record. It must be treated as lower confidence than RP10 or
RP100 in any later dashboard or decision-support display.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import gumbel_r


BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = BASE_DIR / "outputs" / "annual_max_daily_rainfall_chirps.csv"
SITES_FILE = BASE_DIR / "data" / "sites_input.csv"
HAZARD_FILE = BASE_DIR / "outputs" / "sites_with_cities.csv"
OUTPUT_FILE = BASE_DIR / "outputs" / "rainfall_return_periods_chirps.csv"
MIN_RECORD_YEARS = 15
RETURN_PERIODS = (10, 100, 500)


def return_level(values, period):
    """Fit a Gumbel maximum distribution and return its annual exceedance level."""
    location, scale = gumbel_r.fit(values)
    return float(gumbel_r.ppf(1 - 1 / period, location, scale))


def fit_site(group):
    """Fit one site's valid annual maxima or return explicit nulls for short records."""
    values = pd.to_numeric(group["annual_max_daily_rainfall_mm"], errors="coerce").dropna()
    record_years = len(values)
    result = {
        "Site_ID": group["Site_ID"].iloc[0],
        "Client": group["Client"].iloc[0],
        "years_used": record_years,
        "rainfall_RP10_mm": np.nan,
        "rainfall_RP100_mm": np.nan,
        "rainfall_RP500_mm": np.nan,
    }
    if record_years >= MIN_RECORD_YEARS:
        result.update({f"rainfall_RP{period}_mm": return_level(values, period) for period in RETURN_PERIODS})
    return result


def print_plausibility_check(out):
    """Compare a deterministic ten-site sample with existing monsoon maxima."""
    if not HAZARD_FILE.exists():
        print(f"Check B unavailable: {HAZARD_FILE} does not exist.")
        return
    hazard = pd.read_csv(HAZARD_FILE)
    required = {"Site_ID", "monsoon_max_rainfall_mm"}
    if not required.issubset(hazard.columns):
        print("Check B unavailable: existing hazard file lacks monsoon_max_rainfall_mm.")
        return

    compare = out.merge(hazard[["Site_ID", "monsoon_max_rainfall_mm"]], on="Site_ID", how="left")
    compare = compare.dropna(subset=["rainfall_RP100_mm", "monsoon_max_rainfall_mm"]).sort_values("Site_ID")
    compare["rp100_below_observed_max"] = compare["rainfall_RP100_mm"] < compare["monsoon_max_rainfall_mm"]
    sample = compare.iloc[np.linspace(0, len(compare) - 1, min(10, len(compare)), dtype=int)]
    print("\n=== CHECK B: RP100 versus existing monsoon historical maximum (sample) ===")
    print(sample[["Site_ID", "Client", "monsoon_max_rainfall_mm", "rainfall_RP100_mm", "rp100_below_observed_max"]].to_string(index=False))
    below = int(compare["rp100_below_observed_max"].sum())
    print(f"RP100 below existing observed monsoon maximum: {below}/{len(compare)} fitted sites")
    if below:
        print("FLAG: investigate before relying on RP100 values that fall below the observed maximum.")


def main():
    annual = pd.read_csv(INPUT_FILE)
    required = {"Site_ID", "Client", "year", "annual_max_daily_rainfall_mm"}
    missing = required - set(annual.columns)
    if missing:
        raise ValueError(f"{INPUT_FILE.name} is missing required columns: {sorted(missing)}")

    results = [fit_site(group) for _, group in annual.groupby("Site_ID", sort=False)]
    out = pd.DataFrame(results)

    # Preserve one output row for every current portfolio site, even if extraction
    # returned no observations for one of them.
    sites = pd.read_csv(SITES_FILE)[["Site_ID", "Client"]]
    out = sites.merge(out.drop(columns="Client"), on="Site_ID", how="left")
    out["years_used"] = out["years_used"].fillna(0).astype(int)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT_FILE, index=False)

    successful = out["rainfall_RP100_mm"].notna()
    successful_n = int(successful.sum())
    insufficient_n = len(out) - successful_n
    print(f"Wrote {len(out)} site rows to {OUTPUT_FILE}")
    print(f"Successful fits: {successful_n}")
    print(f"Insufficient-data/null fits: {insufficient_n} (minimum {MIN_RECORD_YEARS} years)")
    if successful_n:
        stats = out.loc[successful, "rainfall_RP100_mm"].agg(["min", "median", "max"])
        print("RP100 summary (mm):")
        print(stats.to_string())

    valid = out.loc[successful]
    ordering_violations = int((
        (valid["rainfall_RP10_mm"] >= valid["rainfall_RP100_mm"])
        | (valid["rainfall_RP100_mm"] >= valid["rainfall_RP500_mm"])
    ).sum())
    print(f"\n=== CHECK A: RP10 < RP100 < RP500 ===")
    print(f"Ordering violations: {ordering_violations}/{successful_n}")
    print_plausibility_check(out)


if __name__ == "__main__":
    main()
