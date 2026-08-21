"""Clip downloaded Aqueduct coastal rasters to the Pakistan coastal study area."""

from pathlib import Path

import rasterio
from rasterio.windows import from_bounds, transform as window_transform


BASE = Path(__file__).resolve().parent.parent
SOURCE_DIR = BASE / "data" / "aqueduct_coastal"
OUTPUT_DIR = SOURCE_DIR / "pakistan_coast"
BBOX = (65.0, 23.0, 69.0, 27.0)  # west, south, east, north


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sources = sorted(SOURCE_DIR.glob("inuncoast_historical_nosub_hist_rp*.tif"))
    if not sources:
        raise FileNotFoundError(f"No historical no-subsidence coastal rasters in {SOURCE_DIR}")

    for source_path in sources:
        target_path = OUTPUT_DIR / source_path.name
        with rasterio.open(source_path) as src:
            window = from_bounds(*BBOX, transform=src.transform).round_offsets().round_lengths()
            profile = src.profile.copy()
            profile.update(
                height=int(window.height),
                width=int(window.width),
                transform=window_transform(window, src.transform),
            )
            with rasterio.open(target_path, "w", **profile) as dst:
                dst.write(src.read(1, window=window), 1)
        print(f"Wrote {target_path.name}: {int(window.width)} x {int(window.height)} pixels")


if __name__ == "__main__":
    main()
