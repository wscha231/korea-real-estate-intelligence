#!/usr/bin/env python3
"""Current 10-digit legal-dong registry. No network unless --live."""
import argparse
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from re_phase1.region_collector import collect_current_region_registry, fetch_region_page


def main():
    parser = argparse.ArgumentParser(description="Current legal-dong snapshot; not historical code bridge")
    parser.add_argument("--dest", default="./local_data")
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=100)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.rows <= 1000 or not 1 <= args.max_pages <= 100:
        parser.error("page controls out of bounds")
    if args.dry_run:
        print(json.dumps({"status": "DRY_RUN_VALIDATED", "request_count": 0,
                          "operation": "StanReginCd/getStanReginCdList",
                          "historical_code_coverage": "NOT_VERIFIED"}))
        return 0
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY", "").strip()
    if not key:
        print(json.dumps({"status": "PENDING_AUTH",
                          "reason": "DATA_GO_KR_SERVICE_KEY_not_set"}))
        return 2
    try:
        result = collect_current_region_registry(
            Path(args.dest), lambda page, size: fetch_region_page(key, page, size),
            page_size=args.rows, max_pages=args.max_pages)
    except OSError:
        print(json.dumps({"status": "FETCH_FAILED", "reason": "local_storage_error"}))
        return 3
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("pages", "endpoint")}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "CURRENT_REGISTRY_COMPLETE" else 3


if __name__ == "__main__":
    sys.exit(main())
