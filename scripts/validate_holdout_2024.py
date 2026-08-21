"""Evaluate the frozen model only on 2024 claims; never use this output as a feature input."""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pathlib import Path
import validate_against_claims as validator
import project_paths as paths

BASE_DIR = Path(__file__).resolve().parent.parent

# Temporarily override project paths for this run by setting values on
# the central `project_paths` module so validator picks them up.
paths.CLAIMS_FILE = BASE_DIR / "data" / "claims_holdout_2024.csv"
paths.CLAIMS_MATCHED_OUT = BASE_DIR / "outputs" / "claims_matched_holdout_2024.csv"
paths.UNMATCHED_OUT = BASE_DIR / "outputs" / "unmatched_claims_holdout_2024.csv"
paths.VALIDATION_OUT = BASE_DIR / "outputs" / "validation_summary_holdout_2024.txt"


if __name__ == "__main__":
    validator.main()
