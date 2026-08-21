"""Extract one CHIRPS annual maximum daily-rainfall value per portfolio site.

This intentionally runs one full-portfolio Earth Engine query per calendar year.
It is therefore much slower than the project's single-pass hazard extraction;
watch the reported failed-year list rather than treating a long runtime as proof
of success.
"""

import os
import sys
from datetime import date
from pathlib import Path

import ee
import pandas as pd
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
SITES_FILE = BASE_DIR / "data" / "sites_input.csv"
OUTPUT_FILE = BASE_DIR / "outputs" / "annual_max_daily_rainfall_chirps.csv"
FAILED_YEARS_FILE = BASE_DIR / "outputs" / "annual_max_daily_rainfall_chirps_failed_years.txt"
START_YEAR = 1990
END_YEAR = date.today().year - 1  # most recent complete calendar year
CHIRPS_SCALE_M = 5_566  # approximately CHIRPS' native 0.05-degree resolution
TILE_SCALE = 16


def init_earth_engine():
    """Initialize Earth Engine from the repository's EE_PROJECT_ID setting."""
    load_dotenv(BASE_DIR / ".env")
    project_id = os.getenv("EE_PROJECT_ID")
    if not project_id:
        raise ValueError("EE_PROJECT_ID not found in .env")
    ee.Initialize(project=project_id)
    print(f"Earth Engine initialized (project: {project_id}).")


def build_sites_feature_collection(sites):
    """Convert the full local site table to EE point features with identifiers."""
    return ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Point([row.Longitude, row.Latitude]),
            {"Site_ID": row.Site_ID, "Client": row.Client},
        )
        for row in sites[["Site_ID", "Client", "Latitude", "Longitude"]].itertuples(index=False)
    ])


def extract_year(year, sites_fc):
    """Return one annual-maximum daily CHIRPS value for every sampled site."""
    annual_max = (
        ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .select("precipitation")
        .max()
        .rename("annual_max_daily_rainfall_mm")
    )
    sampled = annual_max.sampleRegions(
        collection=sites_fc,
        properties=["Site_ID", "Client"],
        scale=CHIRPS_SCALE_M,
        geometries=False,
        tileScale=TILE_SCALE,
    )
    response = sampled.getInfo()
    rows = []
    for feature in response["features"]:
        properties = feature["properties"]
        rows.append({
            "Site_ID": properties.get("Site_ID"),
            "Client": properties.get("Client"),
            "year": year,
            "annual_max_daily_rainfall_mm": properties.get("annual_max_daily_rainfall_mm"),
        })
    return pd.DataFrame(rows)


def main():
    sites = pd.read_csv(SITES_FILE)
    required = {"Site_ID", "Client", "Latitude", "Longitude"}
    missing = required - set(sites.columns)
    if missing:
        raise ValueError(f"{SITES_FILE.name} is missing required columns: {sorted(missing)}")

    print(f"Loaded {len(sites)} sites from {SITES_FILE}")
    print(f"Extracting annual maxima for {START_YEAR}-{END_YEAR} ({END_YEAR - START_YEAR + 1} years)")
    init_earth_engine()
    sites_fc = build_sites_feature_collection(sites)

    yearly_frames = []
    failed_years = []
    for year in range(START_YEAR, END_YEAR + 1):
        print(f"Processing {year}...")
        try:
            frame = extract_year(year, sites_fc)
            yearly_frames.append(frame)
            print(f"  success: {len(frame)} sampled rows")
        except Exception as error:
            failed_years.append(year)
            print(f"  FAILED: {type(error).__name__}: {error}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if yearly_frames:
        out = pd.concat(yearly_frames, ignore_index=True)
    else:
        out = pd.DataFrame(columns=["Site_ID", "Client", "year", "annual_max_daily_rainfall_mm"])
    out.to_csv(OUTPUT_FILE, index=False)
    FAILED_YEARS_FILE.write_text(
        "\n".join(map(str, failed_years)) + ("\n" if failed_years else ""),
        encoding="utf-8",
    )

    print(f"Wrote {len(out)} rows to {OUTPUT_FILE}")
    if failed_years:
        print(f"Failed years ({len(failed_years)}): {failed_years}")
        print(f"Failed-year record: {FAILED_YEARS_FILE}")
    else:
        print("Failed years: none")


if __name__ == "__main__":
    main()
