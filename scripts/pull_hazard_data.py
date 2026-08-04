"""
pull_hazard_data.py
Batched flood hazard extraction for insured client sites using Earth Engine.

Reads a sites CSV (Site_ID, Client, Latitude, Longitude, net_sum_insured)
and writes sites_with_hazard.csv with flood depth, historical flood hits,
and terrain columns appended. Does NOT compute a risk score - that's a
separate step (risk_score.py), kept deliberately apart from extraction.

Setup (once):
    pip install earthengine-api pandas python-dotenv
    earthengine authenticate
Set EE_PROJECT_ID in a .env file in the project root.
"""

import os
from pathlib import Path

import ee
import pandas as pd
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = BASE_DIR / "data" / "sites_input.csv"     # switch to test_sites.csv for a quick run
OUTPUT_FILE = BASE_DIR / "outputs" / "sites_with_hazard.csv"

# Set to True for a small test batch (uses getInfo(), synchronous, instant).
# Set to False for the full ~2,335-site production run (uses Export.table,
# asynchronous - runs on Google's servers, you download the result after).
TEST_MODE = False


def init_earth_engine():
    load_dotenv()
    project_id = os.getenv("EE_PROJECT_ID")
    if not project_id:
        raise ValueError("EE_PROJECT_ID not found - check your .env file")
    ee.Initialize(project=project_id)
    print("Earth Engine initialized successfully.")
    return project_id


def load_datasets(verify=True):
    jrc = ee.ImageCollection('JRC/CEMS_GLOFAS/FloodHazard/v2_1').mosaic()
    jrc_depth = jrc.select(['RP10_depth', 'RP100_depth', 'RP500_depth']).unmask(0)

    gfd = ee.ImageCollection('GLOBAL_FLOOD_DB/MODIS_EVENTS/V1')
    historical_hits = (gfd.select('flooded').sum()
                        .rename('historical_flood_hits').unmask(0))

    merit = ee.Image('MERIT/Hydro/v1_0_1')
    elevation_raw = merit.select('elv').rename('elevation_m')
    local_min = elevation_raw.focal_min(radius=1000, units='meters')
    relief = elevation_raw.subtract(local_min).rename('local_relief_m').unmask(-9999)
    elevation = elevation_raw.unmask(-9999)
    hand = merit.select('hnd').rename('hand_m').unmask(-9999)

    # Rainfall: monsoon-season extreme daily rainfall, 2005-2025.
    # p95 = the daily rainfall intensity exceeded only 5% of monsoon days -
    # a standard extreme-event indicator, less noisy than a single max day.
    chirps = (ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
              .filterDate('2005-01-01', '2025-12-31')
              .filter(ee.Filter.calendarRange(6, 9, 'month'))
              .select('precipitation'))
    rainfall_p95 = (chirps.reduce(ee.Reducer.percentile([95]))
                    .rename('monsoon_p95_rainfall_mm').unmask(0))
    rainfall_max = chirps.max().rename('monsoon_max_rainfall_mm').unmask(0)

    if verify:
        print("JRC bands:", jrc_depth.bandNames().getInfo())
        print("GFD sample bands:", gfd.first().bandNames().getInfo())
        print("MERIT Hydro bands:", merit.bandNames().getInfo())
        print("CHIRPS band:", chirps.first().bandNames().getInfo())

    combined = (jrc_depth.addBands(historical_hits).addBands(elevation)
                .addBands(relief).addBands(hand)
                .addBands(rainfall_p95).addBands(rainfall_max))
    return combined

def build_feature_collection(sites_df):
    features = [
        ee.Feature(
            ee.Geometry.Point([row['Longitude'], row['Latitude']]),
            {'Site_ID': row['Site_ID'], 'Client': row['Client'],
             'net_sum_insured': row['net_sum_insured']}
        )
        for _, row in sites_df.iterrows()
    ]
    return ee.FeatureCollection(features)


def run_test_mode(sampled):
    """Synchronous extraction - fine for a handful of sites, instant feedback."""
    try:
        result = sampled.getInfo()
    except Exception as e:
        print("sampleRegions() failed:", e)
        raise

    rows = [f['properties'] for f in result['features']]
    out = pd.DataFrame(rows)
    print(out.head())
    return out


def run_production_export(sampled, description="hazard_export_new"):
    """
    Asynchronous export for the full site list. This does NOT return a
    DataFrame directly - it starts a job on Google's servers and writes
    the CSV to your Google Drive once finished. Check progress at
    https://code.earthengine.google.com/tasks, or poll with task.status()
    below. Typically takes a few minutes for ~2,000 points.
    """
    task = ee.batch.Export.table.toDrive(
        collection=sampled,
        description=description,
        fileFormat="CSV"
    )
    task.start()
    print(f"Export task '{description}' started. Task ID: {task.id}")
    print("Check status at https://code.earthengine.google.com/tasks")
    print("Once COMPLETED, download the CSV from your Google Drive root folder.")
    return task


def main():
    init_earth_engine()

    sites = pd.read_csv(INPUT_FILE)
    print(sites.head())
    print(f"Loaded {len(sites)} sites")

    combined = load_datasets(verify=TEST_MODE)  # verify prints only in test mode
    fc = build_feature_collection(sites)

    print(combined.bandNames().getInfo())

    sampled = combined.sampleRegions(
        collection=fc,
        scale=90,
        geometries=True,
        tileScale=16
    )

    if TEST_MODE:
        out = run_test_mode(sampled)
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(OUTPUT_FILE, index=False)
        print(f"Done. Wrote {len(out)} rows to {OUTPUT_FILE}")
    else:
        run_production_export(sampled)
        print("Production export submitted - this script's job is done.")
        print("Come back once the Drive file is ready, then join it back")
        print("onto Site_Level_Data before moving to risk_score.py.")


if __name__ == "__main__":
    main()