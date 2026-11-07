#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build/gerbers
kicad-cli sch erc --severity-all --exit-code-violations -o build/erc.rpt leak-node.kicad_sch
kicad-cli pcb drc --schematic-parity --severity-all --exit-code-violations -o build/drc.rpt leak-node.kicad_pcb
kicad-cli sch export netlist --format kicadxml -o build/netlist.xml leak-node.kicad_sch
kicad-cli sch export pdf -o build/leak-node.pdf leak-node.kicad_sch
kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts -o build/gerbers/ leak-node.kicad_pcb
kicad-cli pcb export drill --format excellon -o build/gerbers/ leak-node.kicad_pcb
kicad-cli sch export bom --fields 'Reference,Value,Footprint,MPN,${QUANTITY}' --labels 'Reference,Value,Footprint,MPN,Qty' -o build/bom.csv leak-node.kicad_sch
