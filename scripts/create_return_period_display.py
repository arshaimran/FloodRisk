"""
Create site-level return-period display bands.

This script DOES NOT modify risk scoring.

It consolidates existing fluvial, coastal and pluvial
hazard recurrence information into simple display labels
for the dashboard.

Output:
    outputs/return_period_display.csv


FLUVIAL
-------
Uses JRC modeled river flood scenarios:

    RP10
    RP100
    RP500

The lowest scenario showing positive modeled flooding is
used to assign a scenario interval:

    0-10 years
    10-100 years
    100-500 years
    No modeled flooding

These are modeled scenario intervals, not statistically
estimated site-specific return periods.


COASTAL
-------
Uses Aqueduct/GTSR modeled coastal flood scenarios:

    RP2
    RP10
    RP100
    RP1000

The lowest scenario showing positive modeled inundation
is displayed.

These are scenario thresholds, not empirical return periods.


PLUVIAL
-------
Uses the previously calculated CHIRPS/GEV rainfall
return-period classification from:

    outputs/rainfall_return_periods_chirps.csv

That file performs the statistical analysis separately.
This script simply carries its final rainfall recurrence
band into the unified display output.


IMPORTANT
---------
All values produced here are DISPLAY-ONLY.

This script does NOT affect:

    - risk scoring
    - final risk tiers
    - site flagging
    - hazard extraction
    - underlying portfolio logic

The output is intended only for communicating hazard
recurrence information consistently on the dashboard.
"""
from pathlib import Path

import numpy as np
import pandas as pd


BASE = Path(__file__).resolve().parent.parent

SITES_FILE = (
    BASE / "outputs" / "sites_scored.csv"
)

COASTAL_FILE = (
    BASE / "outputs" / "coastal_rp_samples.csv"
)

PLUVIAL_FILE = (
    BASE / "outputs" / "rainfall_return_periods_chirps.csv"
)

OUTPUT_FILE = (
    BASE / "outputs" / "return_period_display.csv"
)


# ------------------------------------------------------------
# FLUVIAL
# ------------------------------------------------------------


def classify_fluvial(row):
    """
    Assign a fluvial flood recurrence band based on the lowest
    JRC return-period scenario with modeled flooding.

    This is a modeled scenario interval, not an exact empirical
    site-specific return period.
    """

    rp10 = row.get("RP10_depth", np.nan)
    rp100 = row.get("RP100_depth", np.nan)
    rp500 = row.get("RP500_depth", np.nan)

    values = [rp10, rp100, rp500]

    if not any(pd.notna(v) for v in values):
        return "No data"

    # Flooding present even in the 10-year scenario
    if pd.notna(rp10) and rp10 > 0:
        return "0-10 years"

    # No flooding at RP10, but present at RP100
    if pd.notna(rp100) and rp100 > 0:
        return "10-100 years"

    # Only appears at the extreme RP500 scenario
    if pd.notna(rp500) and rp500 > 0:
        return "100-500 years"

    return "No modeled flooding"

# ------------------------------------------------------------
# COASTAL
# ------------------------------------------------------------

def classify_coastal(row):
    """
    Assign a coastal flood recurrence band based on the lowest
    Aqueduct/GTSR return-period scenario with modeled inundation.

    This is a modeled scenario interval, not an exact empirical
    site-specific return period.
    """

    rp2 = row.get(
        "coastal_RP2_depth_m",
        np.nan,
    )

    rp10 = row.get(
        "coastal_RP10_depth_m",
        np.nan,
    )

    rp100 = row.get(
        "coastal_RP100_depth_m",
        np.nan,
    )

    rp1000 = row.get(
        "coastal_RP1000_depth_m",
        np.nan,
    )

    values = [
        rp2,
        rp10,
        rp100,
        rp1000,
    ]

    # Site is outside available coastal model coverage
    if not any(pd.notna(v) for v in values):
        return "No data"

    # Flooding present in the most frequent available scenario
    if pd.notna(rp2) and rp2 > 0:
        return "0-2 years"

    # No flooding at RP2, but present at RP10
    if pd.notna(rp10) and rp10 > 0:
        return "2-10 years"

    # No flooding at lower scenarios, but present at RP100
    if pd.notna(rp100) and rp100 > 0:
        return "10-100 years"

    # Only appears in the most extreme RP1000 scenario
    if pd.notna(rp1000) and rp1000 > 0:
        return "100-1000 years"

    return "No modeled flooding"
