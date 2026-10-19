"""Fail-closed RTMS apartment collector: one service × LAWD-5 × contract month.

Source reuse: preserves Phase 1 v1.1 API, partition receipts and failure states.
COMPLETE is not nationwide/source-license/model-input approval.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4
from xml.etree import ElementTree as ET

ENDPOINTS = {
    "trade_detail": "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    "trade_basic": "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
    "rent": "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
}
SUCCESS_CODES = {"00", "000"}
MAX_HTTP_BYTES = 12_000_000


class GateFailure(Exception):
    def __init__(self, gate: str, status: str, reason: str):
        super().__init__(reason)
        self.gate, self.status, self.reason = gate, status, reason


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None


@dataclass(frozen=True)
class Partition:
    service: str
    lawd_5: str
    contract_ymd: str
    rows_per_page: int = 100
    max_pages: int = 10

    def validate(self):
        if self.service not in ENDPOINTS:
            raise ValueError("unapproved_api_service")
        if not re.fullmatch(r"[0-9]{5}", self.lawd_5):
            raise ValueError("lawd_must_be_five_digits")
        if not re.fullmatch(r"20[0-9]{4}", self.contract_ymd):
            raise ValueError("invalid_YYYYMM")
        yr, mo = int(self.contract_ymd[:4]), int(self.contract_ymd[4:])
        if not 2000 <= yr <= datetime.now(timezone.utc).year + 1 or not 1 <= mo <= 12:
            raise ValueError("invalid_contract_month")
        if not 1 <= self.rows_per_page <= 1000 or not 1 <= self.max_pages <= 100:
            raise ValueError("page_size_or_cap_exceeded")

    @property
    def public_params(self):
        return {"LAWD_CD": self.lawd_5, "DEAL_YMD": self.contract_ymd,
                "numOfRows": self.rows_per_page}


@dataclass(frozen=True)
class Page:
    result_code: str
    total_count: int
    items_count: int
    page_no: int | None
    response_page_size: int | None
    fields_first_item: tuple[str, ...]
    xml_body: bytes


def parse_rtms_xml(payload: bytes) -> Page:
    if not isinstance(payload, bytes) or len(payload) > MAX_HTTP_BYTES:
        raise GateFailure("G02", "SCHEMA_CHANGED", "response_size_or_type")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise GateFailure("G02", "SCHEMA_CHANGED", "forbidden_xml_declaration")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise GateFailure("G02", "SCHEMA_CHANGED", "invalid_xml") from None
    result = (root.findtext(".//header/resultCode") or root.findtext(".//resultCode") or "").strip()
    if result not in SUCCESS_CODES:
        # Never print resultMsg; it could contain the credential or full request URL.
        raise GateFailure("G02", "API_REJECTED", "api_result_" + (result or "MISSING")[:20])
    total_raw = (root.findtext(".//body/totalCount") or root.findtext(".//totalCount") or "").strip()
    if not total_raw.isdigit() or int(total_raw) > 10_000_000:
        raise GateFailure("G03", "SCHEMA_CHANGED", "totalCount_not_valid")
    items = root.findall(".//body/items/item") or root.findall(".//items/item")

    def optional_positive(path):
        raw = (root.findtext(".//body/" + path) or root.findtext(".//" + path) or "").strip()
        if not raw:
            return None
        if not raw.isdigit() or int(raw) < 1:
            raise GateFailure("G03", "SCHEMA_CHANGED", "page_metadata_invalid")
        return int(raw)

    return Page(result, int(total_raw), len(items), optional_positive("pageNo"),
                optional_positive("numOfRows"),
                tuple(sorted(child.tag for child in items[0])) if items else tuple(), payload)


def normalize_price_10k(raw: str) -> int:
    """Return the integer *10,000 KRW* amount; never silently convert to KRW."""
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})*|[0-9]+", raw.strip()):
        raise ValueError("invalid_deal_amount")
    return int(raw.strip().replace(",", ""))


def fetch_page_http(endpoint: str, params_public: dict, key: str, timeout: int = 25) -> bytes:
    if endpoint not in ENDPOINTS.values() or not key:
        raise GateFailure("G00", "PENDING_AUTH", "endpoint_or_key_unavailable")
    request = Request(endpoint + "?" + urlencode({"serviceKey": key, **params_public}),
                      headers={"User-Agent": "KoreaRealEstatePhase1/1.1"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            if response.status != 200:
                raise GateFailure("G11", "FETCH_FAILED", "not_http_200")
            body = response.read(MAX_HTTP_BYTES + 1)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise GateFailure("G00", "PENDING_AUTH", "auth_or_service_not_approved") from None
        raise GateFailure("G11", "FETCH_FAILED", "http_failure_" + str(exc.code)) from None
    except (URLError, TimeoutError, OSError):
        raise GateFailure("G11", "FETCH_FAILED", "network_or_timeout") from None
    if len(body) > MAX_HTTP_BYTES:
        raise GateFailure("G02", "SCHEMA_CHANGED", "oversized_response")
    return body


def save_immutable(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def collect_partition(spec: Partition, dest: Path, fetch, *, now=None) -> dict:
    """fetch(service, params_without_key, page_no) -> bytes, injected for offline tests."""
    spec.validate()
    now = now or (lambda: datetime.now(timezone.utc))
    run_id = now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12]
    root = (Path(dest) / "raw" / "rtms" / spec.service /
            ("contract_ymd=" + spec.contract_ymd) /
            ("lawd_5=" + spec.lawd_5) / ("run=" + run_id))
    receipt = {
        "format_version": 1, "source_id": spec.service, "endpoint": ENDPOINTS[spec.service],
        "run_id": run_id,
        "partition_id": f"{spec.service}:{spec.lawd_5}:{spec.contract_ymd}",
        "public_request": spec.public_params,
        "started_at": now().isoformat(), "reference_period": spec.contract_ymd,
        "status": "PENDING", "reason": None, "gate": None,
        "official_total_count": None, "items_received": 0,
        "completed_pages": 0, "planned_pages": None, "pages": [],
        "dataset_admission": "BLOCKED", "national_coverage": False,
        "historical_revision_coverage": False, "commercial_use_rights": "NOT_VERIFIED",
        "first_public_availability_at": "UNKNOWN", "raw_retention_policy": "local_immutable",
        "credentials_in_evidence": False
    }
    expected_total = None
    planned = None
    fingerprints = set()
    try:
        for page_no in range(1, spec.max_pages + 1):
            payload = fetch(spec.service, dict(spec.public_params), page_no)
            if not isinstance(payload, bytes):
                raise GateFailure("G02", "SCHEMA_CHANGED", "transport_non_bytes")
            digest = hashlib.sha256(payload).hexdigest()
            filename = f"page-{page_no:05d}.xml"
            save_immutable(root / filename, payload)
            info = {"page": page_no, "file": filename, "sha256": digest,
                    "bytes": len(payload), "validated": False, "items": None,
                    "retrieved_at": now().isoformat()}
            receipt["pages"].append(info)
            page = parse_rtms_xml(payload)
            if digest in fingerprints:
                raise GateFailure("G03", "PARTIAL", "duplicate_response_page_payload")
            fingerprints.add(digest)
            if expected_total is None:
                expected_total = page.total_count
                planned = max(1, math.ceil(expected_total / spec.rows_per_page))
                receipt["official_total_count"], receipt["planned_pages"] = expected_total, planned
                if planned > spec.max_pages:
                    raise GateFailure("G03", "PARTIAL", "page_cap_below_official_total")
            elif page.total_count != expected_total:
                raise GateFailure("G03", "PARTIAL", "totalCount_changed_between_pages")
            if page.page_no is not None and page.page_no != page_no:
                raise GateFailure("G03", "PARTIAL", "pageNo_did_not_match_request")
            if page.response_page_size is not None and page.response_page_size != spec.rows_per_page:
                raise GateFailure("G03", "PARTIAL", "response_numOfRows_mismatch")
            expected_here = max(0, min(spec.rows_per_page, expected_total - (page_no - 1) * spec.rows_per_page))
            if page.items_count != expected_here:
                raise GateFailure("G03", "PARTIAL", "page_item_count_mismatch")
            info.update({"validated": True, "items": page.items_count, "result_code": page.result_code,
                         "first_row_schema": list(page.fields_first_item)})
            receipt["items_received"] += page.items_count
            receipt["completed_pages"] += 1
            if page_no >= planned:
                break
        if receipt["completed_pages"] != planned or receipt["items_received"] != expected_total:
            raise GateFailure("G03", "PARTIAL", "aggregate_incomplete")
        receipt["status"] = "CONFIRMED_ZERO" if expected_total == 0 else "COMPLETE"
    except GateFailure as exc:
        receipt.update({"gate": exc.gate, "status": exc.status, "reason": exc.reason})
    except OSError:
        receipt.update({"gate": "G10", "status": "FETCH_FAILED", "reason": "local_storage_error"})
    finally:
        receipt["finished_at"] = now().isoformat()
        receipt["total_pages_saved"] = len(receipt["pages"])
        save_immutable(root / "receipt.json",
                       json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
    return receipt


def compact_report(evidence: dict) -> dict:
    keys = ("partition_id", "status", "gate", "reason", "official_total_count",
            "items_received", "completed_pages", "planned_pages", "run_id", "dataset_admission")
    return {key: evidence.get(key) for key in keys}
