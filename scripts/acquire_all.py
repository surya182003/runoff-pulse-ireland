"""Run every RunoffPulse data acquisition step and print a provenance summary.

Each source is attempted independently: a failing upstream service is reported and the
remaining sources still run. Nothing is fabricated when a source fails; the previous file
(if any) is left in place and the manifest keeps its earlier retrieval time.

Usage (from the repository root):
    .\\.venv\\Scripts\\python.exe scripts\\acquire_all.py [--only epa,met,bathing,opw]
"""

import argparse
import traceback

import _bootstrap  # noqa: F401

from app.config import get_settings
from app.ingest.bathing import acquire_bathing
from app.ingest.common import make_client
from app.ingest.epa import acquire_epa
from app.ingest.met import acquire_met
from app.ingest.opw import acquire_opw

STEPS = {
    "epa": ("EPA GeoServer layers (stations, catchment, rivers, waterbodies, shellfish waters)", acquire_epa),
    "met": ("Met Éireann rainfall (Cork Airport)", acquire_met),
    "bathing": ("EPA bathing water API", acquire_bathing),
    "opw": ("OPW waterlevel.ie hydrometric snapshot", acquire_opw),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="Comma-separated subset of: " + ",".join(STEPS))
    args = parser.parse_args()
    selected = args.only.split(",") if args.only else list(STEPS)

    data_dir = get_settings().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    with make_client(timeout=120) as client:
        for key in selected:
            title, step = STEPS[key]
            print(f"\n==> {title}")
            try:
                for name, count in step(client, data_dir).items():
                    print(f"    {name:<26} {count}")
            except Exception as error:  # keep going: other sources are independent
                failures += 1
                print(f"    FAILED: {error}")
                traceback.print_exc(limit=1)
    print(f"\nData directory: {data_dir}")
    print("Done." if not failures else f"Completed with {failures} failed source(s); see messages above.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
