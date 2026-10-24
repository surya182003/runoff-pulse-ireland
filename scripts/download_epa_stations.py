"""Download EPA Ireland water monitoring stations for the Cork Harbour / River Lee study area.

Fixes over the original version of this script:
* EPA publishes stations as MultiPoint geometries; the original accepted only Point and
  therefore silently discarded every station. MultiPoints are now normalised to Point.
* The study-area box now covers the whole of WFD Catchment 19 (the original western limit of
  -8.65 excluded the upper Lee: Macroom, Inchigeelagh, Gougane Barra).
* Results are paged, validated, de-duplicated by StationID and tagged with catchment membership
  using the official catchment polygon.

Usage (from the repository root):
    .\\.venv\\Scripts\\python.exe scripts\\download_epa_stations.py
"""

import _bootstrap  # noqa: F401

from app.config import get_settings
from app.ingest.common import AcquisitionError, make_client
from app.ingest.epa import download_catchment, download_stations


def main() -> None:
    data_dir = get_settings().data_dir
    print("Downloading EPA monitoring stations (Cork Harbour / River Lee study area)...")
    try:
        with make_client() as client:
            catchment = download_catchment(client, data_dir)
            count = download_stations(client, data_dir, catchment)
    except AcquisitionError as error:
        raise SystemExit(f"EPA download failed: {error}")
    print(f"Saved {count} stations to {data_dir / 'monitoring_stations.geojson'}")


if __name__ == "__main__":
    main()
