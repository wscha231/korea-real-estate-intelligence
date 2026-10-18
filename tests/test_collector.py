import json
import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import escape

from re_phase1.collector import (Partition, GateFailure, collect_partition,
                                 normalize_price_10k, parse_rtms_xml)
from re_phase1.legal_dong import (normalize_city_registry,
                                 assert_complete_pagination, write_verified_registry)


def xmlpage(total, data, page=None, rows=None, code="00"):
    items = "".join("<item><aptNm>" + escape(x) +
                    "</aptNm><dealAmount>123,450</dealAmount></item>" for x in data)
    page_meta = f"<pageNo>{page}</pageNo>" if page else ""
    rows_meta = f"<numOfRows>{rows}</numOfRows>" if rows else ""
    return (f"<response><header><resultCode>{code}</resultCode><resultMsg>OK</resultMsg></header>"
            f"<body><items>{items}</items><totalCount>{total}</totalCount>"
            f"{page_meta}{rows_meta}</body></response>").encode("utf-8")


class TestParse(unittest.TestCase):
    def test_parse_normal(self):
        p = parse_rtms_xml(xmlpage(1, ["A"], 1, 1))
        self.assertEqual((p.total_count, p.items_count, p.page_no, p.response_page_size), (1, 1, 1, 1))

    def test_parse_empty(self):
        self.assertEqual(parse_rtms_xml(xmlpage(0, [])).total_count, 0)

    def test_reject_html(self):
        with self.assertRaises(GateFailure):
            parse_rtms_xml(b"<html><body>Login</body></html>")

    def test_reject_doctype(self):
        with self.assertRaises(GateFailure):
            parse_rtms_xml(b"<!DOCTYPE foo><response/>")

    def test_reject_xml_api_error(self):
        with self.assertRaises(GateFailure) as cm:
            parse_rtms_xml(xmlpage(0, [], code="20"))
        self.assertEqual(cm.exception.status, "API_REJECTED")

    def test_reject_missing_count(self):
        with self.assertRaises(GateFailure):
            parse_rtms_xml(b"<response><header><resultCode>00</resultCode></header><body/></response>")

    def test_amount_unit(self):
        self.assertEqual(normalize_price_10k("123,456"), 123456)
        self.assertEqual(normalize_price_10k("123456"), 123456)
        for val in ("", "-10", "5.2", "1,23", None):
            with self.subTest(val=val), self.assertRaises(ValueError):
                normalize_price_10k(val)

    def test_invalid_partition(self):
        for lawd, ymd in (("1111", "202609"), ("11110", "202613"), ("11110", "200099")):
            with self.subTest(lawd=lawd, ymd=ymd), self.assertRaises(ValueError):
                Partition("trade_detail", lawd, ymd).validate()


