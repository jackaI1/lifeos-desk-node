using System;
using System.IO;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using SolidWorks.Interop.sldworks;
public static class SensorEnclosure {
 static Dictionary<string,object> p;static double D(string key){return Convert.ToDouble(p[key]);}
 public static void Build(string json,string root){
  p=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(json);
  double l=D("length_mm"),w=D("width_mm"),h=D("height_mm"),floor=D("floor_mm"),rim=D("rim_mm"),depth=D("groove_depth_mm"),gw=D("groove_width_mm"),offset=D("groove_offset_mm"),gap=D("lid_gap_mm");
  if(l<=2*rim||w<=2*rim||depth<=0||depth>=h-floor||gw>=rim||offset-gw/2<=0)throw new Exception("Invalid enclosure geometry");
  CadCore.Start(root);
  IModelDoc2 m=CadCore.NewPart();
  CadCore.Box(m,-l/2,-w/2,0,l,w,floor,"Floor");
  CadCore.Ring(m,l,w,rim,floor,h-floor-depth,"Lower_walls");
  // The top rim is split into two concentric lips, leaving the gasket groove between them.
  double outerLip=offset-gw/2,innerLip=rim-offset-gw/2;
  CadCore.Ring(m,l,w,outerLip,h-depth,depth,"Outer_groove_lip");
  double innerL=l-2*(offset+gw/2),innerW=w-2*(offset+gw/2);
  CadCore.Ring(m,innerL,innerW,innerLip,h-depth,depth,"Inner_groove_lip");
  foreach(double x in new[]{-D("screw_x_mm"),D("screw_x_mm")})foreach(double y in new[]{-D("screw_y_mm"),D("screw_y_mm")}){
   // Bosses join the cavity side wall; shoulders establish the nominal lid gap.
   CadCore.Tube(m,x,y,floor,D("boss_diameter_mm"),D("screw_pilot_mm"),h+gap-floor,"Screw_boss");
  }
  foreach(double x in new[]{-D("pcb_x_mm"),D("pcb_x_mm")})foreach(double y in new[]{-D("pcb_y_mm"),D("pcb_y_mm")})CadCore.Tube(m,x,y,floor,D("pcb_post_diameter_mm"),D("pcb_hole_mm"),D("pcb_post_mm"),"PCB_post");
  string housing=CadCore.SavePart(m,"ED-101_sensor_housing_B","PETG, assumed");CadCore.Sw.CloseDoc(m.GetTitle());
  m=CadCore.NewPart();CadCore.Box(m,-l/2,-w/2,0,l,w,D("lid_mm"),"Lid_plate");
  foreach(double x in new[]{-D("screw_x_mm"),D("screw_x_mm")})foreach(double y in new[]{-D("screw_y_mm"),D("screw_y_mm")})CadCore.Hole(m,x,y,D("screw_clearance_mm"),0,D("lid_mm"),"M3_clearance");
  string lid=CadCore.SavePart(m,"ED-102_sensor_lid_B","PETG, assumed");CadCore.Sw.CloseDoc(m.GetTitle());
  m=CadCore.NewPart();double gasketWidth=D("gasket_width_mm");
  double gl=l-2*offset+gasketWidth, gwidth=w-2*offset+gasketWidth;
  CadCore.Box(m,-gl/2,-gwidth/2,0,gl,gwidth,D("gasket_thickness_mm"),"Gasket_blank");
  CadCore.Sketch(m);CadCore.Rect(m,-gl/2+gasketWidth,-gwidth/2+gasketWidth,gl-2*gasketWidth,gwidth-2*gasketWidth);
  CadCore.Cut(m,0,D("gasket_thickness_mm"),"Gasket_inner_opening");
  string gasket=CadCore.SavePart(m,"ED-103_gasket_B","Silicone sheet, uncompressed reference");CadCore.Sw.CloseDoc(m.GetTitle());
  string datums="Datum A: exterior floor plane. Datum B: long exterior side plane. Datum C: short exterior end plane.\nFlatness frame applies to A; position to screw pattern; profile to sealing rim relative A/B/C.\nGD&T design targets per ASME Y14.5-2018; not production-qualified.";
  CadCore.Drawing(housing,"ED-101_sensor_housing_B","PETG. Envelope "+l+" x "+w+" x "+h+". Floor "+floor+"; rim "+rim+".\nGroove width "+gw+", depth "+depth+" +/-"+D("depth_tolerance_mm")+"; centre offset "+offset+".\n4 M3 screw pilots diameter "+D("screw_pilot_mm")+" at +/-"+D("screw_x_mm")+", +/-"+D("screw_y_mm")+" BASIC.\nPCB posts at +/-"+D("pcb_x_mm")+", +/-"+D("pcb_y_mm")+"; post height "+D("pcb_post_mm")+".\nShoulder height "+(h+gap)+" +/-"+D("shoulder_height_tolerance_mm")+"; rim height "+h+" +/-"+D("housing_height_tolerance_mm")+".\n"+datums,true);
  CadCore.Drawing(lid,"ED-102_sensor_lid_B","PETG. Thickness "+D("lid_mm")+". 4 diameter "+D("screw_clearance_mm")+" clear holes.\nPattern +/-"+D("screw_x_mm")+", +/-"+D("screw_y_mm")+" BASIC.\nDatum A: underside. B: long edge. C: short edge.\nFlatness applies underside A; position to holes; profile to outer outline.\nNominal lid gap "+gap+"; gasket compression target 25 percent. No sealing rating.",true);
  CadCore.Drawing(gasket,"ED-103_gasket_B","Silicone flat ring, width "+gasketWidth+", free thickness "+D("gasket_thickness_mm")+" +/-"+D("gasket_tolerance_mm")+".\nCentreline rectangle "+(l-2*offset)+" x "+(w-2*offset)+". Custom sheet-cut reference.\nNominal installed gland height "+(depth+gap)+". No pressure or ingress qualification.",false);
  File.WriteAllText(Path.Combine(root,"bom.csv"),"id,description,quantity,material\nED-101,sensor housing B,1,PETG\nED-102,sensor lid B,1,PETG\nED-103,flat gasket,1,silicone\nM3-SCREW,M3 x 12 thread-forming screw reference,4,steel\nPCB,revision A generic carrier 50 x 25 reference,1,FR4\n");
  CadCore.Finish();
 }
}
