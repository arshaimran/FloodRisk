"""
build_claims_features.py
Derives evidence-based features from your real claims data, to feed into
risk_score.py as inputs alongside (or instead of) the satellite-derived
historical_flood_hits.

  1. repeat_claim_client  - True if a CLIENT filed 2+ distinct claims in
                             the data. Safe regardless of fan-out, since
                             it doesn't depend on knowing which specific
                             site was hit each time.

  2. repeat_claim_site    - True if a SPECIFIC site has 2+ distinct
                             claims. Only computed from claims that
                             matched to exactly ONE site (unambiguous) -
                             fanned claims (matched to several sites for
                             the same client) are excluded here, because
                             we don't actually know which of that
                             client's sites was hit. Including them would
                             silently spread one real claim's "repeat"
                             status across every site the client owns
                             (this happened in the first version of this
                             script - see note below).

  3. city_claim_rate      - unambiguous (non-fanned) claims / total sites
                             in that city. Also excludes fan-out for the
                             same reason - a fanned claim can't be
                             confidently attributed to one city if a
                             client has sites in several.

IMPORTANT FIX vs. the first version of this script: that version deduped
by (Site_ID, Loss Date), which does NOT collapse fan-out - a single real
claim that matched 5 of a client's sites produces 5 different Site_IDs,
each looking "distinct" to that check. This silently multiplied claim
counts (94 rows counted for what should be far fewer real events) and
produced false repeat-claim flags (e.g. a client with 2 real claims,
each fanning to several sites, made EVERY one of their sites look like
a 2-claim "repeat" location, regardless of which site was actually
hit). This version identifies true claim identity FIRST (by
Insured/Participant + Loss Date), then explicitly separates claims that
matched exactly one site (trustworthy for site/city attribution) from
claims that fanned to multiple sites (not attributable without manual
resolution - reported separately, not silently included).

Requires: pandas
Inputs:
  sites_scored.csv    - your model output
  claims_matched_history.csv  - output from validate_against_claims.py

Outputs:
  city_claim_rates_history.csv           - city-level rates, non-fanned claims only
  repeat_claim_clients_history.csv       - clients with 2+ distinct claims (safe)
  repeat_claim_sites_history.csv         - sites with 2+ distinct claims (non-fanned only)
  unattributed_fanned_claims_history.csv - claims that COULD affect the above but
                                    can't be attributed without manually
                                    resolving them to a specific site -
                                    review this list, don't ignore it
  sites_with_claims_features.csv - sites_scored.csv + new columns
"""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd
from project_paths import (
    SITES_FILE,
    CLAIMS_MATCHED_OUT as CLAIMS_MATCHED_FILE,
    CITY_RATES_OUT,
    REPEAT_CLIENTS_OUT,
    REPEAT_SITES_OUT,
    UNATTRIBUTED_OUT,
    MERGED_OUT,
    MANUAL_RESOLUTIONS_FILE,
)

FLOOD_ONLY = True


