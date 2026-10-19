#!/usr/bin/env python3
"""Zero-network scope preview from a current legal-dong manifest."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from re_phase1.collector import Partition


def months(a: str, b: str):
    y, m = int(a[:4]), int(a[4:])
    end = (int(b[:4]), int(b[4:]))
    if (y, m) > end:
        raise ValueError("from-month after to-month")
    out = []
    while (y, m) <= end:
        out.append(f"{y:04}{m:02}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        if len(out) > 120:
            raise ValueError("plan exceeds 120 months")
    return out


def main():
    parser = argparse.ArgumentParser(description="Offline-only planner; not authorized collection")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--from-month", required=True)
    parser.add_argument("--to-month", required=True)
    parser.add_argument("--max-partitions", type=int, default=10_000)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    doc = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    if (doc.get("approval_scope") != "CURRENT_REGISTRY_SNAPSHOT_ONLY" or
            doc.get("lawd_5_count") != len(doc.get("entries", []))):
        parser.error("verified current registry manifest required")
    try:
        pairs = [(row["lawd_5"], month)
                 for row in doc["entries"]
                 for month in months(args.from_month, args.to_month)]
        for code, month in pairs:
            Partition("trade_detail", code, month).validate()
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))
    if not pairs or len(pairs) > args.max_partitions:
        parser.error("partition cap violated or empty")
    plan = {
        "schema_version": 1, "execution": "NOT_AUTHORIZED", "network_requests": 0,
        "registry_snapshot_at": doc["snapshot_at"],
        "historical_code_coverage": "NOT_VERIFIED",
        "contract_period": [args.from_month, args.to_month],
        "partition_count_per_service": len(pairs),
        "total_trade_plus_rent_partitions": len(pairs) * 2,
        "partitions": [{"lawd_5": code, "contract_ymd": month} for code, month in pairs]
    }
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: val for key, val in plan.items()
                      if key != "partitions"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
