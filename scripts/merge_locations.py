"""
merge_locations.py

Adds Latitude, Longitude, City and Province to the hazard dataset.

Run:

python scripts/merge_locations.py
"""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from project_paths import OUTPUTS_DIR, DATA_DIR
import pandas as pd
import reverse_geocoder as rg

HAZARD_FILE = OUTPUTS_DIR / "hazard_export.csv"
SITES_FILE = DATA_DIR / "sites_input.csv"
OUTPUT_FILE = OUTPUTS_DIR / "sites_with_cities.csv"


def main():

    print("Loading files...")

    hazard = pd.read_csv(HAZARD_FILE)

    sites = pd.read_csv(SITES_FILE)

    print("Merging coordinates...")

    df = hazard.merge(
        sites[
            [
                "Site_ID",
                "Latitude",
                "Longitude"
            ]
        ],
        on="Site_ID",
        how="left"
    )

    print("Reverse geocoding...")

    coords = list(zip(df["Latitude"], df["Longitude"]))

    # mode=1 avoids multiprocessing issues on Windows
    results = rg.search(coords, mode=1)

    df["city"] = [r["name"] for r in results]
    df["province"] = [r["admin1"] for r in results]
    df["country"] = [r["cc"] for r in results]

    print("Saving...")

    df.to_csv(OUTPUT_FILE, index=False)

    print(f"Saved to:\n{OUTPUT_FILE}")


if __name__ == "__main__":
    main()