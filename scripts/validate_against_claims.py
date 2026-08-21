"""
validate_against_claims.py
Compares model risk tiers against real claims history to sanity-check
calibration. Run this locally against your actual files - nothing here
needs to leave your machine.

Requires: pandas, rapidfuzz
    pip install pandas rapidfuzz --break-system-packages

Usage:
    python validate_against_claims.py

Uses explicit project-root paths:
    sites_scored.csv   - your model output
    claims_history_to_2023.csv - historical claims only, with a
                                 'flood_relevant' column
                          you've manually added (Yes/No/Maybe from Step 1)

Output:
    claims_matched_history.csv   - every claim with matched site(s) + tier
    unmatched_claims_history.csv - claims that couldn't be confidently matched
                                 (needs manual resolution)
    validation_summary_history.txt - the actual numbers you care about
"""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd
from rapidfuzz import process, fuzz
import project_paths as paths

MATCH_THRESHOLD = 85  # fuzzy match confidence cutoff (0-100) - below this,
                       # goes to the explicit unmatched output for manual review
                       # rather than being silently trusted


def normalize(name):
    """Rough cleanup so fuzzy matching isn't thrown off by punctuation/case."""
    if pd.isna(name):
        return ""
    return (
        str(name).upper()
        .replace("(PVT.)", "").replace("(PVT)", "")
        .replace("(PRIVATE)", "").replace("LIMITED", "")
        .replace(".", "").replace(",", "")
        .strip()
    )


