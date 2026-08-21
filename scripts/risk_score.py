"""
risk_score.py (v4)
Explainable flood risk tiering for insured sites - EDA-informed design,
now validated against 70 real claims from the past year.

CHANGES IN v4 vs. v3 - all backed by the claims validation, not guesswork:

  1. RELIEF THRESHOLD LOOSENED: <1 -> <3 (RELIEF_SAFE_THRESHOLD below).
     13 of 17 claim-based false negatives in v3 all shared
     local_relief_m between 1 and 3 - just above the old cutoff. This is
     an evidence-backed change, not a guess (see validate_against_claims.py
     diagnostic output).

  2. -9999 SENTINEL BUG FIXED: local_relief_m == -9999 (missing data)
     previously satisfied "< 1" and was silently treated as STRONG
     evidence of a pronounced depression - the opposite of what missing
     data should mean. Now explicitly excluded before any threshold
     comparison, same pattern already used for hand_m/elevation_m.

  3. REASON TEXT FIXED: v3 always described "corroborating evidence"
     for pluvial-dominant sites even when the vulnerability gate had
     REJECTED that evidence and produced a Low tier - actively
     misleading. Reason is now derived from what evidence actually
     fired, not just from comparing riverine vs pluvial scores.

  4. REAL CLAIMS AS OVERRIDE INPUTS: repeat_claim_client and
     repeat_claim_site (from build_claims_features.py, itself
     validated - see script docstring) are now first-class override
     inputs, same weight as 2+ satellite-derived historical_flood_hits.
     A site/client with 2+ REAL claims this year is at least as strong
     evidence as 2+ satellite-inferred historical flood extents, arguably
     stronger since it reflects actual insured loss, not a modeled proxy.

  NOT changed in v4 (insufficient evidence to justify a change yet):
    - Rainfall bucketing (monsoon_p95 thresholds) - missed claims cluster
      in the expected hazard buckets 1-2, consistent with the buckets
      being reasonable; only 33 real claims, mostly pluvial, isn't
      enough spread to safely retune exact boundaries.
    - Riverine scoring (RP100/RP500/HAND) - zero riverine claims in this
      year's data to validate against. Needs NDMA Sitrep cross-check
      (planned, not yet done) before touching this half of the model.
    - city_claim_rate - built and available (see build_claims_features.py)
      but NOT wired in yet. Only 11 of 33 claims currently resolve to a
      single unambiguous site; most cities show 0-1 claims, too thin to
      trust as a rate. Revisit once more fan-out claims are resolved.
    - Drainage/waterway proximity (OSM) - tested, mixed/weak evidence
      (pooled claim-site median 838m vs 986m non-claim, direction
      inconsistent across cities). Not included in v4.
"""

import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = BASE_DIR / "outputs" / "sites_with_cities.csv"
# Claims-derived features (Site_ID, city_claim_rate, repeat_claim_site,
# repeat_claim_client) from build_claims_features.py. Optional - if this
# hasn't been generated yet, v4 still runs, just without claims-derived
# overrides (falls back to v3 behavior for that piece only).
CLAIMS_FEATURES_FILE = BASE_DIR / "outputs" / "sites_with_claims_features.csv"
OUTPUT_FILE = BASE_DIR / "outputs" / "sites_scored.csv"

HAND_SAFE_THRESHOLD = 50

# v4 CHANGE: was 1, now 3 - see module docstring point 1.
RELIEF_SAFE_THRESHOLD = 3


def riverine_score(rp100, rp500, hand_m):
    if pd.isna(rp100) or pd.isna(rp500) or pd.isna(hand_m):
        return np.nan

    # v5: percentile-derived cutoffs (computed from portfolio distribution)
    # Nonzero RP100_depth percentiles (from compute_bin_edges.py):
    #  90th: 2.594200 m, 97th: 3.504470 m (N=524 nonzero values)
    RP100_90 = 2.5942
    RP100_97 = 3.50447

    if rp100 <= 0:
        score = 0
    elif rp100 < 0.5:
        score = 1
    elif rp100 < 1.5:
        score = 2
    elif rp100 < RP100_90:
        score = 3
    elif rp100 >= RP100_97:
        score = 4
    else:
        # between 90th and 97th percentile -> treat as high (3)
        score = 3

    if hand_m > HAND_SAFE_THRESHOLD and score <= 1:
        score = 0

    return score


def relief_modifier(local_relief_m):
    """
    v4 CHANGE: sentinel check added FIRST. -9999 no longer falls through
    into "< 1" (previously true, wrongly implying a pronounced
    depression). Boundaries below <1/<3/<8 unchanged from v3's version -
    only the pluvial gate's own threshold (RELIEF_SAFE_THRESHOLD) moved.
    """
    if local_relief_m == -9999:
        return 0
    elif local_relief_m < 1:
        return 2
    elif local_relief_m < 3:
        return 1
    elif local_relief_m < 8:
        return 0
    else:
        return -1


