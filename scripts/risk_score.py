"""
risk_score.py
Explainable flood risk tiering for insured sites - EDA-informed design.

Key structural decisions from the EDA (see eda.py / eda_geo.py output):
  - RP100/RP10/RP500 depth are 0.91-0.99 correlated - RP100 used as the
    primary riverine signal; RP500 only as a tail-risk modifier.
  - Riverine depth (JRC) and monsoon rainfall are NEGATIVELY correlated
    (-0.30 to -0.37) - two geographically distinct flood mechanisms
    (Indus-basin riverine flooding in Sindh vs. orographic monsoon/
    pluvial risk in northern hill areas). Score independently, take MAX.
  - HAND correlates only -0.06 linearly with depth - the real
    relationship is a threshold/floor effect, not a smooth scale. Used
    as a soft suppressor (only when RP100 is already low), not a hard
    override of a genuinely high modeled depth.
  - monsoon_max was tried first and rejected: as the max of ~2,440
    daily observations (20 years x ~122 monsoon days), it's an extreme-
    value statistic - nearly every site in Pakistan has SOME freak rain
    day on record, so it collapsed almost the entire portfolio into
    "heavy/very heavy" regardless of that site's typical conditions
    (median came out at 85mm, already category 2). Switched to
    monsoon_p95 - reflects typical severe-day intensity, not a one-off
    record, and its spread (per EDA) actually differentiates sites.
    Thresholds below are derived from this portfolio's own percentiles,
    not an external scale - re-check against
    df["monsoon_p95_rainfall_mm"].describe(percentiles=[.25,.5,.75,.9,.95,.99])
    whenever the site list changes meaningfully.
  - Only 1.8% of sites have any historical_flood_hits - too sparse to
    matter as an additive term. Used as an override/boost instead.
"""

import pandas as pd
from pathlib import Path
import numpy as np


BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = BASE_DIR / "outputs" / "sites_with_cities.csv"
OUTPUT_FILE = BASE_DIR / "outputs" / "sites_scored.csv"

# HAND threshold above which riverine flooding is treated as unlikely -
# only suppresses an ALREADY-LOW modeled depth, never overrides a
# genuinely high RP100 value (see riverine_score()).
HAND_SAFE_THRESHOLD = 50


def riverine_score(rp100, rp500, hand_m):
    if pd.isna(rp100) or pd.isna(rp500) or pd.isna(hand_m):
        return np.nan

    if rp100 <= 0:
        score = 0
    elif rp100 < 0.5:
        score = 1
    elif rp100 < 1.5:
        score = 2
    elif rp100 < 3.0:
        score = 3
    else:
        score = 4

    # HAND only suppresses an already-marginal score - never zeroes out
    # a genuinely high JRC-modeled depth (e.g. HAND=55, RP100=4.2m stays
    # at score 4; HAND=55, RP100=0.3m gets suppressed to 0).
    if hand_m > HAND_SAFE_THRESHOLD and score <= 1:
        score = 0

    return score



def relief_modifier(local_relief_m):
    if local_relief_m == -9999:
        return 0
    elif local_relief_m < 1:
        return 2       # sits in a pronounced local depression
    elif local_relief_m < 3:
        return 1        # mildly low relative to surroundings
    elif local_relief_m < 8:
        return 0        # unremarkable
    else:
        return -1        # sits on a genuine local rise - modest risk reduction


def pluvial_score(monsoon_p95_mm, local_relief_m):
    if pd.isna(monsoon_p95_mm):
        return np.nan

    if monsoon_p95_mm < 10:
        base = 0
    elif monsoon_p95_mm < 20:
        base = 1
    elif monsoon_p95_mm < 33:
        base = 2
    elif monsoon_p95_mm < 45:
        base = 3
    else:
        base = 4

    base = base + relief_modifier(local_relief_m)
    return max(0, min(base, 4))


def dominant_hazard(riverine, pluvial):
    if pd.isna(riverine) or pd.isna(pluvial):
        return "Unknown"
    if riverine > pluvial:
        return "Riverine"
    if pluvial > riverine:
        return "Pluvial"
    return "Combined"


def tier_from_score(score):
    if score >= 4:
        return "Critical"
    elif score >= 2:
        return "High"
    elif score >= 1:
        return "Medium"
    else:
        return "Low"


def apply_historical_override(tier, historical_hits):
    """Observed past flooding overrides the model-based tier upward."""
    order = ["Low", "Medium", "High", "Critical"]
    if historical_hits >= 2:
        return "Critical"
    elif historical_hits >= 1:
        idx = order.index(tier)
        return order[min(idx + 1, len(order) - 1)]
    return tier


