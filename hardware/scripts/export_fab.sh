#!/usr/bin/env bash
# ERC, DRC (with schematic parity) and JLCPCB fabrication outputs, using kicad-cli only.
# Used locally and in .github/workflows/hardware.yml (kicad/kicad:8.0 container).
set -euo pipefail
HW="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HW"
KICAD_CLI="${KICAD_CLI:-kicad-cli}"
NAME=desk-node
OUT=fab
rm -rf "$OUT" && mkdir -p "$OUT/gerbers"

echo "== ERC"
"$KICAD_CLI" sch erc --severity-all --exit-code-violations -o "$OUT/erc.rpt" "$NAME.kicad_sch" \
  || { cat "$OUT/erc.rpt"; exit 1; }
echo "== DRC (+ schematic parity)"
"$KICAD_CLI" pcb drc --schematic-parity --severity-all --exit-code-violations \
  -o "$OUT/drc.rpt" "$NAME.kicad_pcb" || { cat "$OUT/drc.rpt"; exit 1; }

echo "== Physical pin contract"
"$KICAD_CLI" sch export netlist --format kicadxml -o "$OUT/netlist.xml" "$NAME.kicad_sch"
python3 scripts/check_contract.py "$OUT/netlist.xml"

echo "== Gerbers + drill"
"$KICAD_CLI" pcb export gerbers -o "$OUT/gerbers/" \
  --layers F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts \
  --subtract-soldermask --use-drill-file-origin "$NAME.kicad_pcb"
"$KICAD_CLI" pcb export drill -o "$OUT/gerbers/" --format excellon --drill-origin absolute \
  --excellon-units mm --excellon-separate-th --generate-map --map-format gerberx2 "$NAME.kicad_pcb"

echo "== Pick-and-place, BOM, schematic PDF"
"$KICAD_CLI" pcb export pos -o "$OUT/$NAME-pos.csv" --format csv --units mm --side both \
  --exclude-dnp "$NAME.kicad_pcb"
"$KICAD_CLI" sch export bom -o "$OUT/$NAME-bom-kicad.csv" \
  --fields 'Reference,Value,Footprint,LCSC,MPN,${QUANTITY}' \
  --labels 'Designator,Value,Footprint,LCSC,MPN,Qty' \
  --group-by 'Value,Footprint,LCSC' --ref-range-delimiter '' --exclude-dnp "$NAME.kicad_sch"
"$KICAD_CLI" sch export pdf -o "$OUT/$NAME-schematic.pdf" "$NAME.kicad_sch"
python3 scripts/jlc_outputs.py "$OUT"

echo "== Summary"
grep -E 'Found [0-9]+' "$OUT/erc.rpt" "$OUT/drc.rpt" || true
ls -1 "$OUT" "$OUT/gerbers" | sed 's/^/  /'