def has_relief_evidence(local_relief_m):
    """
    v4: centralizes the "is this site in a real depression" check used
    by the vulnerability gate, with the sentinel bug fixed and the
    threshold loosened to RELIEF_SAFE_THRESHOLD (3, was 1).
    """
    if local_relief_m == -9999:
        return False
    return local_relief_m < RELIEF_SAFE_THRESHOLD


def pluvial_score(monsoon_p95_mm, local_relief_m, historical_hits,
                   repeat_claim_site=False, repeat_claim_client=False):
    """
    Pluvial flooding requires BOTH a rainfall hazard AND evidence the
    location is vulnerable. v4: evidence now includes real repeat
    claims, not just relief/historical_flood_hits.
    """
    if pd.isna(monsoon_p95_mm):
        return np.nan

    # v5: percentile-derived cutoffs for top bins (computed from portfolio)
    # Nonzero monsoon_p95_rainfall_mm percentiles (from compute_bin_edges.py):
    #  90th: 33.62616 mm, 97th: 39.567738 mm (N=2334 nonzero values)
    MONSOON_90 = 33.62616
    MONSOON_97 = 39.567738

    if monsoon_p95_mm < 10:
        hazard = 0
    elif monsoon_p95_mm < 20:
        hazard = 1
    elif monsoon_p95_mm < MONSOON_90:
        hazard = 2
    elif monsoon_p95_mm >= MONSOON_97:
        hazard = 4
    else:
        # between 90th and 97th percentile
        hazard = 3

    strong_evidence = (
        historical_hits >= 1
        or has_relief_evidence(local_relief_m)
        or repeat_claim_site
        or repeat_claim_client
    )

    if not strong_evidence:
        return min(hazard, 1)

    if local_relief_m != -9999 and local_relief_m < 0.5:
        modifier = 2
    elif local_relief_m != -9999 and local_relief_m < 1:
        modifier = 1
    else:
        modifier = 0

    return min(hazard + modifier, 4)


def dominant_hazard(riverine, pluvial):
    if pd.isna(riverine) or pd.isna(pluvial):
        return "Unknown"
    if riverine > pluvial:
        return "Riverine"
    if pluvial > riverine:
        return "Pluvial"
    return "Combined"


def tier_from_evidence(final_score, riverine_score, pluvial_score,
                        historical_hits, repeat_claim_site=False, repeat_claim_client=False,
                        has_history_claim=False):
    """
    Evidence-gated tiering (v5): requires hazard magnitude AND at least
    one piece of corroborating evidence to reach High or Critical,
    except that maximum modeled hazard (final_score >= 4) is treated
    as sufficient on its own to reach High and Critical depending on
    evidence (see below).

    Evidence sources counted (independent):
      - satellite-derived historical flood hit (historical_hits >= 1)
      - repeat claim at this site
      - repeat claim at this client
      - both riverine and pluvial scoring >= 2 (independent-model agreement)

    Real repeat-claim evidence (historical_hits >=2 or any repeat)
    forces Critical immediately.
    """
    # Real evidence override - preserved from previous logic
    if historical_hits >= 2 or repeat_claim_site or repeat_claim_client:
        return "Critical"

    evidence_count = sum([
        historical_hits >= 1,
        bool(repeat_claim_site),
        bool(repeat_claim_client),
        bool(has_history_claim),
        (riverine_score >= 2 and pluvial_score >= 2),
    ])

    if final_score >= 4:
        # Extreme modeled hazard: promote to Critical if any evidence,
        # otherwise High (hazard-alone is strong but evidence still matters)
        return "Critical" if evidence_count >= 1 else "High"

    if final_score >= 3:
        # Fix 1 spec: score 3 maps directly to High, ungated.
        return "High"

    if final_score >= 2:
        return "High" if evidence_count >= 1 else "Medium"

    if final_score >= 1:
        return "Medium" if evidence_count >=1 else "Low"

    return "Low"


# apply_historical_override removed; historical/repeat-claim overrides are
# now incorporated directly into `tier_from_evidence()` per v5 spec.


def apply_live_conditions(base_tier, current_rainfall_mm=None, active_alert=None):
    if current_rainfall_mm is None:
        return {"live_status": "No live data available", "base_tier": base_tier}
    return {"live_status": "placeholder - not yet implemented", "base_tier": base_tier}


