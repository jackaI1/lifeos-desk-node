#!/usr/bin/env python3
"""Reuse the desk-node schematic and project writers with a separate design."""
import importlib.util
import json
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import design
sys.path.insert(0,str(HERE.parents[1]/'scripts'))
import gen_schematic as schematic
import gen_project as project
schematic.design=project.design=design
libs=schematic.Libs(next(p for p in schematic.DEFAULT_SYMBOLS if p and Path(p).is_dir()))
sheet=schematic.Sheet(libs)
for c in design.COMPONENTS: sheet.component(c)
for net,at in design.PWR_FLAGS: sheet.pwr_flag(net,at)
for at,text in design.NOTES: sheet.text(at,text)
out=HERE.parent
(out/(design.PROJECT+'.kicad_sch')).write_text(sheet.render().replace('Pinout contract: docs/pinout.md','Probe and MCU pinout: hardware/leak/README.md'))
project.PROJECT['net_settings']['netclass_patterns']=[]
project.PROJECT['meta']['filename']=design.PROJECT+'.kicad_pro'
(out/(design.PROJECT+'.kicad_pro')).write_text(json.dumps(project.PROJECT,indent=2)+'\n')
project.lib_tables(str(out))

(out/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "Leak") (type "KiCad") (uri "${KIPRJMOD}/Leak.pretty") (options "") (descr "KiCad 8 footprint snapshot")))\n')
