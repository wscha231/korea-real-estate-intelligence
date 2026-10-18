"""Conservative current legal-dong registry normalizer; NOT a historic bridge."""
from __future__ import annotations
import json
import re
from collections import Counter
from pathlib import Path
from .collector import GateFailure


def normalize_city_registry(records: list[dict], *, region_code_field="region_cd") -> list[dict]:
    candidates = {}
    for record in records:
        code = str(record.get(region_code_field, "")).strip()
        if not re.fullmatch(r"[0-9]{10}", code):
            raise GateFailure("G08", "VERIFY_REQUIRED", "non_10_digit_region_code")
        if code[2:5] == "000" or code[5:] != "00000":
            continue
        name = str(record.get("locatadd_nm") or "").strip()
        if not name:
            raise GateFailure("G08", "VERIFY_REQUIRED", "region_name_missing")
        code5 = code[:5]
        if code5 in candidates and candidates[code5]["region_name"] != name:
            raise GateFailure("G08", "VERIFY_REQUIRED", "conflicting_sigungu_names")
        candidates[code5] = {
            "lawd_5": code5, "region_code_10": code,
            "region_name": name, "adpt_de": str(record.get("adpt_de") or "")
        }
    return sorted(candidates.values(), key=lambda x: x["lawd_5"])


def assert_complete_pagination(receipts: list[dict]) -> None:
    if not receipts:
        raise GateFailure("G01", "PARTIAL", "missing_registry_receipts")
    totals = {r.get("totalCount") for r in receipts}
    if len(totals) != 1 or not all(isinstance(t, int) and t >= 0 for t in totals):
        raise GateFailure("G01", "PARTIAL", "registry_totalCount_inconsistent")
    if Counter(r.get("pageNo") for r in receipts) != Counter(range(1, len(receipts) + 1)):
        raise GateFailure("G01", "PARTIAL", "registry_page_sequence_broken")
    if sum(r.get("items", -1000) for r in receipts) != next(iter(totals)):
        raise GateFailure("G01", "PARTIAL", "registry_item_count_mismatch")


def write_verified_registry(path: Path, entries: list[dict], receipts: list[dict], snapshot_at: str) -> None:
    assert_complete_pagination(receipts)
    if not entries:
        raise GateFailure("G01", "PARTIAL", "no_active_sigungu_entries")
    body = {
        "schema_version": 1, "snapshot_at": snapshot_at,
        "approval_scope": "CURRENT_REGISTRY_SNAPSHOT_ONLY",
        "historical_region_bridge": "PENDING",
        "lawd_5_count": len(entries), "entries": entries
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as out:
        json.dump(body, out, ensure_ascii=False, indent=2)
