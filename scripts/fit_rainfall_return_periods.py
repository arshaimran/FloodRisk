"""Fit rainfall return periods from CHIRPS annual daily maxima.

Return-period estimates are used for dashboard display only, not risk scoring.

A simple plausibility check is applied to the RP100 estimate:
    RP100 <= 3 * observed annual maximum  -> Stable
    otherwise                              -> Unstable - not displayed

Unstable and insufficient-data sites have null return-period values.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import genextreme


BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = BASE_DIR / "outputs" / "annual_max_daily_rainfall_chirps.csv"
SITES_FILE = BASE_DIR / "data" / "sites_input.csv"
OUTPUT_FILE = BASE_DIR / "outputs" / "rainfall_return_periods_chirps.csv"

MIN_RECORD_YEARS = 15
RETURN_PERIODS = (10, 100)


def return_level(values, period):
    """Fit a GEV distribution and return the requested rainfall return level."""
    shape, location, scale = genextreme.fit(values)

    probability = 1 - 1 / period

    return float(
        genextreme.ppf(
            probability,
            shape,
            loc=location,
            scale=scale,
        )
    )


def fit_site(group):
    """Fit one site's rainfall return periods."""

    values = pd.to_numeric(
        group["annual_max_daily_rainfall_mm"],
        errors="coerce",
    ).dropna()

    record_years = len(values)

    result = {
        "Site_ID": group["Site_ID"].iloc[0],
        "Client": group["Client"].iloc[0],
        "years_used": record_years,
        "observed_annual_max_mm": np.nan,
        "rainfall_RP10_mm": np.nan,
        "rainfall_RP100_mm": np.nan,
        "rainfall_fit_status": "Insufficient data",
    }

    # Not enough years to fit a meaningful distribution.
    if record_years < MIN_RECORD_YEARS:
        return result

    observed_max = float(values.max())

    rp10 = return_level(values, 10)
    rp100 = return_level(values, 100)

    result["observed_annual_max_mm"] = observed_max

    # Simple plausibility check requested for dashboard display.
    if np.isfinite(rp100) and rp100 <= 3 * observed_max:
        result["rainfall_RP10_mm"] = rp10
        result["rainfall_RP100_mm"] = rp100
        result["rainfall_fit_status"] = "Stable"
    else:
        result["rainfall_fit_status"] = "Unstable - not displayed"

    return result


def main():

    annual = pd.read_csv(INPUT_FILE)

    required = {
        "Site_ID",
        "Client",
        "year",
        "annual_max_daily_rainfall_mm",
    }

    missing = required - set(annual.columns)

    if missing:
        raise ValueError(
            f"{INPUT_FILE.name} is missing required columns: {sorted(missing)}"
        )

    print("==============================================")
    print("RAINFALL RETURN PERIOD FIT")
    print("==============================================")
    print(f"Input rows: {len(annual):,}")
    print(f"Unique sites: {annual['Site_ID'].nunique():,}")
    print()

    results = []

    grouped = annual.groupby("Site_ID", sort=False)
    total_groups = len(grouped)

    for i, (_, group) in enumerate(grouped, start=1):

        results.append(fit_site(group))

        # Progress output every 50 sites
        if i % 50 == 0 or i == total_groups:
            print(f"Fitted {i:,}/{total_groups:,} rainfall series...")

    out = pd.DataFrame(results)

    # Preserve one output row for every current portfolio site.
    sites = pd.read_csv(SITES_FILE)[["Site_ID", "Client"]]

    out = sites.merge(
        out.drop(columns="Client"),
        on="Site_ID",
        how="left",
    )

    out["years_used"] = out["years_used"].fillna(0).astype(int)

    # Any site that somehow has no status gets treated as insufficient data.
    out["rainfall_fit_status"] = out["rainfall_fit_status"].fillna(
        "Insufficient data"
    )

    # Ensure unstable / insufficient sites never expose raw RP values.
    invalid_status = out["rainfall_fit_status"].isin(
        [
            "Unstable - not displayed",
            "Insufficient data",
        ]
    )

    out.loc[
        invalid_status,
        ["rainfall_RP10_mm", "rainfall_RP100_mm"],
    ] = np.nan

    # Only keep the requested display columns.
    output_columns = [
        "Site_ID",
        "Client",
        "years_used",
        "observed_annual_max_mm",
        "rainfall_RP10_mm",
        "rainfall_RP100_mm",
        "rainfall_fit_status",
    ]

    out = out[output_columns]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    out.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    # --------------------------------------------------
    # FINAL REPORT
    # --------------------------------------------------

    stable = int(
        (out["rainfall_fit_status"] == "Stable").sum()
    )

    unstable = int(
        (out["rainfall_fit_status"] == "Unstable - not displayed").sum()
    )

    insufficient = int(
        (out["rainfall_fit_status"] == "Insufficient data").sum()
    )

    print()
    print("==============================================")
    print("FIT SUMMARY")
    print("==============================================")

    print(f"Output site rows: {len(out):,}")
    print(f"Stable: {stable:,}")
    print(f"Unstable - not displayed: {unstable:,}")
    print(f"Insufficient data: {insufficient:,}")

    print()
    print("==============================================")
    print("RAIN FALL FIT STATUS")
    print("==============================================")

    print(
        out["rainfall_fit_status"]
        .value_counts()
        .to_string()
    )

    print()
    print("Saved rainfall return-period data to:")
    print(OUTPUT_FILE)

    print()
    print("Done.")


if __name__ == "__main__":
    main()