"""Exercise manufacturing deliverables with synthetic, redistributable parts."""

import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from openpyxl import load_workbook

from hardware.components.reports import write_reports


def part(ipn="DN-R-001", lifecycle="active", candidates=True):
    evidence = {
        "status": lifecycle, "source_url": "https://manufacturer.example/lifecycle",
        "document_date": "2026-01-01", "checked_on": "2026-11-06",
        "scope": "Exact MPN", "note": "Manufacturer evidence, review before ordering",
    }
    return {
        "family": "resistor", "key": "resistor_10k", "manufacturer": "Maker A",
        "mpn": "R10K", "datasheet": "https://manufacturer.example/R10K.pdf",
        "specs": {"resistance_ohms": 10000, "power_w": 0.1, "package": "0603"},
        "lifecycle": evidence, "rohs": {**evidence, "status": "unverified"},
        "reach": {**evidence, "status": "unverified"},
        "suppliers": [
            {"name": "Distributor One", "sku": "123", "url": "https://supplier.example/123"},
            {"name": "Distributor Two", "sku": "456", "url": "https://supplier2.example/456"},
        ],
        "alternates": [{
            "manufacturer": "Maker B", "mpn": "ALT10K", "kind": "candidate",
            "datasheet": "https://makerb.example/ALT10K.pdf",
            "specs": {"resistance_ohms": 10000, "power_w": 0.125, "package": "0603"},
            "note": "Check temperature coefficient and assembly process",
        }] if candidates else [],
        "no_alternate_reason": "No reviewed second-source candidate" if not candidates else "",
        "refs": ["R1", "R2"], "quantity": 2, "ipn": ipn,
        "footprint": "Resistor_SMD:R_0603_1608Metric", "value": "10k",
    }


