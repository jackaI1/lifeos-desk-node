#!/usr/bin/env python3
"""Headless PCB placement and batch route import; no desktop is opened."""
from pathlib import Path
import os
import sys
import xml.etree.ElementTree as ET
import pcbnew as p
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import design
sys.path.insert(0,str(HERE.parents[1]/'scripts'))
from gen_schematic import uid
ROOT=HERE.parent
PCB=str(ROOT/'leak-node.kicad_pcb')
PLACEMENT={'J1':(6,6,0),'J2':(39,8,0),'U1':(25,16,0),'R1':(33,10,0),'R2':(18,12,0),'R3':(18,20,0),'R4':(32,21,0),'R5':(12,10,0),'R6':(12,27,0),'D1':(22,27,180),'C1':(25,10,0)}
if len(sys.argv)>1 and sys.argv[1]=='import':
 board=p.LoadBoard(PCB)
 if not p.ImportSpecctraSES(board,str(ROOT/'build/leak.ses')): raise RuntimeError('route import failed')
 p.SaveBoard(PCB,board)
else:
 board=p.BOARD();board.SetCopperLayerCount(2)
 nets={}
 for net in ET.parse(ROOT/'build/netlist.xml').findall('./nets/net'):
  info=p.NETINFO_ITEM(board,net.attrib['name']);board.Add(info)
  for node in net.findall('node'):nets[(node.attrib['ref'],node.attrib['pin'])]=info
 library=Path(os.getenv('KICAD8_FOOTPRINT_DIR','/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints'))
 if not library.is_dir():library=Path('/usr/share/kicad/footprints')
 for c in design.COMPONENTS:
  lib,name=c['fp'].split(':');fp=p.FootprintLoad(str(library/(lib+'.pretty')),name)
  fp.SetFPID(p.LIB_ID(lib,name));fp.SetReference(c['ref']);fp.SetValue(c['value']);fp.SetPath(p.KIID_PATH('/'+uid('sym',c['ref'])));fp.SetSheetname('Root');fp.SetSheetfile('leak-node.kicad_sch')
  board.Add(fp);x,y,rot=PLACEMENT[c['ref']];fp.SetPosition(p.VECTOR2I_MM(100+x,100+y));fp.SetOrientationDegrees(rot)
  fp.Reference().SetVisible(False);fp.Value().SetVisible(False)
  for pad in fp.Pads():pad.SetNet(nets[(c['ref'],pad.GetNumber())])
 for a,b in [((0,0),(45,0)),((45,0),(45,35)),((45,35),(0,35)),((0,35),(0,0))]:
  line=p.PCB_SHAPE(board);line.SetShape(p.SHAPE_T_SEGMENT);line.SetStart(p.VECTOR2I_MM(100+a[0],100+a[1]));line.SetEnd(p.VECTOR2I_MM(100+b[0],100+b[1]));line.SetLayer(p.Edge_Cuts);line.SetWidth(p.FromMM(.1));board.Add(line)
 for text,x,y in [('DESK WATER PROBE',22,3),('3V3  GND  ALERT  SENSE',16,32)]:
  item=p.PCB_TEXT(board);item.SetText(text);item.SetTextSize(p.VECTOR2I_MM(.8,.8));item.SetTextThickness(p.FromMM(.12));item.SetLayer(p.F_SilkS);item.SetPosition(p.VECTOR2I_MM(100+x,100+y));board.Add(item)
 p.SaveBoard(PCB,board)
 if not p.ExportSpecctraDSN(board,str(ROOT/'build/leak.dsn')):raise RuntimeError('DSN export failed')