def main():
    sites = pd.read_csv(SITES_FILE)
    claims = pd.read_csv(CLAIMS_MATCHED_FILE)

    def load_manual_resolutions(client_col, loss_date_col):
        if not MANUAL_RESOLUTIONS_FILE.exists():
            return None

        manual = pd.read_csv(MANUAL_RESOLUTIONS_FILE, dtype=str)
        # Defensive: ensure the provided manual resolutions have unique claim keys
        if "Insured/Participant" in manual.columns or client_col in manual.columns:
            temp_client = client_col if client_col in manual.columns else client_col.strip()
        else:
            temp_client = client_col
        if client_col not in manual.columns and client_col.strip() in manual.columns:
            manual = manual.rename(columns={client_col.strip(): client_col})
        if loss_date_col not in manual.columns and loss_date_col.strip() in manual.columns:
            manual = manual.rename(columns={loss_date_col.strip(): loss_date_col})
        if "Site_ID" not in manual.columns:
            raise ValueError(f"{MANUAL_RESOLUTIONS_FILE.name} must contain a Site_ID column")
        manual = manual[[client_col, loss_date_col, "Site_ID"]].copy()
        manual[client_col] = manual[client_col].astype(str).str.strip()
        manual[loss_date_col] = manual[loss_date_col].astype(str).str.strip()
        manual["claim_key"] = manual[client_col] + "|" + manual[loss_date_col]
        if manual["claim_key"].duplicated().any():
            dupes = manual[manual["claim_key"].duplicated(keep=False)]["claim_key"].unique()
            raise ValueError(f"Duplicate claim_key(s) found in {MANUAL_RESOLUTIONS_FILE.name}: {list(dupes)}")
        return manual.set_index("claim_key")

    if FLOOD_ONLY and "flood_relevant" in claims.columns:
        before = len(claims)
        claims = claims[claims["flood_relevant"].str.strip().str.lower() == "yes"].copy()
        print(f"Filtered to flood-relevant claims: {len(claims)} of {before} matched rows")

    sites["city_norm"] = sites["city"].str.strip().str.lower()
    claims["city_norm"] = claims["city"].str.strip().str.lower()

    client_col = "Insured/Participant" if "Insured/Participant" in claims.columns else "Insured/Participant "
    loss_date_col = "Loss Date" if "Loss Date" in claims.columns else None
    if loss_date_col is None:
        raise ValueError(f"Expected a 'Loss Date' column in {CLAIMS_MATCHED_FILE.name}")

    claims[client_col] = claims[client_col].astype(str).str.strip()
    claims[loss_date_col] = claims[loss_date_col].astype(str).str.strip()
    claims["claim_key"] = claims[client_col] + "|" + claims[loss_date_col]
    manual_resolutions = load_manual_resolutions(client_col, loss_date_col)
    if manual_resolutions is not None:
        claims["manual_resolved_site"] = claims["claim_key"].map(manual_resolutions["Site_ID"])
        claims["manual_resolution_applies"] = claims["claim_key"].isin(manual_resolutions.index)
        claims["use_for_features"] = (~claims["manual_resolution_applies"]) | (
            claims["Site_ID"] == claims["manual_resolved_site"]
        )
        print(f"Loaded {manual_resolutions.index.nunique()} manual fanned-claim resolution(s) from {MANUAL_RESOLUTIONS_FILE.name}")
    else:
        claims["manual_resolved_site"] = pd.NA
        claims["manual_resolution_applies"] = False
        claims["use_for_features"] = True

    # ---------------------------------------------------------------
    # Step 1: identify TRUE claim identity (client + loss date), THEN
    # check how many distinct sites each one matched to. This must come
    # before any site/city counting, or fan-out silently corrupts both.
    # ---------------------------------------------------------------
    claim_id_cols = [client_col, loss_date_col]
    claims_for_features = claims[claims["use_for_features"]].copy()
    sites_per_claim = claims_for_features.groupby(claim_id_cols)["Site_ID"].nunique().rename("n_sites_matched")
    claims_with_fanout_info = claims.merge(sites_per_claim, on=claim_id_cols, how="left")

    non_fanned = claims_with_fanout_info[claims_with_fanout_info["n_sites_matched"] == 1].copy()
    fanned = claims_with_fanout_info[claims_with_fanout_info["n_sites_matched"] > 1].copy()

    n_true_claims = claims_with_fanout_info.drop_duplicates(subset=claim_id_cols).shape[0]
    n_fanned_claims = fanned.drop_duplicates(subset=claim_id_cols).shape[0]
    print(f"\nTrue distinct claim events: {n_true_claims}")
    print(f"  Unambiguous (matched exactly 1 site): {n_true_claims - n_fanned_claims}")
    print(f"  Fanned (matched multiple sites, NOT used below): {n_fanned_claims}")

    fanned_dedup = fanned.drop_duplicates(subset=claim_id_cols)
    fanned_dedup[[client_col, loss_date_col, "n_sites_matched"]].to_csv(UNATTRIBUTED_OUT, index=False)
    print(f"Saved {len(fanned_dedup)} fanned claim(s) to {UNATTRIBUTED_OUT} - "
          f"resolve these to a specific site manually (remarks sometimes name "
          f"the depot/branch) to recover their signal.")

    # ---------------------------------------------------------------
    # Feature 1: repeat_claim_client - safe regardless of fan-out
    # ---------------------------------------------------------------
    claims_per_client = claims_with_fanout_info.drop_duplicates(subset=claim_id_cols) \
        .groupby(client_col).size().rename("distinct_claim_count")
    repeat_clients = claims_per_client[claims_per_client >= 2].reset_index()
    repeat_clients.to_csv(REPEAT_CLIENTS_OUT, index=False)
    print(f"\nSaved {len(repeat_clients)} repeat-claim client(s) to {REPEAT_CLIENTS_OUT}")
    if len(repeat_clients):
        print(repeat_clients.to_string(index=False))

    # ---------------------------------------------------------------
    # Feature 2: city_claim_rate - non-fanned claims only
    # ---------------------------------------------------------------
    city_claim_counts = non_fanned.drop_duplicates(subset=claim_id_cols) \
        .groupby("city_norm").size().rename("claim_count")
    city_site_counts = sites.groupby("city_norm").size().rename("site_count")

    city_rates = pd.DataFrame({
        "site_count": city_site_counts,
        "claim_count": city_claim_counts,
    }).fillna(0)
    city_rates["claim_count"] = city_rates["claim_count"].astype(int)
    city_rates["city_claim_rate"] = (city_rates["claim_count"] / city_rates["site_count"]).round(4)
    city_rates = city_rates.sort_values("city_claim_rate", ascending=False)
    city_rates.to_csv(CITY_RATES_OUT)

    print(f"\nSaved city-level claim rates (non-fanned claims only) to {CITY_RATES_OUT}")
    print("Top 10 cities by claim rate:")
    print(city_rates.head(10).to_string())
    print("\nNote: cities with claims ONLY from fanned (unattributed) events will show")
    print("as 0 here even if the client's real claim may well have happened there -")
    print(f"check {UNATTRIBUTED_OUT} before concluding a city has no risk signal.")

    # ---------------------------------------------------------------
    # Feature 3: repeat_claim_site - non-fanned claims only
    # ---------------------------------------------------------------
    site_claim_counts = non_fanned.drop_duplicates(subset=claim_id_cols + ["Site_ID"]) \
        .groupby("Site_ID").size().rename("distinct_claim_count")
    repeat_sites = site_claim_counts[site_claim_counts >= 2].reset_index()
    repeat_sites = repeat_sites.merge(
        sites[["Site_ID", "Client", "city", "risk_tier"]].drop_duplicates(subset="Site_ID"),
        on="Site_ID", how="left"
    )
    repeat_sites.to_csv(REPEAT_SITES_OUT, index=False)
    print(f"\nSaved {len(repeat_sites)} repeat-claim site(s) (non-fanned only) to {REPEAT_SITES_OUT}")
    if len(repeat_sites):
        print(repeat_sites.to_string(index=False))
    else:
        print("(none found among unambiguous single-site claims)")

    # ---------------------------------------------------------------
    # Merge onto full site list
    # ---------------------------------------------------------------
    out = sites.copy()
    out["city_claim_rate"] = out["city_norm"].map(city_rates["city_claim_rate"]).fillna(0)

    repeat_site_ids = set(repeat_sites["Site_ID"]) if len(repeat_sites) else set()
    out["repeat_claim_site"] = out["Site_ID"].isin(repeat_site_ids)

    repeat_client_names = set(repeat_clients[client_col]) if len(repeat_clients) else set()
    out["repeat_claim_client"] = out["Client"].isin(repeat_client_names)

    has_history_claim_ids = set(claims_with_fanout_info["Site_ID"]) if len(claims_with_fanout_info) else set()
    out["has_history_claim"] = out["Site_ID"].isin(has_history_claim_ids)

    out = out.drop(columns=["city_norm"])
    out.to_csv(MERGED_OUT, index=False)
    print(f"\nSaved full site list with new features to {MERGED_OUT}")
    print("New columns: city_claim_rate, repeat_claim_site, repeat_claim_client, has_history_claim")
    print(f"\nRemember: {n_fanned_claims} claim(s) remain unattributed - resolving those")
    print("manually would likely add more repeat-claim signal than shown here.")


if __name__ == "__main__":
    main()
