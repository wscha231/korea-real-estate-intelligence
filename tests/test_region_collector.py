import json
import tempfile
import unittest
from pathlib import Path
from re_phase1.region_collector import parse_region_xml, collect_current_region_registry
from re_phase1.collector import GateFailure


def xml(total, records, code="INFO-0"):
    items = "".join("<row>" + "".join(f"<{k}>{v}</{k}>" for k, v in rec.items()) +
                    "</row>" for rec in records)
    return (f"<response><header><resultCode>{code}</resultCode></header><body>"
            f"<items>{items}</items><totalCount>{total}</totalCount></body></response>").encode("utf-8")


class TestRegion(unittest.TestCase):
    def test_parse_valid(self):
        row = {"region_cd": "1111000000", "locatadd_nm": "서울 종로구"}
        count, rows = parse_region_xml(xml(1, [row]))
        self.assertEqual(count, 1)
        self.assertEqual(rows[0]["region_cd"], row["region_cd"])

    def test_reject_api_error(self):
        with self.assertRaises(GateFailure):
            parse_region_xml(xml(0, [], code="20"))

    def test_reject_bad_row_code(self):
        with self.assertRaises(GateFailure):
            parse_region_xml(xml(1, [{"region_cd": "11110"}]))

    def test_collect_full_registry_snapshot(self):
        pages = {
            1: xml(2, [{"region_cd": "1111000000", "locatadd_nm": "서울 종로구"}]),
            2: xml(2, [{"region_cd": "1114000000", "locatadd_nm": "서울 중구"}])
        }
        with tempfile.TemporaryDirectory() as tmp:
            got = collect_current_region_registry(Path(tmp), lambda n, size: pages[n], page_size=1)
            self.assertEqual(got["status"], "CURRENT_REGISTRY_COMPLETE")
            self.assertEqual(got["lawd_5_count"], 2)
            root = Path(tmp) / "raw" / "region_codes" / ("run=" + got["run_id"])
            parsed = json.loads((root / "current_sigungu_verified.json").read_text())
            self.assertEqual(parsed["historical_region_bridge"], "PENDING")

    def test_partial_not_approved(self):
        pages = {1: xml(3, [{"region_cd": "1111000000", "locatadd_nm": "서울 종로구"}])}
        with tempfile.TemporaryDirectory() as tmp:
            got = collect_current_region_registry(Path(tmp), lambda n, size: pages[n],
                                                   page_size=1, max_pages=1)
            self.assertEqual(got["status"], "PARTIAL")
            self.assertFalse(got["current_code_registry_complete"])


if __name__ == "__main__":
    unittest.main()
