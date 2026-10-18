#!/usr/bin/env python3
"""One explicitly approved RTMS partition. No API call unless --live."""
import argparse
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from re_phase1.collector import (Partition, collect_partition,
                                compact_report, fetch_page_http, ENDPOINTS)


def main():
    parser = argparse.ArgumentParser(description="Scope-limited RTMS collection, not nationwide")
    parser.add_argument("--service", choices=ENDPOINTS, required=True)
    parser.add_argument("--lawd", required=True, help="five-digit RTMS LAWD_CD; not HIRA code")
    parser.add_argument("--ymd", required=True, help="YYYYMM contract month")
    parser.add_argument("--rows", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--dest", default="./local_data", help="private local raw storage")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="zero network")
    mode.add_argument("--live", action="store_true", help="requires independently approved API key")
    args = parser.parse_args()

    spec = Partition(args.service, args.lawd, args.ymd, args.rows, args.max_pages)
    try:
        spec.validate()
    except ValueError as exc:
        parser.error(str(exc))
    if args.dry_run:
        print(json.dumps({"status": "DRY_RUN_VALIDATED",
                          "partition_id": f"{args.service}:{args.lawd}:{args.ymd}",
                          "max_pages": args.max_pages, "request_count": 0,
                          "raw_saved": False, "official_lawd_registry_verified": False}))
        return 0
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY", "").strip()
    if not key:
        print(json.dumps({"status": "PENDING_AUTH",
                          "reason": "DATA_GO_KR_SERVICE_KEY_not_set"}))
        return 2

    def fetch(service, public_params, page):
        return fetch_page_http(ENDPOINTS[service], {**public_params, "pageNo": page}, key)

    try:
        result = collect_partition(spec, Path(args.dest), fetch)
    except OSError:
        print(json.dumps({"status": "FETCH_FAILED", "reason": "local_storage_error"}))
        return 3
    print(json.dumps(compact_report(result), ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("COMPLETE", "CONFIRMED_ZERO") else 3


if __name__ == "__main__":
    sys.exit(main())
