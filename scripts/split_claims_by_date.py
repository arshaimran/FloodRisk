"""Create the immutable time split used by the claims-validation pipeline."""

from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
CLAIMS_FILE = BASE_DIR / "data" / "claims.csv"
HISTORY_OUT = BASE_DIR / "data" / "claims_history_to_2023.csv"
HOLDOUT_OUT = BASE_DIR / "data" / "claims_holdout_2024.csv"
CUTOFF = pd.Timestamp("2024-01-01")


def main():
    claims = pd.read_csv(CLAIMS_FILE)
    if "Loss Date" not in claims.columns:
        raise ValueError("claims.csv must contain a 'Loss Date' column")

    loss_dates = pd.to_datetime(claims["Loss Date"], dayfirst=True, errors="coerce")
    if loss_dates.isna().any():
        bad_rows = (loss_dates.isna().to_numpy().nonzero()[0] + 2).tolist()
        raise ValueError(f"Unparseable Loss Date values in CSV row(s): {bad_rows}")

    claims = claims.copy()
    claims["validation_split"] = pd.Series(
        pd.NA, index=claims.index, dtype="string"
    )
    claims.loc[loss_dates < CUTOFF, "validation_split"] = "HISTORY"
    claims.loc[loss_dates >= CUTOFF, "validation_split"] = "HOLDOUT"

    history = claims[claims["validation_split"] == "HISTORY"]
    holdout = claims[claims["validation_split"] == "HOLDOUT"]
    history.to_csv(HISTORY_OUT, index=False)
    holdout.to_csv(HOLDOUT_OUT, index=False)
    print(f"Wrote {len(history)} history claims to {HISTORY_OUT}")
    print(f"Wrote {len(holdout)} holdout claims to {HOLDOUT_OUT}")


if __name__ == "__main__":
    main()