# ------------------------------------------------------------
# PLUVIAL
# ------------------------------------------------------------

def classify_pluvial(row):
    """
    The rainfall script already determines the site's
    estimated rainfall return-period band.

    Simply use that classification here.
    """

    value = row.get(
        "rainfall_return_period_band"
    )

    if pd.isna(value):
        return "No data"

    return str(value)


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    print("==============================================")
    print("CREATE RETURN-PERIOD DISPLAY DATA")
    print("==============================================")

    sites = pd.read_csv(
        SITES_FILE
    )

    print(
        f"Sites: {len(sites):,}"
    )

    # --------------------------------------------------------
    # COASTAL
    # --------------------------------------------------------

    if COASTAL_FILE.exists():

        coastal = pd.read_csv(
            COASTAL_FILE
        )

        coastal_cols = [
            "Site_ID",
            "coastal_RP2_depth_m",
            "coastal_RP10_depth_m",
            "coastal_RP100_depth_m",
            "coastal_RP1000_depth_m",
        ]

        coastal_cols = [
            c
            for c in coastal_cols
            if c in coastal.columns
        ]

        df = sites.merge(
            coastal[coastal_cols],
            on="Site_ID",
            how="left",
        )

    else:

        print(
            "WARNING: coastal file not found."
        )

        df = sites.copy()

    # --------------------------------------------------------
    # PLUVIAL
    # --------------------------------------------------------

    if PLUVIAL_FILE.exists():

        pluvial = pd.read_csv(
            PLUVIAL_FILE
        )

        pluvial_cols = [
            "Site_ID",
            "rainfall_return_period_band",
        ]

        pluvial_cols = [
            c
            for c in pluvial_cols
            if c in pluvial.columns
        ]

        df = df.merge(
            pluvial[pluvial_cols],
            on="Site_ID",
            how="left",
        )

    else:

        print(
            "WARNING: rainfall RP file not found."
        )

    # --------------------------------------------------------
    # CLASSIFY
    # --------------------------------------------------------

    df["fluvial_return_period"] = (
        df.apply(
            classify_fluvial,
            axis=1,
        )
    )

    df["coastal_return_period"] = (
        df.apply(
            classify_coastal,
            axis=1,
        )
    )

    df["pluvial_return_period"] = (
        df.apply(
            classify_pluvial,
            axis=1,
        )
    )

    # --------------------------------------------------------
    # KEEP ONLY DISPLAY DATA
    # --------------------------------------------------------

    display_columns = [
        "Site_ID",
        "Client",
        "fluvial_return_period",
        "coastal_return_period",
        "pluvial_return_period",
    ]

    out = df[
        [
            c
            for c in display_columns
            if c in df.columns
        ]
    ].copy()

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    out.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print("FLUVIAL")
    print(
        out[
            "fluvial_return_period"
        ]
        .value_counts()
        .to_string()
    )

    print()
    print("COASTAL")
    print(
        out[
            "coastal_return_period"
        ]
        .value_counts()
        .to_string()
    )

    print()
    print("PLUVIAL")
    print(
        out[
            "pluvial_return_period"
        ]
        .value_counts()
        .to_string()
    )

    print()
    print("Saved:")
    print(
        OUTPUT_FILE
    )

    print()
    print("Done.")


if __name__ == "__main__":
    main()