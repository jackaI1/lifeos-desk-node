"""Generate a review-held contract manufacturer package from catalogue data.

This module deliberately performs no network requests or component approval. The
JSON and Markdown are deterministic for the same inputs. Excel recalculates its
batch quantities when opened in an application with formula support.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
from numbers import Real
from pathlib import Path
from urllib.parse import urlsplit

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.properties import CalcProperties


LIFECYCLE_WEIGHTS = {"active": 0, "nrnd": 35, "eol": 50, "unverified": 20}
COMPLIANT = {"compliant", "compliant_with_exemptions", "conformant", "verified"}
CLAIMS = ("lifecycle", "rohs", "reach")
HOLD = "HOLD: engineering review and board validation required"


def _text(value):
    """Keep supplied strings as literal Excel text, including formula prefixes."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _row(sheet, values):
    sheet.append(values)
    for cell in sheet[sheet.max_row]:
        if isinstance(cell.value, str):
            # Setting the explicit type protects even strings starting with =,
            # +, -, @, whitespace, or tabs without changing component identity.
            cell.data_type = "s"


def _link(cell, url):
    url = _text(url)
    if urlsplit(url).scheme in {"https", "http"} and urlsplit(url).netloc:
        cell.hyperlink = url
        cell.font = Font(color="0563C1", underline="single")


def _evidence(part, claim):
    evidence = part.get(claim) or {}
    return {
        "status": evidence.get("status") or "unverified",
        "reported_status": evidence.get("reported_status") or "",
        "source_url": evidence.get("source_url") or "",
        "document_date": evidence.get("document_date") or "",
        "checked_on": evidence.get("checked_on") or "",
        "scope": evidence.get("scope") or "Unverified for exact MPN",
        "note": evidence.get("note") or "Obtain and review manufacturer evidence for the exact MPN.",
    }


def _risk(part):
    lifecycle = _evidence(part, "lifecycle")
    state = lifecycle["status"].lower()
    reported = lifecycle["reported_status"].lower()
    if reported and LIFECYCLE_WEIGHTS.get(reported, 0) > LIFECYCLE_WEIGHTS.get(state, 20):
        state = reported
    score = LIFECYCLE_WEIGHTS.get(state, 20)
    reasons = []
    if lifecycle["status"].lower() == "unverified" and reported:
        reasons.append(f"manufacturer reports {reported.upper()}; dated evidence unverified: obtain a dated exact-MPN declaration.")
    if state == "eol":
        reasons.append("Lifecycle EOL (+50): confirm last-order dates and redesign or qualify a replacement.")
    elif state == "nrnd":
        reasons.append("Lifecycle NRND (+35): avoid new production dependency; qualify a replacement.")
    elif state != "active":
        reasons.append("Lifecycle unverified (+20): obtain the manufacturer's current exact-MPN status.")
    if not all(lifecycle[field] for field in ("source_url", "document_date", "checked_on")) or lifecycle["scope"].startswith("Unverified"):
        score += 10
        reasons.append("Missing manufacturer lifecycle evidence (+10): record a source, document date, check date and exact-MPN scope.")
    manufacturer = _text(part.get("manufacturer")).strip().casefold()
    diverse = any(
        _text(candidate.get("manufacturer")).strip().casefold() not in {"", manufacturer}
        for candidate in part.get("alternates", [])
    )
    if diverse:
        score += 10
        reasons.append("Other-manufacturer candidates only (+10): compare specifications and qualify on the board before substitution.")
    else:
        score += 25
        reasons.append("No other-manufacturer alternate (+25): find a second source or document an accepted single-source plan.")
    for claim in ("rohs", "reach"):
        evidence = _evidence(part, claim)
        if evidence["status"].lower() not in COMPLIANT or not evidence["source_url"]:
            score += 5
            reasons.append(f"{claim.upper()} unverified or unresolved (+5): obtain and review an exact-MPN manufacturer declaration.")
        if evidence["status"].lower() in {"noncompliant", "non-compliant"}:
            reasons.append(f"HOLD: {claim.upper()} NONCOMPLIANT; resolve material compliance before release.")
    return min(score, 100), reasons


def _comparison(primary, candidate, rule):
    if primary is None or candidate is None:
        return "missing value: manual review"
    if rule == "equal":
        matches = primary == candidate
    elif rule in {"at_least", "at_most"}:
        if not all(isinstance(value, Real) and not isinstance(value, bool) for value in (primary, candidate)):
            return "non-numeric value: manual review"
        matches = candidate >= primary if rule == "at_least" else candidate <= primary
    else:
        return "unknown rule: manual review"
    return "passes rule only" if matches else "fails rule: engineering review"