def main():
    paths.ensure_outputs()
    sites = pd.read_csv(paths.SITES_FILE)
    claims = pd.read_csv(paths.CLAIMS_FILE)

    if "flood_relevant" not in claims.columns:
        print("WARNING: no 'flood_relevant' column found - did you do Step 1?")
        print("Proceeding with all claims treated as relevant, but you should")
        print("add that column and re-run for a cleaner result.\n")
        claims["flood_relevant"] = "Yes"

    # Only validate against genuinely flood/water-relevant claims.
    # 'Maybe' is kept separate so you can eyeball it, not silently included.
    relevant = claims[claims["flood_relevant"].str.strip().str.lower() == "yes"].copy()
    maybe = claims[claims["flood_relevant"].str.strip().str.lower() == "maybe"].copy()
    print(f"Total claims: {len(claims)}")
    print(f"Flood-relevant (Yes): {len(relevant)}")
    print(f"Ambiguous (Maybe, excluded from main analysis): {len(maybe)}")

    sites["_client_norm"] = sites["Client"].apply(normalize)
    site_names = sites["_client_norm"].tolist()

    matched_rows = []
    unmatched_rows = []

    claim_col = "Insured/Participant" if "Insured/Participant" in relevant.columns else "Insured/Participant "
    loss_date_col = "Loss Date" if "Loss Date" in relevant.columns else None
    if loss_date_col is None:
        raise ValueError(f"Expected a 'Loss Date' column in {paths.CLAIMS_FILE.name}")

    # Load manual resolutions if present. They map claim_key (client|Loss Date)
    # to a specific Site_ID and will be used to short-circuit fan-out.
    def load_manual_resolutions(client_col, loss_col):
        if not paths.MANUAL_RESOLUTIONS_FILE.exists():
            return None
        manual = pd.read_csv(paths.MANUAL_RESOLUTIONS_FILE, dtype=str)
        # handle possible trailing-space header in the CSV
        if client_col not in manual.columns and client_col.strip() in manual.columns:
            manual = manual.rename(columns={client_col.strip(): client_col})
        if loss_col not in manual.columns and loss_col.strip() in manual.columns:
            manual = manual.rename(columns={loss_col.strip(): loss_col})
        if "Site_ID" not in manual.columns:
            raise ValueError(f"{paths.MANUAL_RESOLUTIONS_FILE.name} must contain a Site_ID column")
        manual = manual[[client_col, loss_col, "Site_ID"]].copy()
        manual[client_col] = manual[client_col].astype(str).str.strip()
        manual[loss_col] = manual[loss_col].astype(str).str.strip()
        manual["claim_key"] = manual[client_col] + "|" + manual[loss_col]
        if manual["claim_key"].duplicated().any():
            dupes = manual[manual["claim_key"].duplicated(keep=False)]["claim_key"].unique()
            raise ValueError(f"Duplicate claim_key(s) found in {paths.MANUAL_RESOLUTIONS_FILE.name}: {list(dupes)}")
        return manual.set_index("claim_key")["Site_ID"]

    manual_resolutions = load_manual_resolutions(claim_col, loss_date_col)
    if manual_resolutions is not None:
        print(f"Loaded {manual_resolutions.index.nunique()} manual fanned-claim resolution(s) from {paths.MANUAL_RESOLUTIONS_FILE.name}")

    for _, claim in relevant.iterrows():
        claim_name_norm = normalize(claim[claim_col])
        # If there's a manual resolution for this exact claim (client + Loss Date),
        # prefer that Site_ID and avoid fuzzy fan-out.
        claim_key = f"{str(claim[claim_col]).strip()}|{str(claim[loss_date_col]).strip()}"
        resolved_site = None
        if manual_resolutions is not None and claim_key in manual_resolutions.index:
            resolved_site = manual_resolutions.loc[claim_key]

        if resolved_site is not None:
            # find that site in the portfolio
            site_row = sites[sites["Site_ID"] == resolved_site]
            if site_row.empty:
                # fallback to fuzzy matching if resolved Site_ID not in current portfolio
                resolved_site = None
            else:
                site_row = site_row.iloc[0]
                matched_rows.append({**claim.to_dict(),
                                     "matched_client_in_sites": site_row["Client"],
                                     "match_confidence": 100,
                                     "Site_ID": site_row["Site_ID"],
                                     "city": site_row["city"],
                                     "risk_tier": site_row["risk_tier"],
                                     "riverine_score": site_row["riverine_score"],
                                     "pluvial_score": site_row["pluvial_score"],
                                     "final_score": site_row["final_score"],
                                     "dominant_hazard": site_row["dominant_hazard"],
                                     "local_relief_m": site_row.get("local_relief_m"),
                                     "hand_m": site_row.get("hand_m"),
                                     "historical_flood_hits": site_row.get("historical_flood_hits"),
                                     "monsoon_p95_rainfall_mm": site_row.get("monsoon_p95_rainfall_mm"),
                                     "RP100_depth": site_row.get("RP100_depth")})
                continue

        # No manual resolution applied, do usual fuzzy matching
        best = process.extractOne(claim_name_norm, site_names, scorer=fuzz.token_sort_ratio)

        if best is None or best[1] < MATCH_THRESHOLD:
            unmatched_rows.append(claim)
            continue

        matched_client_norm = best[0]
        client_sites = sites[sites["_client_norm"] == matched_client_norm]

        for _, site_row in client_sites.iterrows():
            matched_rows.append({
                **claim.to_dict(),
                "matched_client_in_sites": site_row["Client"],
                "match_confidence": best[1],
                "Site_ID": site_row["Site_ID"],
                "city": site_row["city"],
                "risk_tier": site_row["risk_tier"],
                "riverine_score": site_row["riverine_score"],
                "pluvial_score": site_row["pluvial_score"],
                "final_score": site_row["final_score"],
                "dominant_hazard": site_row["dominant_hazard"],
                "local_relief_m": site_row.get("local_relief_m"),
                "hand_m": site_row.get("hand_m"),
                "historical_flood_hits": site_row.get("historical_flood_hits"),
                "monsoon_p95_rainfall_mm": site_row.get("monsoon_p95_rainfall_mm"),
                "RP100_depth": site_row.get("RP100_depth"),
            })

    matched_df = pd.DataFrame(matched_rows)
    unmatched_df = pd.DataFrame(unmatched_rows)

    # ---- Fan-out detection ----
    # A single claim can expand into many rows if the matched client has
    # many sites in the portfolio (e.g. "VARIOUS LOCATIONS" claims). That
    # inflates whichever tiers that client's OTHER, unaffected sites happen
    # to sit in - it's portfolio noise being counted as claim evidence.
    # We give each original claim a unique id so we can tell the difference
    # between "70 claims" and "however many rows they expanded into".
    if len(matched_df):
        matched_df["_claim_id"] = matched_df.apply(
            lambda r: f"{r.get('Loss Date','')}|{r.get(claim_col,'')}", axis=1
        )
        fanout_counts = matched_df.groupby("_claim_id").size()
        fanned_out_claims = fanout_counts[fanout_counts > 1]
        n_unique_claims_matched = matched_df["_claim_id"].nunique()
        n_fanned_out = len(fanned_out_claims)
        n_rows_from_fanout = int(fanned_out_claims.sum())
    else:
        n_unique_claims_matched = 0
        n_fanned_out = 0
        n_rows_from_fanout = 0
        fanned_out_claims = pd.Series(dtype=int)

    # Ensure outputs directory exists and write to outputs/
    paths.ensure_outputs()
    matched_df.to_csv(paths.CLAIMS_MATCHED_OUT, index=False)
    unmatched_df.to_csv(paths.UNMATCHED_OUT, index=False)

    print(f"\nMatched: {len(matched_df)} claim-site rows from "
          f"{n_unique_claims_matched} unique claims")
    print(f"  -> {n_fanned_out} of those claims fanned out across multiple sites "
          f"({n_rows_from_fanout} rows total from fan-out)")
    print(f"Unmatched (needs manual review): {len(unmatched_df)}")

    # ---- The actual numbers that matter ----
    summary_lines = []
    summary_lines.append(f"=== VALIDATION SUMMARY: {paths.CLAIMS_FILE.name} ===\n")

    if len(matched_df):
        portfolio_tier_pct = sites["risk_tier"].value_counts(normalize=True) * 100
        portfolio_tier_n = sites["risk_tier"].value_counts()

        # --- View A: all matched rows (fan-out included, current behavior) ---
        claims_tier_pct_raw = matched_df["risk_tier"].value_counts(normalize=True) * 100
        claims_tier_n_raw = matched_df["risk_tier"].value_counts()

        # --- View B: one row per unique claim (fan-out removed) ---
        # For claims matched to multiple sites, take the WORST (highest-risk)
        # tier among that client's matched sites, so a claim doesn't just
        # vanish - but it's counted once, not N times.
        tier_severity = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3,
                          "Coastal/Marine - Requires Storm Surge Assessment": 4,
                          "Insufficient Data": 5}
        matched_df["_severity"] = matched_df["risk_tier"].map(tier_severity).fillna(9)
        dedup_df = (matched_df.sort_values("_severity")
                    .drop_duplicates(subset="_claim_id", keep="first"))
        claims_tier_pct_dedup = dedup_df["risk_tier"].value_counts(normalize=True) * 100
        claims_tier_n_dedup = dedup_df["risk_tier"].value_counts()

        print("\n=== FULL DEDUP TIER LIST - every unique 2024 holdout claim ===")
        print(
            dedup_df[["matched_client_in_sites", "city", "risk_tier",
                      "riverine_score", "pluvial_score", "dominant_hazard"]]
            .sort_values("risk_tier")
            .to_string(index=False)
        )

        print("\n=== Tier breakdown among DEDUP claims ===")
        print(dedup_df["risk_tier"].value_counts())

        # Holdout-safe capture metrics. A client may have several possible
        # sites, so report unambiguous matches as the primary result and the
        # all-claim result as a conservative/optimistic range.
        matched_df["_high_critical"] = matched_df["risk_tier"].isin(["High", "Critical"])
        candidates_per_claim = matched_df.groupby("_claim_id")["_high_critical"]
        unique_claim_ids = fanout_counts[fanout_counts == 1].index
        unique_claims = matched_df[matched_df["_claim_id"].isin(unique_claim_ids)]
        primary_capture_n = int(unique_claims["_high_critical"].sum())
        primary_capture_total = len(unique_claims)
        conservative_capture_n = int(candidates_per_claim.all().sum())
        optimistic_capture_n = int(candidates_per_claim.any().sum())
        all_claims_total = n_unique_claims_matched
        portfolio_high_critical_n = int(sites["risk_tier"].isin(["High", "Critical"]).sum())
        portfolio_high_critical_pct = 100 * portfolio_high_critical_n / len(sites) if len(sites) else 0

        summary_lines.append("\n=== HIGH/CRITICAL CAPTURE METRICS ===")
        summary_lines.append(
            f"Primary — unambiguous claims matched to exactly one Site_ID: "
            f"{primary_capture_n}/{primary_capture_total} High/Critical "
            f"({(100 * primary_capture_n / primary_capture_total) if primary_capture_total else 0:.1f}%)"
        )
        summary_lines.append(
            f"Secondary — all matched claims, conservative (every candidate High/Critical): "
            f"{conservative_capture_n}/{all_claims_total} "
            f"({(100 * conservative_capture_n / all_claims_total) if all_claims_total else 0:.1f}%)"
        )
        summary_lines.append(
            f"Secondary — all matched claims, optimistic (any candidate High/Critical): "
            f"{optimistic_capture_n}/{all_claims_total} "
            f"({(100 * optimistic_capture_n / all_claims_total) if all_claims_total else 0:.1f}%)"
        )
        summary_lines.append(
            f"Portfolio High/Critical: {portfolio_high_critical_n}/{len(sites)} "
            f"({portfolio_high_critical_pct:.1f}%)\n"
        )

        summary_lines.append(f"NOTE: {n_fanned_out} of {n_unique_claims_matched} unique claims "
                              f"fanned out across multiple sites (multi-site client match).")
        summary_lines.append("Two views below: RAW (all matched rows, fan-out included) and")
        summary_lines.append("DEDUP (one row per unique claim, worst tier kept, fan-out removed).")
        summary_lines.append("If RAW and DEDUP tell noticeably different stories, trust DEDUP -")
        summary_lines.append("RAW is likely distorted by multi-site clients.\n")

        summary_lines.append("Tier distribution - portfolio vs. claims (RAW, with counts):\n")
        all_tiers = sorted(set(portfolio_tier_pct.index) | set(claims_tier_pct_raw.index))
        for tier in all_tiers:
            p_pct, p_n = portfolio_tier_pct.get(tier, 0), portfolio_tier_n.get(tier, 0)
            c_pct, c_n = claims_tier_pct_raw.get(tier, 0), claims_tier_n_raw.get(tier, 0)
            summary_lines.append(f"  {tier:45s} portfolio: {p_pct:5.1f}% (n={p_n:4d})   "
                                  f"claims RAW: {c_pct:5.1f}% (n={c_n})")

        summary_lines.append(f"\nTier distribution - portfolio vs. claims (DEDUP, n={len(dedup_df)} unique claims):\n")
        for tier in all_tiers:
            p_pct, p_n = portfolio_tier_pct.get(tier, 0), portfolio_tier_n.get(tier, 0)
            c_pct, c_n = claims_tier_pct_dedup.get(tier, 0), claims_tier_n_dedup.get(tier, 0)
            summary_lines.append(f"  {tier:45s} portfolio: {p_pct:5.1f}% (n={p_n:4d})   "
                                  f"claims DEDUP: {c_pct:5.1f}% (n={c_n})")

        summary_lines.append("\nIf the model has real signal, High/Critical should be")
        summary_lines.append("noticeably OVER-represented in claims vs. portfolio - in DEDUP terms.")
        summary_lines.append("With n this small, treat single-digit swings as noise, not signal.\n")

        if n_fanned_out:
            summary_lines.append(f"\nClaims that fanned out (client has multiple sites - resolve these")
            summary_lines.append(f"manually to a specific site if possible, remarks sometimes name")
            summary_lines.append(f"the specific depot/branch):")
            for cid, n in fanned_out_claims.items():
                example = matched_df[matched_df["_claim_id"] == cid].iloc[0]
                summary_lines.append(f"  {example.get(claim_col,'?')} ({example.get('Loss Date','?')}) "
                                      f"-> matched {n} sites")

        low_tier_claims = dedup_df[dedup_df["risk_tier"].isin(["Low", "Insufficient Data"])]
        summary_lines.append(f"\nClaims (deduped) the model scored Low/Insufficient Data (false negatives): "
                              f"{len(low_tier_claims)} of {len(dedup_df)}")
        if len(low_tier_claims):
            summary_lines.append("These are the most important rows to look at individually:")
            summary_lines.append(
                low_tier_claims[["matched_client_in_sites", "city", "risk_tier",
                                  "riverine_score", "pluvial_score", "dominant_hazard"]
                                 ].to_string(index=False)
            )

            # ---- Diagnostic: why did the pluvial gate suppress these? ----
            # Shows the exact hazard-input values behind each missed claim,
            # so you can see where local_relief_m actually clusters instead
            # of guessing at a new threshold. Sorted by relief so the
            # clustering (if any) is easy to spot by eye.
            summary_lines.append(
                "\n--- Diagnostic: hazard inputs behind each missed claim "
                "(sorted by local_relief_m) ---"
            )
            summary_lines.append(
                "This tells you WHERE to move the pluvial gate threshold, "
                "rather than guessing:\n"
            )
            diag_cols = ["matched_client_in_sites", "city", "local_relief_m", "hand_m",
                         "historical_flood_hits", "monsoon_p95_rainfall_mm",
                         "RP100_depth", "risk_tier"]
            diag = low_tier_claims[diag_cols].sort_values("local_relief_m")
            summary_lines.append(diag.to_string(index=False))

            # Quick clustering hint: how many missed claims fall under a
            # few candidate relief thresholds, so you can see the effect
            # of loosening the gate before you edit risk_score.py.
            summary_lines.append("\nHow many missed claims WOULD be caught if the relief gate")
            summary_lines.append("threshold were loosened from < 1 to each of these values:")
            for threshold in [1, 2, 3, 5, 8]:
                would_catch = (diag["local_relief_m"] < threshold).sum()
                summary_lines.append(
                    f"  local_relief_m < {threshold:<3} -> would catch {would_catch} "
                    f"of {len(diag)} currently-missed claims"
                )

    summary_text = "\n".join(summary_lines)
    print("\n" + summary_text)
    with open(paths.VALIDATION_OUT, "w", encoding="utf-8") as f:
        f.write(summary_text)


if __name__ == "__main__":
    main()
