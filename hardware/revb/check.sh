#!/usr/bin/env bash
# Check native Rev B sources without rebuilding or changing routes.
set -euo pipefail
cd "$(dirname "$0")"
cli="${KICAD_CLI:-kicad-cli}"
mkdir -p fab/gerbers
python3 scripts/gen_schematic.py --out fab/regenerated.kicad_sch
diff -q desk-node-b.kicad_sch fab/regenerated.kicad_sch
"$cli" sch erc --severity-all --exit-code-violations -o fab/erc.rpt desk-node-b.kicad_sch
"$cli" pcb drc --schematic-parity --severity-all --exit-code-violations -o fab/drc.rpt desk-node-b.kicad_pcb
"$cli" sch export netlist --format kicadxml -o fab/netlist.xml desk-node-b.kicad_sch
python3 scripts/check_contract.py fab/netlist.xml desk-node-b.kicad_pcb
"$cli" pcb export gerbers -o fab/gerbers/ --layers F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts desk-node-b.kicad_pcb
"$cli" pcb export drill --format excellon --excellon-separate-th -o fab/gerbers/ desk-node-b.kicad_pcb
"$cli" sch export bom --fields 'Reference,Value,Footprint,MPN,${QUANTITY}' --labels 'Reference,Value,Footprint,MPN,Qty' -o fab/bom.csv desk-node-b.kicad_sch
"$cli" pcb export pos --format csv --units mm -o fab/placement.csv desk-node-b.kicad_pcb