class TestCollection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name)

    def go(self, pages, rows=2, cap=10):
        def mock(service, params, page_number):
            return pages[page_number]
        return collect_partition(Partition("trade_detail", "11110", "202609", rows, cap),
                                 self.dest, mock)

    def check_saved(self, receipt):
        base = (self.dest / "raw" / "rtms" / "trade_detail" / "contract_ymd=202609" /
                "lawd_5=11110" / ("run=" + receipt["run_id"]))
        disk = json.loads((base / "receipt.json").read_text())
        self.assertEqual(disk["status"], receipt["status"])
        from hashlib import sha256
        for page in receipt["pages"]:
            self.assertEqual(sha256((base / page["file"]).read_bytes()).hexdigest(), page["sha256"])
        return disk

    def test_complete_two_pages(self):
        r = self.go({1: xmlpage(3, ["one", "two"], 1, 2),
                     2: xmlpage(3, ["three"], 2, 2)})
        self.assertEqual(r["status"], "COMPLETE")
        self.assertEqual((r["official_total_count"], r["items_received"], r["completed_pages"]), (3, 3, 2))
        self.assertEqual(len(self.check_saved(r)["pages"]), 2)

    def test_zero(self):
        r = self.go({1: xmlpage(0, [], 1, 2)})
        self.assertEqual(r["status"], "CONFIRMED_ZERO")
        self.assertEqual(r["dataset_admission"], "BLOCKED")
        self.check_saved(r)

    def test_empty_but_total_positive(self):
        r = self.go({1: xmlpage(2, [], 1, 2)})
        self.assertEqual(r["status"], "PARTIAL")
        self.assertEqual(r["completed_pages"], 0)
        self.assertEqual(len(r["pages"]), 1)
        self.check_saved(r)

    def test_duplicate_page_payload(self):
        duplicate = xmlpage(4, ["same", "same"])
        r = self.go({1: duplicate, 2: duplicate})
        self.assertEqual(r["status"], "PARTIAL")
        self.assertEqual(r["reason"], "duplicate_response_page_payload")
        self.assertEqual(r["total_pages_saved"], 2)
        self.check_saved(r)

    def test_page_cap_fails_before_pagination(self):
        r = self.go({1: xmlpage(9, ["one", "two"], 1, 2)}, cap=2)
        self.assertEqual(r["reason"], "page_cap_below_official_total")
        self.check_saved(r)

    def test_totalcount_changes(self):
        r = self.go({1: xmlpage(3, ["one", "two"], 1, 2),
                     2: xmlpage(4, ["three"], 2, 2)})
        self.assertEqual(r["reason"], "totalCount_changed_between_pages")
        self.check_saved(r)

    def test_wrong_page_number(self):
        r = self.go({1: xmlpage(1, ["one"], 2, 2)})
        self.assertEqual(r["reason"], "pageNo_did_not_match_request")
        self.check_saved(r)

    def test_page_size_mismatch(self):
        r = self.go({1: xmlpage(1, ["one"], 1, 10)})
        self.assertEqual(r["reason"], "response_numOfRows_mismatch")

    def test_bad_code_not_zero(self):
        r = self.go({1: xmlpage(0, [], code="20")})
        self.assertEqual(r["status"], "API_REJECTED")
        self.assertNotEqual(r["status"], "CONFIRMED_ZERO")
        self.check_saved(r)

    def test_network_failure_not_zero(self):
        def bad(*_):
            raise GateFailure("G11", "FETCH_FAILED", "network_or_timeout")
        r = collect_partition(Partition("rent", "11110", "202609"), self.dest, bad)
        self.assertEqual(r["status"], "FETCH_FAILED")
        self.assertIsNone(r["official_total_count"])

    def test_runs_never_overwrite(self):
        a = self.go({1: xmlpage(0, [])})
        b = self.go({1: xmlpage(0, [])})
        self.assertNotEqual(a["run_id"], b["run_id"])
        self.check_saved(a)
        self.check_saved(b)


class TestLegalDong(unittest.TestCase):
    def test_region_normalization(self):
        source = [{"region_cd": "1100000000", "locatadd_nm": "서울"},
                  {"region_cd": "1111000000", "locatadd_nm": "서울 종로구"},
                  {"region_cd": "1111010100", "locatadd_nm": "서울 종로구 청운동"}]
        self.assertEqual([x["lawd_5"] for x in normalize_city_registry(source)], ["11110"])

    def test_duplicate_conflict(self):
        source = [{"region_cd": "1111000000", "locatadd_nm": "종로구"},
                  {"region_cd": "1111000000", "locatadd_nm": "다른명칭"}]
        with self.assertRaises(GateFailure):
            normalize_city_registry(source)

    def test_registry_complete_receipts(self):
        assert_complete_pagination([{"pageNo": 1, "totalCount": 3, "items": 2},
                                    {"pageNo": 2, "totalCount": 3, "items": 1}])
        with self.assertRaises(GateFailure):
            assert_complete_pagination([{"pageNo": 1, "totalCount": 3, "items": 2}])

    def test_write_registry_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            receipts = [{"pageNo": 1, "totalCount": 1, "items": 1}]
            write_verified_registry(path, [{"lawd_5": "11110"}], receipts, "2026-10-18")
            self.assertEqual(json.loads(path.read_text())["lawd_5_count"], 1)
            with self.assertRaises(FileExistsError):
                write_verified_registry(path, [{"lawd_5": "11110"}], receipts, "2026-10-18")


if __name__ == "__main__":
    unittest.main()
