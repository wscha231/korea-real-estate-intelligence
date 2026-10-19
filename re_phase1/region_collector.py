"""Current 10-digit legal-dong code page collector; history is not inferred."""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from uuid import uuid4
from xml.etree import ElementTree as ET

from .collector import GateFailure, NoRedirect, MAX_HTTP_BYTES, save_immutable
from .legal_dong import assert_complete_pagination, normalize_city_registry

ENDPOINT = "https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"
SUCCESS_CODES = {"INFO-0", "00", "000"}


def parse_region_xml(payload: bytes) -> tuple[int, list[dict]]:
    if not isinstance(payload, bytes) or len(payload) > MAX_HTTP_BYTES:
        raise GateFailure("G01", "SCHEMA_CHANGED", "region_response_too_large")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise GateFailure("G01", "SCHEMA_CHANGED", "forbidden_xml_declaration")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise GateFailure("G01", "SCHEMA_CHANGED", "region_response_not_xml") from None
    code = (root.findtext(".//resultCode") or "").strip()
    if code not in SUCCESS_CODES:
        raise GateFailure("G00", "API_REJECTED", "region_api_result_" + (code or "MISSING")[:20])
    count_raw = (root.findtext(".//totalCount") or "").strip()
    if not count_raw.isdigit():
        raise GateFailure("G01", "SCHEMA_CHANGED", "region_totalCount_missing")
    total = int(count_raw)
    rows = root.findall(".//row") or root.findall(".//item")
    if total > 0 and not rows:
        raise GateFailure("G01", "SCHEMA_CHANGED", "region_rows_missing")
    records = [{child.tag: (child.text or "").strip() for child in row} for row in rows]
    for record in records:
        if len(record.get("region_cd", "")) != 10:
            raise GateFailure("G08", "VERIFY_REQUIRED", "region_cd_missing_or_wrong_width")
    return total, records


def fetch_region_page(key: str, page: int, page_size: int = 1000) -> bytes:
    if not key:
        raise GateFailure("G00", "PENDING_AUTH", "missing_service_key")
    params = {"ServiceKey": key, "pageNo": page, "numOfRows": page_size, "type": "xml"}
    req = Request(ENDPOINT + "?" + urlencode(params), headers={"User-Agent": "RealEstatePhase1/1.1"})
    try:
        with build_opener(NoRedirect()).open(req, timeout=30) as response:
            if response.status != 200:
                raise GateFailure("G11", "FETCH_FAILED", "not_http_200")
            payload = response.read(MAX_HTTP_BYTES + 1)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise GateFailure("G00", "PENDING_AUTH", "auth_or_service_not_approved") from None
        raise GateFailure("G11", "FETCH_FAILED", "region_http_failure_" + str(exc.code)) from None
    except (URLError, TimeoutError, OSError):
        raise GateFailure("G11", "FETCH_FAILED", "region_network_or_timeout") from None
    if len(payload) > MAX_HTTP_BYTES:
        raise GateFailure("G01", "SCHEMA_CHANGED", "region_response_too_large")
    return payload


def collect_current_region_registry(dest: Path, fetch, *, page_size: int = 1000, max_pages: int = 100) -> dict:
    if not 1 <= page_size <= 1000 or not 1 <= max_pages <= 100:
        raise ValueError("invalid_page_size_or_cap")
    now = datetime.now(timezone.utc)
    run = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12]
    root = Path(dest) / "raw" / "region_codes" / ("run=" + run)
    receipt = {
        "source_id": "legal_dong_current", "run_id": run,
        "started_at": now.isoformat(), "endpoint": ENDPOINT,
        "status": "PENDING", "reason": None, "gate": None,
        "total_records": None, "rows_received": 0, "pages": [],
        "historical_code_coverage": False, "dataset_admission": "BLOCKED",
        "approved_usage": "CURRENT_SNAPSHOT_ONLY",
        "national_transaction_coverage": False,
        "current_code_registry_complete": False
    }
    page_receipts = []
    records = []
    planned = None
    try:
        for page_no in range(1, max_pages + 1):
            raw = fetch(page_no, page_size)
            digest = hashlib.sha256(raw).hexdigest()
            filename = f"page-{page_no:05d}.xml"
            save_immutable(root / filename, raw)
            entry = {"pageNo": page_no, "file": filename, "sha256": digest,
                     "bytes": len(raw), "validated": False}
            receipt["pages"].append(entry)
            total, parsed = parse_region_xml(raw)
            if receipt["total_records"] is None:
                receipt["total_records"] = total
                planned = max(1, math.ceil(total / page_size))
                if planned > max_pages:
                    raise GateFailure("G01", "PARTIAL", "region_page_cap_insufficient")
            elif total != receipt["total_records"]:
                raise GateFailure("G01", "PARTIAL", "region_count_changed_during_collection")
            expected = max(0, min(page_size, total - (page_no - 1) * page_size))
            if len(parsed) != expected:
                raise GateFailure("G01", "PARTIAL", "region_page_count_mismatch")
            entry.update({"validated": True, "items": len(parsed)})
            page_receipts.append({"pageNo": page_no, "totalCount": total, "items": len(parsed)})
            records.extend(parsed)
            receipt["rows_received"] += len(parsed)
            if page_no >= planned:
                break
        assert_complete_pagination(page_receipts)
        regions = normalize_city_registry(records)
        if not regions:
            raise GateFailure("G01", "PARTIAL", "empty_sigungu_registry")
        save_immutable(root / "current_sigungu_verified.json",
                       json.dumps({
                           "schema_version": 1, "snapshot_at": now.isoformat(),
                           "approval_scope": "CURRENT_REGISTRY_SNAPSHOT_ONLY",
                           "historical_region_bridge": "PENDING",
                           "lawd_5_count": len(regions), "entries": regions,
                           "provenance": {
                               "source_id": "legal_dong_current", "run_id": run,
                               "totalCount": receipt["total_records"],
                               "page_sha256": [p["sha256"] for p in receipt["pages"]]
                           }
                       }, ensure_ascii=False, indent=2).encode("utf-8"))
        receipt["lawd_5_count"] = len(regions)
        receipt["status"] = "CURRENT_REGISTRY_COMPLETE"
        receipt["current_code_registry_complete"] = True
    except GateFailure as exc:
        receipt.update({"status": exc.status, "reason": exc.reason, "gate": exc.gate})
    finally:
        receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_immutable(root / "receipt.json",
                       json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8"))
    return receipt
