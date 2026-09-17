# =============================================================================
# real_estate_cleaning — Incremental Run Ingest
# Purpose: Validate one completed light-scraper run and create durable staging
#          inputs used by every downstream cleaning step.
# =============================================================================

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.staging import stage_completed_run, stage_full_rebuild


def parse_args():
    parser = argparse.ArgumentParser(
        description="Stage either one completed light-scraper run or an explicit full rebuild."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--run-dir",
        help="Path to data/runs/<run_id> produced by the light scraper.",
    )
    source.add_argument(
        "--full-file",
        action="append",
        dest="full_files",
        help=(
            "Historical raw CSV for a full rebuild. Repeat this option in "
            "the exact chronological processing order."
        ),
    )
    parser.add_argument(
        "--work-dir",
        default="data/work",
        help="Cleaning work directory. Defaults to data/work.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    work_dir = Path(args.work_dir)
    if args.run_dir:
        run = stage_completed_run(args.run_dir, work_dir)
        print(f"Validated incremental run: {run.run_id}")
    else:
        context = stage_full_rebuild(args.full_files, work_dir)
        print(
            f"Validated full rebuild input: {len(context['sources'])} files, "
            f"{context['row_count']:,} accepted rows"
        )
    print(f"Staging rows: {work_dir / 'df_staging.pkl'}")
    print(f"Staging actions: {work_dir / 'df_actions.pkl'}")
    print(f"Run context: {work_dir / 'run_context.json'}")


if __name__ == "__main__":
    main()
