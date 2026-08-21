from pathlib import Path

# Centralised project paths to keep scripts consistent and non-destructive.
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUTS_DIR = BASE_DIR / "outputs"

# Common files
SITES_FILE = OUTPUTS_DIR / "sites_scored.csv"
CLAIMS_FILE = DATA_DIR / "claims_history_to_2023.csv"

# Validation outputs
CLAIMS_MATCHED_OUT = OUTPUTS_DIR / "claims_matched_history.csv"
UNMATCHED_OUT = OUTPUTS_DIR / "unmatched_claims_history.csv"
VALIDATION_OUT = OUTPUTS_DIR / "validation_summary_history.txt"

# Feature build outputs
CITY_RATES_OUT = OUTPUTS_DIR / "city_claim_rates_history.csv"
REPEAT_CLIENTS_OUT = OUTPUTS_DIR / "repeat_claim_clients_history.csv"
REPEAT_SITES_OUT = OUTPUTS_DIR / "repeat_claim_sites_history.csv"
UNATTRIBUTED_OUT = OUTPUTS_DIR / "unattributed_fanned_claims_history.csv"
MERGED_OUT = OUTPUTS_DIR / "sites_with_claims_features.csv"

# Manual resolution file (human-provided mappings)
MANUAL_RESOLUTIONS_FILE = OUTPUTS_DIR / "manual_fanned_claim_resolutions.csv"

# Cache / helper dirs
CACHE_DIR = OUTPUTS_DIR / "cache"
WATERWAY_CACHE = OUTPUTS_DIR / "waterway_cache"

def ensure_outputs():
    (OUTPUTS_DIR).mkdir(parents=True, exist_ok=True)
    (CACHE_DIR).mkdir(parents=True, exist_ok=True)
    (WATERWAY_CACHE).mkdir(parents=True, exist_ok=True)