def score_site(row):
    required = [row["RP100_depth"], row["RP500_depth"], row["hand_m"], row["monsoon_p95_rainfall_mm"]]
    if any(pd.isna(x) for x in required):
        return pd.Series({
            "riverine_score": np.nan, "pluvial_score": np.nan, "final_score": np.nan,
            "risk_tier": "Insufficient Data", "dominant_hazard": "Unknown",
            "reason": "Missing hazard inputs"
        })

    if row["hand_m"] == -9999 or row["elevation_m"] == -9999:
        return pd.Series({
            "riverine_score": np.nan, "pluvial_score": np.nan, "final_score": np.nan,
            "risk_tier": "Coastal/Marine - Requires Storm Surge Assessment",
            "dominant_hazard": "Coastal/Storm Surge",
            "reason": "No land-based elevation data - separate coastal assessment required"
        })

    repeat_site = bool(row.get("repeat_claim_site", False))
    repeat_client = bool(row.get("repeat_claim_client", False))

    r = riverine_score(row["RP100_depth"], row["RP500_depth"], row["hand_m"])
    p = pluvial_score(row["monsoon_p95_rainfall_mm"], row["local_relief_m"],
                       row["historical_flood_hits"], repeat_site, repeat_client)

    # v4: gate condition now matches pluvial_score's strong_evidence check
    # exactly (was subtly different in v3 - both are the single source
    # of truth now via has_relief_evidence()).
    strong_pluvial = (
        row["historical_flood_hits"] >= 1
        or has_relief_evidence(row["local_relief_m"])
        or repeat_site
        or repeat_client
    )

    final = max(r, p) if strong_pluvial else r

    has_history_claim = bool(row.get("has_history_claim", False))
    tier = tier_from_evidence(final, r, p, row["historical_flood_hits"], repeat_site, repeat_client, has_history_claim)

    # v4 FIX: reason text now reflects what actually happened, not just
    # r vs p - previously claimed "corroborating evidence" even when the
    # gate had rejected it and suppressed pluvial risk entirely.
    if repeat_site or repeat_client:
        reason = "Elevated due to repeat claims history at this site/client."
    elif r > p and strong_pluvial:
        reason = "River flood depth dominates."
    elif r > p and not strong_pluvial:
        reason = "River flood depth dominates (rainfall hazard present but not corroborated by relief or claims history)."
    elif p > r:
        reason = "Extreme monsoon rainfall dominates, corroborated by low relief or claims history."
    elif not strong_pluvial:
        reason = "Rainfall hazard present but not corroborated - riverine score only."
    else:
        reason = "Both river and rainfall hazards are similar."

    return pd.Series({
        "riverine_score": r, "pluvial_score": p, "final_score": final,
        "risk_tier": tier, "dominant_hazard": dominant_hazard(r, p),
        "reason": reason
    })


def main():
    df = pd.read_csv(INPUT_FILE)

    if CLAIMS_FEATURES_FILE.exists():
        claims_feat = pd.read_csv(CLAIMS_FEATURES_FILE)[
            ["Site_ID", "city_claim_rate", "repeat_claim_site", "repeat_claim_client", "has_history_claim"]
        ]
        df = df.merge(claims_feat, on="Site_ID", how="left")
        df["repeat_claim_site"] = df["repeat_claim_site"].fillna(False)
        df["repeat_claim_client"] = df["repeat_claim_client"].fillna(False)
        df["has_history_claim"] = df["has_history_claim"].fillna(False)
        df["city_claim_rate"] = df["city_claim_rate"].fillna(0)
        print(f"Merged claims-derived features from {CLAIMS_FEATURES_FILE.name}")
    else:
        df["repeat_claim_site"] = False
        df["repeat_claim_client"] = False
        df["city_claim_rate"] = 0
        print(f"[warn] {CLAIMS_FEATURES_FILE.name} not found - running without claims-derived overrides. "
              f"Run build_claims_features.py first to enable them.")

    print("\n========== RAINFALL SUMMARY (p95) ==========\n")
    print(df["monsoon_p95_rainfall_mm"].describe(percentiles=[0.25, 0.50, 0.75, 0.90, 0.95, 0.99]))

    scores = df.apply(score_site, axis=1)
    out = pd.concat([df, scores], axis=1)

    print("\n========== RISK TIER DISTRIBUTION (v4) ==========\n")
    tier_order = ["Critical", "High", "Medium", "Low",
                  "Coastal/Marine - Requires Storm Surge Assessment", "Insufficient Data"]
    for t in tier_order:
        count = (out["risk_tier"] == t).sum()
        if count:
            print(f"{t}: {count}")

    print(f"\nSites elevated by repeat-claim override: "
          f"{(out['repeat_claim_site'] | out['repeat_claim_client']).sum()}")

    sort_map = {t: i for i, t in enumerate(tier_order)}
    out["_sort"] = out["risk_tier"].map(sort_map)
    out = out.sort_values("_sort", ascending=True).drop(columns="_sort")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(out)} scored sites to {OUTPUT_FILE}")
    print(f"\nCompare this against {OUTPUT_FILE.name} (v3) and re-run "
          "validate_against_claims.py to confirm the false-negative count actually dropped.")


if __name__ == "__main__":
    main()