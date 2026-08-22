"""
geocode_all_sites.py

Reverse-geocodes all site coordinates using OpenStreetMap Nominatim.

Input:
    outputs/sites_scored.csv

Output:
    outputs/sites_nominatim.csv

The script keeps the useful OSM components so we can later
derive a clean "area" field from them.

It caches coordinates, so duplicate coordinates are only
sent to Nominatim once.
"""

import sys
import pathlib
import time
import json

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

from project_paths import OUTPUTS_DIR


# ---------------------------------------------------------
# FILES
# ---------------------------------------------------------

INPUT_FILE = OUTPUTS_DIR / "sites_scored.csv"
OUTPUT_FILE = OUTPUTS_DIR / "sites_nominatim.csv"


# ---------------------------------------------------------
# NOMINATIM
# ---------------------------------------------------------

geolocator = Nominatim(
    user_agent="floodrisk-site-geocoder-arsha"
)

reverse = RateLimiter(
    geolocator.reverse,
    min_delay_seconds=1.1,
    swallow_exceptions=True
)


# ---------------------------------------------------------
# REVERSE GEOCODING
# ---------------------------------------------------------

def reverse_geocode(lat, lon):

    try:

        location = reverse(
            (lat, lon),
            exactly_one=True,
            language="en",
            addressdetails=True
        )

        if location is None:
            return {}

        address = location.raw.get("address", {})

        return {
            "osm_label": location.address,

            "street": address.get("road"),
            "neighbourhood": address.get("neighbourhood"),
            "suburb": address.get("suburb"),
            "district": (
                address.get("district")
                or address.get("city_district")
            ),

            "city": (
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("municipality")
            ),

            "county": address.get("county"),
            "state": address.get("state"),
            "postcode": address.get("postcode"),
            "country": address.get("country"),
        }

    except Exception as e:

        print(f"Geocoding error for {lat}, {lon}: {e}")

        return {}


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    print("=" * 60)
    print("COMPLETE NOMINATIM GEOCODING")
    print("=" * 60)

    print(f"\nLoading:")
    print(INPUT_FILE)

    df = pd.read_csv(INPUT_FILE)

    print(f"Total sites: {len(df)}")

    # -----------------------------------------------------
    # Check required columns
    # -----------------------------------------------------

    required = [
        "Site_ID",
        "Latitude",
        "Longitude"
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    # -----------------------------------------------------
    # Prepare coordinates
    # -----------------------------------------------------

    df["Latitude"] = pd.to_numeric(
        df["Latitude"],
        errors="coerce"
    )

    df["Longitude"] = pd.to_numeric(
        df["Longitude"],
        errors="coerce"
    )

    # -----------------------------------------------------
    # Cache unique coordinates
    # -----------------------------------------------------

    unique_coords = (
        df[
            ["Latitude", "Longitude"]
        ]
        .dropna()
        .drop_duplicates()
    )

    print(
        f"Unique coordinates: {len(unique_coords)}"
    )

    print(
        f"Duplicate coordinate rows saved by caching: "
        f"{len(df) - len(unique_coords)}"
    )

    # -----------------------------------------------------
    # Geocode
    # -----------------------------------------------------

    cache = {}

    total = len(unique_coords)

    for i, row in enumerate(
        unique_coords.itertuples(index=False),
        start=1
    ):

        lat = row.Latitude
        lon = row.Longitude

        key = (
            round(float(lat), 6),
            round(float(lon), 6)
        )

        print(
            f"[{i}/{total}] "
            f"{lat}, {lon}"
        )

        result = reverse_geocode(lat, lon)

        cache[key] = result

    # -----------------------------------------------------
    # Add results to dataframe
    # -----------------------------------------------------

    print("\nAdding OSM results to sites...")

    osm_columns = [
        "osm_label",
        "street",
        "neighbourhood",
        "suburb",
        "district",
        "city",
        "county",
        "state",
        "postcode",
        "country"
    ]

    for column in osm_columns:
        df[column] = None

    for index, row in df.iterrows():

        if pd.isna(row["Latitude"]) or pd.isna(row["Longitude"]):
            continue

        key = (
            round(float(row["Latitude"]), 6),
            round(float(row["Longitude"]), 6)
        )

        result = cache.get(key, {})

        for column in osm_columns:
            df.at[
                index,
                column
            ] = result.get(column)

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    print("\n" + "=" * 60)
    print("GEOCODING COMPLETE")
    print("=" * 60)

    print(f"Rows: {len(df)}")
    print(f"Saved to:")
    print(OUTPUT_FILE)

    print("\nOSM FIELD COVERAGE:")

    for column in osm_columns:

        count = df[column].notna().sum()

        print(
            f"{column:15} "
            f"{count}/{len(df)} "
            f"({count / len(df) * 100:.1f}%)"
        )

    print("\nSample:")

    print(
        df[
            [
                "Site_ID",
                "Latitude",
                "Longitude",
                "city",
                "district",
                "neighbourhood",
                "suburb",
                "osm_label"
            ]
        ]
        .head(20)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()