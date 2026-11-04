#!/usr/bin/env bash
# Regenerate the KiCad design from design.py: schematic, placement, autoroute, pours.
# Needs KiCad 8 (Python with pcbnew), Java 21+ and the Freerouting jar.
# Routing is a foreground batch job. No test server or browser is started.
#   FREEROUTING_JAR=/path/to/freerouting-2.1.0.jar hardware/scripts/build.sh
set -euo pipefail
HW="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HW"
KIPY="${KICAD_PYTHON:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
JAVA="${JAVA:-java}"
: "${FREEROUTING_JAR:?set FREEROUTING_JAR to freerouting-2.x.jar}"
mkdir -p build

python3 scripts/gen_schematic.py
"$KIPY" scripts/gen_pcb.py place
python3 scripts/gen_project.py          # after place: NewBoard() writes a default project
"$KIPY" scripts/gen_pcb.py dsn build/desk-node.dsn
"$JAVA" -Xmx1024m -jar "$FREEROUTING_JAR" -de build/desk-node.dsn -do build/desk-node.ses \
    -mp "${ROUTE_PASSES:-100}" -mt 2 -da --gui.enabled=false > build/router.log 2>&1
tail -n 10 build/router.log
"$KIPY" scripts/gen_pcb.py ses build/desk-node.ses
python3 scripts/gen_project.py          # SaveBoard() may rewrite the project; restore rules
echo "Design regenerated. Run hardware/scripts/export_fab.sh to check ERC/DRC and build outputs."
