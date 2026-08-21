"""
check_drainage_claim_cities.py
Wider (but still bounded) test of the drainage-proximity hypothesis:
across every city that actually has a real claim in it, do claim sites
sit closer to a mapped OSM waterway (river/canal/stream/drain/ditch)
than OTHER, non-claim sites in that same city - regardless of client?

This replaces the earlier 3-city/3-client version, which was scoped to
only the hardest-to-explain outlier sites and so couldn't tell you
anything about the hypothesis in general - only about those specific
already-anomalous cases. This version is driven by your real matched-
claims data, not a hardcoded guess, and compares ALL claim sites against
ALL other sites in the same city, across every client.

Scope control: capped to the top N cities by claim count (MAX_CITIES
below) so this doesn't balloon into a full-portfolio run. Widen or
narrow that number as needed.

Requires: osmnx, geopandas, shapely
  pip install osmnx geopandas shapely --break-system-packages

Inputs expected in the same folder:
  sites_scored.csv     - your model output (Client, Site_ID, Latitude,
                          Longitude, city, risk_tier, local_relief_m)
  claims_matched.csv   - output from validate_against_claims.py, needs
                          at least: Site_ID, city, matched_client_in_sites

Caching: waterway data for each city is cached to waterway_cache/ so
re-running this (e.g. after adjusting MAX_CITIES) doesn't re-query OSM
for cities already fetched.

Output:
  drainage_check_claim_cities.csv  - every site in the scoped cities,
                                      with distance to nearest waterway
                                      and whether it's a claim site
"""



import time
import json
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd
import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point
from project_paths import OUTPUTS_DIR, CLAIMS_MATCHED_OUT, SITES_FILE, WATERWAY_CACHE

ox.settings.timeout = 300

OUTPUT_FILE = OUTPUTS_DIR / "drainage_check_claim_cities.csv"
CACHE_DIR = WATERWAY_CACHE

WATERWAY_TYPES = ["river", "canal", "stream", "drain", "ditch"]

# Scope control - top N cities BY CLAIM COUNT, not all cities in the
# portfolio. Raise this later if this run gives a promising result and
# you want more coverage; keep it low for a first pass.
MAX_CITIES = 9

# Rough UTM zone by longitude - Pakistan spans 42N (west) / 43N (east).
# Good enough for city-scale distance calculations.
def utm_for(lon):
    return "EPSG:32642" if lon < 68 else "EPSG:32643"


