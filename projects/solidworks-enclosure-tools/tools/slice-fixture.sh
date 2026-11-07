#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
"${PRUSA_SLICER:-prusa-slicer}" --threads 2 --export-gcode --load specs/fixture-slicer.ini --center 110,110 --output cad/fixture/FX-001_enclosure_nest_B.gcode cad/fixture/FX-001_enclosure_nest_B.STL > reports/fixture/slicer-log.txt 2>&1
