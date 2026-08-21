"""
resolve_fanned_claims.py
Semi-automated first pass at resolving the 22 fanned claims (matched to
multiple sites for the same client) down to a specific Site_ID.

This does NOT auto-resolve anything - it's a suggestion tool. For each
fanned claim, it scans the REMARKS/Cause of Loss text for a location
keyword (city/depot/branch name) and checks it against that client's
candidate sites' city field. If exactly one candidate site's city
matches a keyword found in the remarks, it's flagged as a
high-confidence suggestion. Everything else is left for manual review.

Given how consequential these are (they feed directly into
repeat_claim_site and city_claim_rate), nothing here should be trusted
without you looking at the 'suggested_site_id' + 'match_reason' columns
and confirming - this is meant to save you re-reading all 22 remarks
from scratch, not to replace your judgment.

Requires: pandas
Inputs:
  unattributed_fanned_claims.csv - from build_claims_features.py
  claims_matched.csv             - from validate_against_claims.py (has
                                    the full REMARKS text + all candidate
                                    Site_IDs per fanned claim)
Output:
  fanned_claims_suggestions.csv  - one row per fanned claim, with a
                                    suggested Site_ID where confident,
                                    or "NEEDS MANUAL REVIEW" otherwise
"""

import pandas as pd
import re
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from project_paths import CLAIMS_MATCHED_OUT, UNATTRIBUTED_OUT, OUTPUTS_DIR

CLAIMS_MATCHED_FILE = CLAIMS_MATCHED_OUT
UNATTRIBUTED_FILE = UNATTRIBUTED_OUT
OUTPUT_FILE = OUTPUTS_DIR / "fanned_claims_suggestions.csv"


def main():
    claims = pd.read_csv(CLAIMS_MATCHED_FILE)
    unattributed = pd.read_csv(UNATTRIBUTED_FILE)

    client_col = "Insured/Participant" if "Insured/Participant" in claims.columns else "Insured/Participant "
    remarks_col = "REMARKS" if "REMARKS" in claims.columns else None
    cause_col = "Cause of  Loss" if "Cause of  Loss" in claims.columns else "Cause of Loss"

    suggestions = []

    for _, fc in unattributed.iterrows():
        client = fc[client_col]
        loss_date = fc["Loss Date"]

        candidates = claims[(claims[client_col] == client) & (claims["Loss Date"] == loss_date)]
        if candidates.empty:
            continue

        remark_text = ""
        if remarks_col and pd.notna(candidates[remarks_col].iloc[0]):
            remark_text += str(candidates[remarks_col].iloc[0])
        if cause_col in candidates.columns and pd.notna(candidates[cause_col].iloc[0]):
            remark_text += " " + str(candidates[cause_col].iloc[0])
        remark_text_lower = remark_text.lower()

        candidate_sites = candidates[["Site_ID", "city", "matched_client_in_sites"]].drop_duplicates()

        matches = []
        for _, cs in candidate_sites.iterrows():
            city_val = str(cs["city"]).lower().strip()
            if city_val and re.search(rf"\b{re.escape(city_val)}\b", remark_text_lower):
                matches.append(cs["Site_ID"])

        if len(matches) == 1:
            suggestions.append({
                "Client": client, "Loss Date": loss_date,
                "remarks_excerpt": remark_text[:150],
                "n_candidate_sites": len(candidate_sites),
                "suggested_site_id": matches[0],
                "match_reason": f"city name found in remarks/cause text",
                "confidence": "HIGH - confirm before using",
            })
        elif len(matches) > 1:
            suggestions.append({
                "Client": client, "Loss Date": loss_date,
                "remarks_excerpt": remark_text[:150],
                "n_candidate_sites": len(candidate_sites),
                "suggested_site_id": ", ".join(matches),
                "match_reason": "multiple city names matched - ambiguous",
                "confidence": "LOW - needs manual review",
            })
        else:
            suggestions.append({
                "Client": client, "Loss Date": loss_date,
                "remarks_excerpt": remark_text[:150],
                "n_candidate_sites": len(candidate_sites),
                "suggested_site_id": "NEEDS MANUAL REVIEW",
                "match_reason": "no city/location keyword found in remarks",
                "confidence": "NONE",
            })

    out = pd.DataFrame(suggestions)
    out.to_csv(OUTPUT_FILE, index=False)

    high_conf = (out["confidence"] == "HIGH - confirm before using").sum()
    print(f"Saved {len(out)} fanned claim(s) to {OUTPUT_FILE}")
    print(f"  {high_conf} high-confidence single-site suggestion(s) - review and confirm")
    print(f"  {len(out) - high_conf} need manual review (ambiguous or no location keyword found)")
    print(f"\nOpen {OUTPUT_FILE}, check the 'remarks_excerpt' against 'suggested_site_id' yourself,")
    print("then manually apply confirmed ones by updating Site_ID in your claims data before")
    print("re-running build_claims_features.py and validate_against_claims.py.")


if __name__ == "__main__":
    main()