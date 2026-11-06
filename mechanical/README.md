# Desk node enclosure study

I wanted to learn how a gasket and a tolerance chain affect a case for my Rev B desk node. This study generates a housing and lid, a gasket groove, assumed PCB supports and an annotated drawing from `spec.json`. The 48 × 54 mm PCB dimensions come from [the Rev B board](../hardware/revb/README.md); the antenna overhang, connector envelopes, mounting-hole positions, sensor airflow and external battery require measurement and design work. Supports are placeholders and no connector openings have been designed. Do not fabricate this enclosure as-is. It is not IP rated or physically tested.

```sh
python3 -m mechanical.enclosure_analysis mechanical/spec.json
DESK_NODE_ROOT="$PWD" xvfb-run -a FreeCAD mechanical/build_enclosure.FCMacro
python3 -m pytest mechanical/tests -q
```

The output folder contains a FreeCAD document, STEP and drawing PDF/SVG. The drawing annotations propose datum and tolerance values for discussion; they are not a validated manufacturing specification. The rectangular groove requires a compatible custom gasket. Screw engagement and bosses are provisional. There is no validated PCB mounting plan or sealing design.

The gasket calculation uses cord diameter minus groove depth minus lid gap. Independent centered normal deviations use each stated ± tolerance as three standard deviations. The Monte Carlo model is unbounded and does not predict actual process yield. Negative theoretical lid gap denotes interference, not physical penetration. The largest half-tolerance is the suggested first contributor to review. Compression and thermal values are assumptions; thermal rise is power times an assumed lumped thermal resistance, not a simulation of airflow or component temperatures. The numerical example is not measured.