def _format(sheet, widths=None):
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="19364D")
        cell.font = Font(color="FFFFFF", bold=True)
    for cells in sheet:
        for cell in cells:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for index, column in enumerate(sheet.columns):
        sheet.column_dimensions[column[0].column_letter].width = (widths or {}).get(index + 1, 25)
    for cells in sheet:
        lines = max(sum(max(1, math.ceil(len(line) / max(8, sheet.column_dimensions[cell.column_letter].width - 2)))
                        for line in _text(cell.value).split("\n")) for cell in cells)
        sheet.row_dimensions[cells[0].row].height = max(30, min(390, lines * 15 + 8))
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.print_title_rows = "1:1"


def _workbook(parts, templates, boards, bom_sha256, path):
    wb = Workbook()
    wb.calculation = CalcProperties(calcId=191029, fullCalcOnLoad=True, forceFullCalc=True)
    build = wb.active
    build.title = "Build"
    for values in [
        ["Control", "Value / instruction"],
        ["Board quantity", boards],
        ["Release status", HOLD],
        ["Editing", "Edit Build!B2 to a positive whole number; CM BOM Batch qty recalculates in Excel or LibreOffice. Quantities have no attrition allowance."],
        ["Formula support", "openpyxl does not calculate formulas. Use an Excel-compatible spreadsheet application to recalculate before purchasing."],
        ["Release gate", "Prototype board is untested. Hold purchasing/assembly release until schematic, layout, electrical tests, assembly process and evidence are reviewed."],
        ["Alternates", "All alternates are unqualified candidates. Passing a comparison rule is only a screening result; it never approves substitution."],
        ["Evidence", "Status is recorded evidence, not a certification. Verify source scope, dates, exemptions and current RoHS/REACH declarations for each exact MPN."],
        ["Manufacturer diversity", "Multiple distributors do not create another manufacturer. Candidate availability and supplier inventory are not guaranteed."],
        ["Risk score", "0–100 review priority, not a predicted probability. Lifecycle + manufacturer diversity + missing evidence; capped at 100."],
        ["Family requirements", "Fire/smoke/toxicity and shock/vibration requirements are recorded in Specifications. Not specified is not a pass."],
        ["Fabrication package", "Use the project's real fabrication and placement exports. This workbook does not generate or certify placement coordinates."],
        ["BOM SHA-256", bom_sha256],
    ]:
        _row(build, values)
    control = DataValidation(type="whole", operator="greaterThanOrEqual", formula1=1)
    control.error = "Enter a positive whole board count."
    control.errorTitle = "Invalid build quantity"
    control.showErrorMessage = True
    control.errorStyle = "stop"
    build.add_data_validation(control)
    control.add(build["B2"])
    build["B2"].fill = PatternFill("solid", fgColor="FFF2CC")
    _format(build, {1: 28, 2: 110})

    bom = wb.create_sheet("CM BOM")
    _row(bom, ["IPN", "References", "Family", "Manufacturer", "MPN", "Value", "Footprint",
               "Qty per board", "Batch qty", "Release status", "Datasheet", "Risk score"])
    alternatives = wb.create_sheet("Alternates")
    _row(alternatives, ["IPN", "Primary MPN", "Candidate manufacturer", "Candidate MPN", "Spec field",
                        "Primary value", "Candidate value", "Rule", "Comparison", "Qualification",
                        "Review notes", "Candidate datasheet"])
    evidence = wb.create_sheet("Evidence")
    _row(evidence, ["IPN", "Role", "Manufacturer", "MPN", "Claim", "Status", "Source URL",
                    "Document date", "Checked on", "Scope", "Note", "Reported status (unverified if downgraded)"])
    specs = wb.create_sheet("Specifications")
    _row(specs, ["IPN", "Family", "Role", "Manufacturer", "MPN", "Field", "Value", "Template field"])
    suppliers = wb.create_sheet("Suppliers")
    _row(suppliers, ["IPN", "Manufacturer", "MPN", "Supplier", "SKU", "Source URL", "Review note"])

    for part in parts:
        ipn = part["ipn"]
        _row(bom, [ipn, ", ".join(part["refs"]), part["family"], part["manufacturer"],
                   part["mpn"], part.get("value", ""), part["footprint"], part["quantity"],
                   "", HOLD, part.get("datasheet", ""), part["score"]])
        bom.cell(bom.max_row, 9, f"=H{bom.max_row}*'Build'!$B$2")
        _link(bom.cell(bom.max_row, 11), part.get("datasheet"))
        template = templates.get(part["family"], {})
        rules = template.get("alternate_rules", {})
        fields = template.get("fields", {})
        for role, item in [("primary", part), *(("candidate", c) for c in part.get("alternates", []))]:
            for claim in CLAIMS:
                source = _evidence(item, claim)
                _row(evidence, [ipn, role, item.get("manufacturer", ""), item.get("mpn", ""),
                                claim, source["status"], source["source_url"], source["document_date"],
                                source["checked_on"], source["scope"], source["note"], source["reported_status"]])
                _link(evidence.cell(evidence.max_row, 7), source["source_url"])
            for field, value in sorted(item.get("specs", {}).items()):
                label = fields.get(field, field) if isinstance(fields, dict) else field
                _row(specs, [ipn, part["family"], role, item.get("manufacturer", ""),
                             item.get("mpn", ""), field, value if isinstance(value, (int, float)) else _text(value), _text(label)])
        requirements = template.get("requirements", {})
        for field in sorted(set(requirements) | {"fire_smoke_toxicity", "shock_vibration"}):
            _row(specs, [ipn, part["family"], "family requirement", "", "", field,
                         _text(requirements.get(field, "Not specified; engineering must define before qualification")), "Requirement; not a certification"])
        for alternate in part.get("alternates", []):
            for field in sorted(set(rules) | set(part.get("specs", {})) | set(alternate.get("specs", {}))):
                primary = part.get("specs", {}).get(field)
                candidate = alternate.get("specs", {}).get(field)
                rule = rules.get(field, "manual review")
                _row(alternatives, [ipn, part["mpn"], alternate.get("manufacturer", ""), alternate.get("mpn", ""),
                                    field, primary if isinstance(primary, (int, float)) else _text(primary),
                                    candidate if isinstance(candidate, (int, float)) else _text(candidate), rule,
                                    _comparison(primary, candidate, rule), "NOT QUALIFIED: board and process validation required",
                                    alternate.get("note", ""), alternate.get("datasheet", "")])
                _link(alternatives.cell(alternatives.max_row, 12), alternate.get("datasheet"))
        if not part.get("alternates"):
            _row(alternatives, [ipn, part["mpn"], "", "", "", "", "", "", "No candidate",
                                "NOT QUALIFIED: no alternate", part.get("no_alternate_reason", "Find and qualify a candidate"), ""])
        for supplier in part.get("suppliers", []):
            _row(suppliers, [ipn, part["manufacturer"], part["mpn"], supplier.get("name", ""),
                            supplier.get("sku", ""), supplier.get("url", ""),
                            "Distributor listing only; confirm exact MPN, traceability, stock and lead time."])
            _link(suppliers.cell(suppliers.max_row, 6), supplier.get("url"))

    for sheet in [bom, alternatives, evidence, specs, suppliers]:
        _format(sheet)
    for sheet in [bom, alternatives, evidence, suppliers]:
        sheet.column_dimensions["K"].width = 60
    bom.column_dimensions["J"].width = 50
    specs.column_dimensions["G"].width = 60
    wb.save(path)
    wb.close()


