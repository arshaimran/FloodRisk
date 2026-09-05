"""
Estimate severe rainfall return-period bands from CHIRPS annual maxima.

DISPLAY ONLY.

This script does NOT affect:
    - risk scoring
    - risk tiers
    - site flagging
    - hazard extraction
    - any underlying portfolio logic

It only creates a rainfall recurrence estimate for display
on the dashboard.

Method:
    1. Use each site's annual maximum daily rainfall series.
    2. Fit a GEV distribution.
    3. Calculate rainfall thresholds for fixed return periods:
       10, 50, 100, 250 and 500 years.
    4. Compare the site's observed historical maximum rainfall
       against those thresholds.
    5. Assign one display band.

Output bands:
    0-10 years
    10-50 years
    50-100 years
    100-250 years
    250-500 years
    500+ years
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import genextreme


BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    BASE_DIR
    / "outputs"
    / "annual_max_daily_rainfall_chirps.csv"
)

SITES_FILE = (
    BASE_DIR
    / "data"
    / "sites_input.csv"
)

OUTPUT_FILE = (
    BASE_DIR
    / "outputs"
    / "rainfall_return_periods_chirps.csv"
)


MIN_RECORD_YEARS = 15


def return_level(shape, location, scale, period):
    """Calculate rainfall magnitude for a fixed return period."""

    probability = 1 - (1 / period)

    return float(
        genextreme.ppf(
            probability,
            shape,
            loc=location,
            scale=scale,
        )
    )


def classify_band(
    observed_max,
    rp10,
    rp50,
    rp100,
    rp250,
    rp500,
):
    """Assign a bounded return-period display band."""

    if observed_max < rp10:
        return "0-10 years"

    if observed_max < rp50:
        return "10-50 years"

    if observed_max < rp100:
        return "50-100 years"

    if observed_max < rp250:
        return "100-250 years"

    if observed_max < rp500:
        return "250-500 years"

    return "500+ years"


def fit_site(group):
    """Fit GEV to one site's annual rainfall maxima."""

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
        "rainfall_return_period_band": "Insufficient data",
        "rainfall_fit_status": "Insufficient data",
    }

    if record_years < MIN_RECORD_YEARS:
        return result

    observed_max = float(values.max())

    result["observed_annual_max_mm"] = observed_max

    try:

        shape, location, scale = genextreme.fit(values)

        rp10 = return_level(
            shape,
            location,
            scale,
            10,
        )

        rp50 = return_level(
            shape,
            location,
            scale,
            50,
        )

        rp100 = return_level(
            shape,
            location,
            scale,
            100,
        )

        rp250 = return_level(
            shape,
            location,
            scale,
            250,
        )

        rp500 = return_level(
            shape,
            location,
            scale,
            500,
        )

    except Exception:

        result["rainfall_fit_status"] = "Fit failed"

        return result

    # Check all calculated values are valid.
    thresholds = [
        rp10,
        rp50,
        rp100,
        rp250,
        rp500,
    ]

    if not all(np.isfinite(x) for x in thresholds):

        result["rainfall_fit_status"] = "Invalid fit"

        return result

    # Return levels must increase with return period.
    if not (
        rp10 < rp50 < rp100 < rp250 < rp500
    ):

        result["rainfall_fit_status"] = "Invalid fit"

        return result

    # Basic plausibility check.
    # Reject extremely unstable extrapolations.
    if rp500 > observed_max * 10:

        result["rainfall_fit_status"] = "Unstable fit"

        return result

    result["rainfall_return_period_band"] = classify_band(
        observed_max,
        rp10,
        rp50,
        rp100,
        rp250,
        rp500,
    )

    result["rainfall_fit_status"] = "Stable"

    return result


def main():

    print("=" * 55)
    print("RAINFALL RETURN PERIOD BAND ESTIMATION")
    print("=" * 55)

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
            f"Missing required columns: {sorted(missing)}"
        )

    print(f"Input rows: {len(annual):,}")
    print(
        f"Unique sites: "
        f"{annual['Site_ID'].nunique():,}"
    )

    results = []

    grouped = annual.groupby(
        "Site_ID",
        sort=False,
    )

    total_sites = len(grouped)

    for i, (_, group) in enumerate(
        grouped,
        start=1,
    ):

        results.append(
            fit_site(group)
        )

        if i % 100 == 0 or i == total_sites:

            print(
                f"Processed "
                f"{i:,}/{total_sites:,} sites"
            )

    out = pd.DataFrame(results)

    # Preserve all portfolio sites.
    sites = pd.read_csv(
        SITES_FILE
    )[[
        "Site_ID",
        "Client",
    ]]

    out = sites.merge(

        out.drop(
            columns="Client"
        ),

        on="Site_ID",

        how="left",

    )

    # Fill missing sites.
    out["years_used"] = (
        out["years_used"]
        .fillna(0)
        .astype(int)
    )

    out["rainfall_fit_status"] = (
        out["rainfall_fit_status"]
        .fillna("Insufficient data")
    )

    out["rainfall_return_period_band"] = (
        out["rainfall_return_period_band"]
        .fillna("Insufficient data")
    )

    # Final output.
    output_columns = [

        "Site_ID",

        "Client",

        "years_used",

        "observed_annual_max_mm",

        "rainfall_return_period_band",

        "rainfall_fit_status",

    ]

    out = out[output_columns]

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    out.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print()
    print("=" * 55)
    print("RETURN PERIOD BAND SUMMARY")
    print("=" * 55)

    print()

    print(
        out[
            "rainfall_return_period_band"
        ]
        .value_counts(
            dropna=False
        )
        .to_string()
    )

    print()

    print("FIT STATUS")

    print(
        out[
            "rainfall_fit_status"
        ]
        .value_counts(
            dropna=False
        )
        .to_string()
    )

    print()

    print(f"Saved: {OUTPUT_FILE}")

    print()
    print("Done.")


if __name__ == "__main__":
    main()