def apply_live_conditions(base_tier, current_rainfall_mm=None, active_alert=None):
    """
    Placeholder for the live-conditions overlay (Phase 2, once weather.py
    and the dashboard exist). Does NOT mutate the base tier.
    """
    if current_rainfall_mm is None:
        return {"live_status": "No live data available", "base_tier": base_tier}
    return {"live_status": "placeholder - not yet implemented", "base_tier": base_tier}


def score_site(row):
    required = [
        row["RP100_depth"], row["RP500_depth"],
        row["hand_m"], row["monsoon_p95_rainfall_mm"]
    ]

    if any(pd.isna(x) for x in required):
        return pd.Series({
            "riverine_score": np.nan, "pluvial_score": np.nan, "final_score": np.nan,
            "risk_tier": "Insufficient Data", "dominant_hazard": "Unknown",
            "reason": "Missing hazard inputs"
        })

    # FIX: -9999 is a sentinel, not NaN - the isna() check above doesn't
    # catch it. Route coastal/marine sites here explicitly, before they
    # can reach riverine_score() with a nonsensical hand_m value.
    if row["hand_m"] == -9999 or row["elevation_m"] == -9999:
        return pd.Series({
            "riverine_score": np.nan, "pluvial_score": np.nan, "final_score": np.nan,
            "risk_tier": "Coastal/Marine - Requires Storm Surge Assessment",
            "dominant_hazard": "Coastal/Storm Surge",
            "reason": "No land-based elevation data - separate coastal assessment required"
        })

    r = riverine_score(row["RP100_depth"], row["RP500_depth"], row["hand_m"])
    p = pluvial_score(row["monsoon_p95_rainfall_mm"], row["local_relief_m"])
    final = max(r, p)

    tier = tier_from_score(final)
    tier = apply_historical_override(tier, row["historical_flood_hits"])

    if r > p:
        reason = "River flood depth dominates."
    elif p > r:
        reason = "Extreme monsoon rainfall dominates."
    else:
        reason = "Both river and rainfall hazards are similar."

    return pd.Series({
        "riverine_score": r, "pluvial_score": p, "final_score": final,
        "risk_tier": tier, "dominant_hazard": dominant_hazard(r, p),
        "reason": reason
    })


def main():
    df = pd.read_csv(INPUT_FILE)

    print("\n========== RAINFALL SUMMARY (p95) ==========\n")
    print(df["monsoon_p95_rainfall_mm"].describe(percentiles=[0.25, 0.50, 0.75, 0.90, 0.95, 0.99]))

    scores = df.apply(score_site, axis=1)
    out = pd.concat([df, scores], axis=1)

    print("\n========== RIVERINE SCORE DISTRIBUTION ==========\n")
    print(scores["riverine_score"].value_counts().sort_index())

    print("\n========== PLUVIAL SCORE DISTRIBUTION ==========\n")
    print(scores["pluvial_score"].value_counts().sort_index())

    print("\n========== FINAL SCORE DISTRIBUTION ==========\n")
    print(scores["final_score"].value_counts().sort_index())

    tier_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3,
                  "Coastal/Marine - Requires Storm Surge Assessment": 4,
                  "Insufficient Data": 5}
    out['_sort'] = out['risk_tier'].map(tier_order)
    out = out.sort_values(['_sort', 'net_sum_insured'], ascending=[True, False]).drop(columns='_sort')

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT_FILE, index=False)

    print("\n========== RISK TIER DISTRIBUTION ==========\n")
    print(out['risk_tier'].value_counts())

    print("\nDominant hazard distribution\n")
    print(out["dominant_hazard"].value_counts())

    print("\nAverage RP100 depth by tier (should increase monotonically Low->Critical)\n")
    print(out.groupby("risk_tier")["RP100_depth"].mean())

    print(f"\nSaved {len(out)} scored sites to {OUTPUT_FILE}")

    print("\n=== Sanity check: riverine vs pluvial dominance ===")
    print("Top 5 by riverine_score:")
    print(out.nlargest(5, 'riverine_score')[['Client', 'riverine_score', 'pluvial_score', 'risk_tier']])
    print("\nTop 5 by pluvial_score:")
    print(out.nlargest(5, 'pluvial_score')[['Client', 'riverine_score', 'pluvial_score', 'risk_tier']])

    print(f"\nCoastal/Marine sites flagged: {(out['risk_tier'] == 'Coastal/Marine - Requires Storm Surge Assessment').sum()}")


if __name__ == "__main__":
    main()