def write_reports(parts, templates, output: Path, boards: int, bom_sha256: str):
    """Write desk-node-cm.xlsx, risk.md and report.json; return JSON report data.

    ``parts`` are enriched catalogue dictionaries. Inputs are never modified.
    ``boards`` must be a positive integer. No runtime timestamps or network data
    enter the report, so risk.md and report.json are reproducible across builds.
    """
    if isinstance(boards, bool) or not isinstance(boards, int) or boards < 1:
        raise ValueError("boards must be a positive integer")
    ranked = []
    for original in parts:
        part = deepcopy(original)
        part["score"], part["reasons"] = _risk(part)
        part["release_status"] = HOLD
        ranked.append(part)
    ranked.sort(key=lambda part: (-part["score"], part["ipn"]))
    report = {
        "schema_version": 1, "boards": boards, "bom_sha256": bom_sha256,
        "release_status": HOLD,
        "risk_method": {
            "meaning": "0–100 review priority, not a predicted probability; capped at 100.",
            "lifecycle": LIFECYCLE_WEIGHTS, "missing_manufacturer_lifecycle_evidence": 10,
            "no_other_manufacturer_alternate": 25, "other_manufacturer_candidates_only": 10,
            "unverified_or_unresolved_rohs": 5, "unverified_or_unresolved_reach": 5,
            "supplier_note": "Distributor count does not establish manufacturer diversity.",
        },
        "parts": ranked,
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    _workbook(ranked, templates, boards, bom_sha256, output / "desk-node-cm.xlsx")
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Component review priority", "", f"Build quantity: {boards} boards. BOM SHA-256: `{bom_sha256}`.", "",
             HOLD + ".", "", report["risk_method"]["meaning"], "",
             "Lifecycle: EOL +50, NRND +35, unverified +20, active +0. Missing manufacturer lifecycle evidence +10. "
             "No other-manufacturer alternate +25; other-manufacturer candidates only +10. Unverified or unresolved RoHS and REACH +5 each.", "",
             "Multiple distributors do not create another manufacturer. All alternates remain unqualified candidates; "
             "a specification comparison never approves substitution. The prototype board is untested.", ""]
    for part in ranked:
        lines += [f"## {part['ipn']}: {part['manufacturer']} {part['mpn']} ({part['score']}/100)", "",
                  f"References: {', '.join(part['refs'])}. Quantity per board: {part['quantity']}.", ""]
        lines += [f"- {reason}" for reason in part["reasons"]]
        if part.get("no_alternate_reason"):
            lines.append(f"- Alternate constraint: {part['no_alternate_reason']}")
        lines.append("")
    (output / "risk.md").write_text("\n".join(lines), encoding="utf-8")
    return report
