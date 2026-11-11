#!/bin/bash
# Runs the OpenROAD flow (Yosys synthesis, floorplan, placement, clock tree, routing)
# for each clock period and core utilization, then collects the results.
# Runs inside the openroad/orfs container with rtl/ mounted at /work.
set -euo pipefail
PERIODS="${PERIODS:-2.0 1.6 1.2}"
UTILS="${UTILS:-30 50}"
OUT=/work/build/openroad
FLOW=/OpenROAD-flow-scripts/flow
cd "$FLOW"
mkdir -p "$OUT/sdc" "$OUT/logs" "$OUT/reports"
for period in $PERIODS; do
  for util in $UTILS; do
    variant="p${period/./}_u${util}"
    sdc="$OUT/sdc/$variant.sdc"
    python3 /work/flow/make_sdc.py "$period" --out "$sdc"
    echo "== $variant: period ${period} ns, utilization ${util} %"
    make DESIGN_CONFIG=/work/flow/config.mk FLOW_VARIANT="$variant" \
      CORE_UTILIZATION="$util" PLACE_DENSITY_LB_ADDON=0.10 SDC_FILE="$sdc" \
      > "$OUT/logs/$variant.make.log" 2>&1 || { tail -60 "$OUT/logs/$variant.make.log"; exit 1; }
    cp -r "logs/nangate45/sensor_path/$variant" "$OUT/logs/" 2>/dev/null || true
    cp -r "reports/nangate45/sensor_path/$variant" "$OUT/reports/" 2>/dev/null || true
  done
done
python3 /work/flow/collect.py "$OUT" --periods $PERIODS --utils $UTILS --chosen-period 1.2 --chosen-util 30 --docs /work/docs/openroad-sweep.md
