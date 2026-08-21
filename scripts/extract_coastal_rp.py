"""Extract coastal return-period depths from local Aqueduct GeoTIFFs.

Run: python scripts/extract_coastal_rp.py

Writes: outputs/coastal_rp_samples.csv
Prints summary counts per return period.
"""
import sys
from pathlib import Path
import glob
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
SITES_CSV = BASE / 'data' / 'sites_input.csv'
AQUA_DIR = BASE / 'data' / 'aqueduct_coastal'
CLIPPED_DIR = AQUA_DIR / 'pakistan_coast'
OUT = BASE / 'outputs' / 'coastal_rp_samples.csv'

RPS = {
    'rp0002': 'coastal_RP2_depth_m',
    'rp0010': 'coastal_RP10_depth_m',
    'rp0100': 'coastal_RP100_depth_m',
    'rp1000': 'coastal_RP1000_depth_m',
}

def find_raster_for_rp(aqua_dir, rp_code):
    patterns = [f"**/*inuncoast*{rp_code}*.tif",
                f"**/*inuncoast*{rp_code}*.tiff",
                f"**/*inuncoast*{rp_code}*.img",
                f"**/*inuncoast*{rp_code}*.vrt",
                f"**/*inuncoast*{rp_code}*.nc"]
    for p in patterns:
        matches = list(aqua_dir.glob(p))
        if matches:
            return matches[0]
    return None


def main():
    if not SITES_CSV.exists():
        print(f"Site list not found: {SITES_CSV}")
        sys.exit(1)

    sites = pd.read_csv(SITES_CSV)
    if not {'Site_ID','Client','Latitude','Longitude'}.issubset(sites.columns):
        print('Input CSV missing required columns: Site_ID, Client, Latitude, Longitude')
        sys.exit(1)

    total_sites = len(sites)
    print(f"Total sites in input: {total_sites}")

    AQUA_DIR.mkdir(parents=True, exist_ok=True)  # ensure dir exists for listing

    # prepare output columns
    out = sites[['Site_ID','Client','Latitude','Longitude']].copy()
    for col in RPS.values():
        out[col] = np.nan

    try:
        import rasterio
        from rasterio.warp import transform
    except Exception:
        print('\n`rasterio` is required to read GeoTIFFs. Install with:')
        print('    pip install rasterio')
        print('\nThe script will still create a CSV with NaNs if no rasters are present.')
        # If rasterio not installed, just write NaNs and exit gracefully.
        OUT.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(OUT, index=False)
        print(f'Wrote placeholder output (all NaN) to: {OUT}')
        sys.exit(0)

    # The original WRI rasters are global.  Prefer local clips of the
    # Pakistan coast so inland points are outside the study footprint and
    # remain missing rather than looking like modeled zero-depth cells.
    raster_dir = CLIPPED_DIR if CLIPPED_DIR.exists() else AQUA_DIR
    print(f"Sampling rasters from: {raster_dir}")

    # for each return period, find a raster and sample
    for rp_code, colname in RPS.items():
        raster_path = find_raster_for_rp(raster_dir, rp_code)
        if raster_path is None:
            print(f'No raster found for {rp_code} in {AQUA_DIR} — column {colname} will be NaN')
            continue

        print(f'Using raster for {rp_code}: {raster_path.name}')

        with rasterio.open(raster_path) as src:
            nodata = src.nodata
            src_crs = src.crs
            bounds = src.bounds

            # prepare coordinate transform from WGS84 -> src_crs if needed
            lons = sites['Longitude'].values
            lats = sites['Latitude'].values
            if src_crs is None:
                xs, ys = lons, lats
            else:
                try:
                    xs, ys = transform('EPSG:4326', src_crs, lons.tolist(), lats.tolist())
                except Exception:
                    # fallback: assume raster already in 4326
                    xs, ys = lons, lats

            vals = []
            for x,y in zip(xs, ys):
                # check bounds (left, bottom, right, top)
                left, bottom, right, top = bounds
                if not (left <= x <= right and bottom <= y <= top):
                    vals.append(np.nan)
                    continue
                try:
                    samp = list(src.sample([(x,y)]))[0][0]
                except Exception:
                    vals.append(np.nan)
                    continue
                # handle masked / nodata
                if samp is None:
                    vals.append(np.nan)
                else:
                    try:
                        v = float(samp)
                    except Exception:
                        vals.append(np.nan)
                        continue
                    if nodata is not None and np.isclose(v, nodata):
                        vals.append(np.nan)
                    elif np.isnan(v):
                        vals.append(np.nan)
                    else:
                        vals.append(v)

            out[colname] = vals

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    # print summary
    print(f'Wrote output: {OUT} (rows: {len(out)})')
    for rp_code, colname in RPS.items():
        notnull = out[colname].notnull().sum()
        nulls = len(out) - notnull
        print(f"{colname}: real values={notnull}, nulls={nulls}")

if __name__ == '__main__':
    main()
