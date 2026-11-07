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
# Explicit field positions keep values off symbol bodies in exported sheets.
original_instance=sheet.instance
def readable_instance(ref,lib_id,value,at,*args,**kwargs):
 if not ref.startswith('#'):
  x,y=at
  if ref.startswith(('R','C')):
   kwargs.update(ref_at=(x+5.08,y-1.27),val_at=(x+5.08,y+1.27))
  elif ref.startswith('U'):
   kwargs.update(ref_at=(x+2.54,y-10.16),val_at=(x+20.32,y+10.16))
  elif ref.startswith('J'):
   kwargs.update(ref_at=(x,y-7.62),val_at=(x,y+10.16))
  else:
   kwargs.update(ref_at=(x,y-5.08),val_at=(x,y+5.08))
 return original_instance(ref,lib_id,value,at,*args,**kwargs)
sheet.instance=readable_instance
for c in design.COMPONENTS:
 original_power=sheet.power
 # Closely spaced connector pins need horizontal net labels, not rotated
 # power-symbol text extending across adjacent pin labels.
 if c['ref'].startswith('J') or c['lib'].startswith('Regulator_Linear:'):sheet.power=sheet.label
 sheet.component(c)
 sheet.power=original_power
for net,at in design.PWR_FLAGS: sheet.pwr_flag(net,at)
for at,text in design.NOTES: sheet.text(at,text)
out=HERE.parent
(out/(design.PROJECT+'.kicad_sch')).write_text(sheet.render().replace('Pinout contract: docs/pinout.md','Probe and MCU pinout: hardware/leak/README.md'))
project.PROJECT['net_settings']['netclass_patterns']=[]
project.PROJECT['meta']['filename']=design.PROJECT+'.kicad_pro'
(out/(design.PROJECT+'.kicad_pro')).write_text(json.dumps(project.PROJECT,indent=2)+'\n')
project.lib_tables(str(out))

(out/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "Leak") (type "KiCad") (uri "${KIPRJMOD}/Leak.pretty") (options "") (descr "KiCad 8 footprint snapshot")))\n')