def fetch_waterways(city_key, north, south, east, west, retries=3, backoff_seconds=15):
    """
    Fetches waterways within a bounding box built from the city's own
    site coordinates (+ buffer), rather than asking Nominatim to resolve
    a place name to a boundary polygon. This sidesteps the
    "did not geocode query to a geometry of type (Multi)Polygon" failure
    that hit Lahore/Kahna/Khurrianwala/Multan - Nominatim sometimes
    returns a point or line for a place instead of the polygon osmnx
    expects, and no amount of retrying a place-name query fixes that.
    Using our own data's bounding box avoids the boundary lookup
    entirely and is arguably more correct: it covers exactly the area
    our sites are actually in, not a possibly much larger/oddly-shaped
    administrative boundary.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{city_key}.geojson"
    if cache_file.exists():
        print(f"  [cache] using cached waterway data for {city_key}")
        gdf = gpd.read_file(cache_file)
        return gdf if not gdf.empty else None

    tags = {"waterway": WATERWAY_TYPES}
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            gdf = ox.features_from_bbox((west, south, east, north), tags=tags)
            gdf = gdf[gdf.geometry.notnull()].reset_index(drop=True)
            gdf["waterway_type"] = gdf.get("waterway", "unknown")
            gdf = gdf[["geometry", "waterway_type"]]
            gdf.to_file(cache_file, driver="GeoJSON")
            return gdf
        except Exception as e:
            last_error = e
            if attempt < retries:
                print(f"    attempt {attempt}/{retries} failed: {e}, retrying in {backoff_seconds}s...")
                time.sleep(backoff_seconds)
    print(f"    all attempts failed for bbox around '{city_key}': {last_error}")
    return None


def nearest_distance(lat, lon, waterways_proj, utm_crs):
    pt = gpd.GeoDataFrame(geometry=[Point(lon, lat)], crs="EPSG:4326").to_crs(utm_crs)
    pt_proj = pt.geometry.iloc[0]
    dists = waterways_proj.geometry.distance(pt_proj)
    pos = dists.values.argmin()
    return round(dists.iloc[pos], 1), waterways_proj.iloc[pos]["waterway_type"]


def main():
    sites = pd.read_csv(SITES_FILE)
    sites["city_norm"] = sites["city"].str.strip().str.lower()

    claims = pd.read_csv(CLAIMS_MATCHED_FILE)
    claims["city_norm"] = claims["city"].str.strip().str.lower()
    claim_site_ids = set(claims["Site_ID"].dropna())

    # Cities ranked by how many claims actually landed there - this is
    # what determines scope now, not a hardcoded guess.
    city_claim_counts = claims["city_norm"].value_counts()
    scoped_cities = city_claim_counts.head(MAX_CITIES)
    print(f"Scoping to top {MAX_CITIES} cities by claim count:")
    for city, n in scoped_cities.items():
        print(f"  {city}: {n} claim(s)")

    results = []

    for city_key in scoped_cities.index:
        city_sites = sites[sites["city_norm"] == city_key].copy()
        if city_sites.empty:
            print(f"\n[skip] '{city_key}' has claims but no matching sites in {SITES_FILE.name} "
                  f"(check city-name spelling consistency)")
            continue

        # UTM zone from this city's own longitude, not a fixed per-city table
        sample_lon = city_sites["Longitude"].iloc[0]
        utm_crs = utm_for(sample_lon)

        # Bounding box from the sites' own coordinates, buffered ~0.08 deg
        # (roughly 8-9km at these latitudes) so waterways just outside the
        # tightest site cluster still get picked up - without this margin,
        # a site near the edge of its own cluster could miss a nearby
        # waterway that falls just outside the raw min/max box.
        buffer_deg = 0.08
        north = city_sites["Latitude"].max() + buffer_deg
        south = city_sites["Latitude"].min() - buffer_deg
        east = city_sites["Longitude"].max() + buffer_deg
        west = city_sites["Longitude"].min() - buffer_deg

        print(f"\n=== {city_key.upper()} ({len(city_sites)} sites, {scoped_cities[city_key]} claim(s)) ===")
        waterways = fetch_waterways(city_key, north, south, east, west)
        if waterways is None or waterways.empty:
            print(f"  [skip] no waterway data available for {city_key}")
            continue
        waterways_proj = waterways.to_crs(utm_crs)

        for _, row in city_sites.iterrows():
            dist, wtype = nearest_distance(row["Latitude"], row["Longitude"], waterways_proj, utm_crs)
            results.append({
                "Client": row["Client"],
                "Site_ID": row["Site_ID"],
                "city": city_key,
                "risk_tier": row["risk_tier"],
                "local_relief_m": row.get("local_relief_m"),
                "dist_to_waterway_m": dist,
                "nearest_waterway_type": wtype,
                "is_claim_site": row["Site_ID"] in claim_site_ids,
            })

        # Incremental save after each city, so a later failure doesn't
        # cost you the cities that already succeeded.
        pd.DataFrame(results).to_csv(OUTPUT_FILE, index=False)

    if not results:
        print("\nNo results produced - check city-name matching between "
              f"{CLAIMS_MATCHED_FILE.name} and {SITES_FILE.name}.")
        return

    out = pd.DataFrame(results)
    out.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(out)} rows to {OUTPUT_FILE}")

    print("\n=== COMPARISON: claim sites vs. non-claim sites, by city ===\n")
    for city_key in scoped_cities.index:
        city_df = out[out["city"] == city_key]
        if city_df.empty:
            continue
        claim_rows = city_df[city_df["is_claim_site"]]
        other_rows = city_df[~city_df["is_claim_site"]]
        print(f"--- {city_key.upper()} ---")
        if len(claim_rows):
            print(f"  Claim sites (n={len(claim_rows)}): "
                  f"median {claim_rows['dist_to_waterway_m'].median():.0f} m")
        if len(other_rows):
            print(f"  Non-claim sites (n={len(other_rows)}): "
                  f"median {other_rows['dist_to_waterway_m'].median():.0f} m")
        print()

    # Overall pooled comparison across all scoped cities - the actual
    # headline number to look at.
    claim_all = out[out["is_claim_site"]]["dist_to_waterway_m"]
    other_all = out[~out["is_claim_site"]]["dist_to_waterway_m"]
    print("=== OVERALL (pooled across all scoped cities) ===")
    if len(claim_all) and len(other_all):
        print(f"Claim sites (n={len(claim_all)}):     median {claim_all.median():.0f} m")
        print(f"Non-claim sites (n={len(other_all)}): median {other_all.median():.0f} m")
        print("\nIf claim-site median is meaningfully LOWER than non-claim median,")
        print("that's real support for adding drainage proximity to the model.")
    else:
        print("Not enough data in one of the groups to compare.")


if __name__ == "__main__":
    main()