TEMPLATES = {"resistor": {
    "fields": {"resistance_ohms": "Resistance (ohms)", "power_w": "Power (W)"},
    "requirements": {"fire_smoke_toxicity": "Not specified for this prototype",
                     "shock_vibration": "Not specified for this prototype"},
    "alternate_rules": {"resistance_ohms": "equal", "power_w": "at_least", "package": "equal"},
}}


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name)

    def generate(self, parts=None, boards=10):
        return write_reports(parts or [part()], TEMPLATES, self.output, boards, "a" * 64)

    def workbook(self):
        workbook = load_workbook(self.output / "desk-node-cm.xlsx")
        self.addCleanup(workbook.close)
        return workbook

    def test_cm_batch_quantity_uses_editable_control_and_review_hold(self):
        self.generate()
        wb = self.workbook()
        self.assertEqual(wb["Build"]["B2"].value, 10)
        bom = wb["CM BOM"]
        headers = {cell.value: cell.column for cell in bom[1]}
        self.assertEqual(bom.cell(2, headers["Qty per board"]).value, 2)
        self.assertEqual(bom.cell(2, headers["Batch qty"]).value,
                         "=H2*'Build'!$B$2")
        self.assertEqual(bom.cell(2, headers["References"]).value, "R1, R2")
        self.assertIn("HOLD", bom.cell(2, headers["Release status"]).value)
        self.assertEqual(bom.freeze_panes, "A2")
        self.assertGreaterEqual(bom.row_dimensions[2].height, 45)
        self.assertTrue(bom.auto_filter.ref)
        self.assertEqual(bom.cell(2, headers["Datasheet"]).hyperlink.target,
                         "https://manufacturer.example/R10K.pdf")

    def test_evidence_does_not_inherit_primary_compliance_for_candidate(self):
        self.generate()
        wb = self.workbook()
        evidence = list(wb["Evidence"].values)
        candidate_rows = [row for row in evidence[1:] if row[1] == "candidate"]
        self.assertEqual(len(candidate_rows), 3)
        self.assertEqual({row[5] for row in candidate_rows}, {"unverified"})
        specs = list(wb["Specifications"].values)
        self.assertTrue(any("fire_smoke_toxicity" in row for row in specs))
        self.assertTrue(any("shock_vibration" in row for row in specs))
        alternates = list(wb["Alternates"].values)
        self.assertTrue(any("at_least" in row and "passes rule only" in row for row in alternates))
        self.assertTrue(all(any(isinstance(cell, str) and "NOT QUALIFIED" in cell for cell in row)
                            for row in alternates[1:]))

    def test_risk_priority_changes_with_lifecycle_and_is_deterministic(self):
        a, b = part("A"), part("B", lifecycle="eol", candidates=False)
        report = self.generate([a, b])
        self.assertEqual([(row["ipn"], row["score"]) for row in report["parts"]],
                         [("B", 85), ("A", 20)])
        first_json = (self.output / "report.json").read_bytes()
        first_md = (self.output / "risk.md").read_bytes()
        self.generate([b, a])
        self.assertEqual((self.output / "report.json").read_bytes(), first_json)
        self.assertEqual((self.output / "risk.md").read_bytes(), first_md)
        self.assertEqual(json.loads(first_json)["bom_sha256"], "a" * 64)
        a["lifecycle"]["status"] = "eol"
        b["lifecycle"]["status"] = "active"
        changed = self.generate([a, b])
        self.assertEqual(changed["parts"][0]["ipn"], "A")
        self.assertIn("not a predicted probability", first_md.decode())

    def test_supplier_count_cannot_substitute_for_manufacturer_diversity(self):
        row = part(candidates=False)
        report = self.generate([row])
        self.assertEqual(report["parts"][0]["score"], 35)
        row["alternates"] = [{**part()["alternates"][0], "manufacturer": "Maker A"}]
        report = self.generate([row])
        self.assertEqual(report["parts"][0]["score"], 35)

    def test_missing_lifecycle_evidence_adds_review_priority(self):
        row = part()
        row["lifecycle"] = {"status": "active"}
        report = self.generate([row])
        self.assertEqual(report["parts"][0]["score"], 30)
        self.assertIn("manufacturer lifecycle", " ".join(report["parts"][0]["reasons"]))

    def test_reported_nrnd_keeps_priority_when_dated_evidence_is_unverified(self):
        row = part()
        row["lifecycle"].update(status="unverified", reported_status="nrnd", document_date="")
        report = self.generate([row])
        self.assertEqual(report["parts"][0]["score"], 65)
        self.assertIn("manufacturer reports NRND; dated evidence unverified",
                      " ".join(report["parts"][0]["reasons"]))

    def test_noncompliant_evidence_is_explicitly_held(self):
        row = part()
        row["rohs"]["status"] = "noncompliant"
        report = self.generate([row])
        self.assertIn("HOLD", report["parts"][0]["release_status"])
        self.assertIn("NONCOMPLIANT", " ".join(report["parts"][0]["reasons"]))

    def test_untrusted_text_never_becomes_an_excel_formula(self):
        row = part()
        row["value"] = '=HYPERLINK("https://evil.example","click")'
        row["mpn"] = "+cmd|malicious"
        row["alternates"][0]["note"] = "@SUM(A1:A2)"
        row["lifecycle"]["note"] = "\t=1+1"
        row["datasheet"] = "javascript:alert(1)"
        self.generate([row])
        wb = self.workbook()
        formulas = [(sheet.title, cell.coordinate) for sheet in wb for cells in sheet
                    for cell in cells if cell.data_type == "f"]
        self.assertEqual(formulas, [("CM BOM", "I2")])
        bom = wb["CM BOM"]
        self.assertIsNone(bom["K2"].hyperlink)
        self.assertEqual(bom["E2"].data_type, "s")

    def test_invalid_build_count_does_not_write_a_package(self):
        for boards in (0, -1, 1.5, True):
            with self.subTest(boards=boards), self.assertRaises(ValueError):
                self.generate(boards=boards)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_real_catalogue_handoff_covers_every_fitted_reference(self):
        from hardware.components.core import parse_bom, prepare
        root = Path(__file__).resolve().parents[1]
        if not (root / "catalog.json").exists() or not (root / "templates.json").exists():
            self.skipTest("Real catalogue/template data not present; synthetic package tests still run")
        catalogue = json.loads((root / "catalog.json").read_text())
        templates = json.loads((root / "templates.json").read_text())
        bom_path = root.parent / "bom.csv"
        with bom_path.open() as stream:
            bom = parse_bom(stream)
        prepared = prepare(bom, catalogue, templates)
        report = write_reports(prepared, templates, self.output, 7,
                               hashlib.sha256(bom_path.read_bytes()).hexdigest())
        wb = self.workbook()
        self.assertEqual(wb["CM BOM"].max_row - 1, len(bom))
        self.assertEqual(sum(row[7] for row in list(wb["CM BOM"].values)[1:]),
                         sum(item["quantity"] for item in bom))
        self.assertEqual(sorted(ref for row in report["parts"] for ref in row["refs"]),
                         sorted(ref for row in bom for ref in row["refs"]))
        self.assertTrue(all("HOLD" in row["release_status"] for row in report["parts"]))


if __name__ == "__main__":
    unittest.main()
