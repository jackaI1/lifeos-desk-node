using System;
using System.IO;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using SolidWorks.Interop.sldworks;
public static class FluidCartridge {
 static Dictionary<string,object> p;static double D(string k){return Convert.ToDouble(p[k]);}
 static void DraftExtrude(IModelDoc2 m,double depth,double angle,string name){
  IFeature s=(IFeature)m.SketchManager.ActiveSketch;m.SketchManager.InsertSketch(true);s.Select2(false,0);
  IFeature f=(IFeature)m.FeatureManager.FeatureExtrusion2(true,false,false,0,0,depth/1000,0,true,false,false,false,angle*Math.PI/180,0,false,false,false,false,true,true,true,0,0,false);
  if(f==null)throw new Exception("Draft extrusion failed "+name);f.Name=name;
 }
 static void DraftCut(IModelDoc2 m,double z,double depth,double angle){
  IFeature s=(IFeature)m.SketchManager.ActiveSketch;m.SketchManager.InsertSketch(true);s.Select2(false,0);
  IFeature f=(IFeature)m.FeatureManager.FeatureCut3(true,false,true,0,0,depth/1000,0,true,false,false,false,angle*Math.PI/180,0,false,false,false,false,false,true,true,true,true,false,3,z/1000,false);
  if(f==null)throw new Exception("Draft cavity failed");f.Name="Drafted_cavity";
 }
 public static void Run(string json,string root){
  p=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(json);
  double l=D("length_mm"),w=D("width_mm"),h=D("height_mm"),wall=D("wall_mm"),floor=D("floor_mm"),lid=D("lid_mm");
  if(wall<=0||l<=2*wall||w<=2*wall||floor>=h)throw new Exception("Invalid cartridge geometry");
  CadCore.Start(root);IModelDoc2 m=CadCore.NewPart();
  CadCore.Sketch(m);CadCore.Rect(m,-l/2,-w/2,l,w);DraftExtrude(m,h,D("draft_deg"),"Drafted_outer_shell");
  CadCore.Sketch(m);CadCore.Rect(m,-l/2+wall,-w/2+wall,l-2*wall,w-2*wall);DraftCut(m,floor,h-floor,D("draft_deg"));
  foreach(double x in new[]{-D("screw_x_mm"),D("screw_x_mm")})foreach(double y in new[]{-D("screw_y_mm"),D("screw_y_mm")})CadCore.Tube(m,x,y,floor,D("boss_outer_mm"),D("screw_pilot_mm"),h-floor,"Screw_boss");
  foreach(double side in new[]{-1.0,1.0}){
   double inner=D("snap_x_mm")+D("snap_thickness_mm")-.2;
   CadCore.Box(m,side>0?inner:-inner-2,-D("snap_width_mm")/2,h-D("snap_length_mm")+1.6,2,D("snap_width_mm"),1.5,"Snap_catch_ledge");
  }
  string body=CadCore.SavePart(m,"FC-001_body","PETG geometry prototype");CadCore.Sw.CloseDoc(m.GetTitle());
  m=CadCore.NewPart();CadCore.Box(m,-l/2,-w/2,0,l,w,lid,"Lid_plate");
  foreach(double x in new[]{-D("port_x_mm"),D("port_x_mm")})CadCore.Hole(m,x,0,D("port_bore_mm"),0,lid,"Port_bore");
  foreach(double x in new[]{-D("screw_x_mm"),D("screw_x_mm")})foreach(double y in new[]{-D("screw_y_mm"),D("screw_y_mm")})CadCore.Hole(m,x,y,D("screw_clearance_mm"),0,lid,"Screw_clearance");
  foreach(double side in new[]{-1.0,1.0}){
   double x=side>0?D("snap_x_mm"):-D("snap_x_mm")-D("snap_thickness_mm");
   CadCore.Box(m,x,-D("snap_width_mm")/2,-D("snap_length_mm"),D("snap_thickness_mm"),D("snap_width_mm"),D("snap_length_mm"),"Snap_beam");
   CadCore.Box(m,side>0?x+D("snap_thickness_mm"):x-.5,-D("snap_width_mm")/2,-D("snap_length_mm"),.5,D("snap_width_mm"),1.5,"Snap_hook");
   CadCore.Sketch(m);CadCore.Rect(m,side>0?x-3:x+D("snap_thickness_mm")+1,-D("release_slot_width_mm")/2,D("release_slot_thickness_mm"),D("release_slot_width_mm"));CadCore.Cut(m,0,lid,"Snap_release_access");
  }
  string lidpath=CadCore.SavePart(m,"FC-002_lid","PETG geometry prototype");CadCore.Sw.CloseDoc(m.GetTitle());
  string[] ids={"FC-003_inlet","FC-004_outlet"};
  foreach(string id in ids){m=CadCore.NewPart();CadCore.Tube(m,0,0,0,D("port_outer_mm"),D("port_bore_mm"),D("port_length_mm"),"Port_tube");CadCore.Tube(m,0,0,0,D("port_flange_mm"),D("port_bore_mm"),2,"Port_flange");string source=CadCore.SavePart(m,id,"PETG reference port; no fitting standard");CadCore.Sw.CloseDoc(m.GetTitle());CadCore.Drawing(source,id,"PETG reference port. Bore diameter "+D("port_bore_mm")+", outside diameter "+D("port_outer_mm")+", length "+D("port_length_mm")+".\nFlange diameter "+D("port_flange_mm")+", thickness 2.\nNo pressure rating, thread, hose retention or fluid compatibility validation.",false);}
  CadCore.Drawing(body,"FC-001_body","SIDE DESIGN EXERCISE, separate from the desk enclosure. PETG.\nEnvelope at base "+l+" x "+w+"; height "+h+"; nominal wall "+wall+"; floor "+floor+".\nMain shell pull direction +Z; draft "+D("draft_deg")+" degrees.\n4 screw pilots diameter "+D("screw_pilot_mm")+" at +/-"+D("screw_x_mm")+", +/-"+D("screw_y_mm")+".\nNo fluid testing, pressure rating or leak-seal design.\nBosses and snap mating faces excluded from the main shell draft screen.",false);
  CadCore.Drawing(lidpath,"FC-002_lid","SIDE DESIGN EXERCISE. PETG. Plate "+l+" x "+w+" x "+lid+".\nPort bores diameter "+D("port_bore_mm")+" at X +/-"+D("port_x_mm")+", Y0.\nScrew clear holes diameter "+D("screw_clearance_mm")+" at +/-"+D("screw_x_mm")+", +/-"+D("screw_y_mm")+".\nSnap beams "+D("snap_thickness_mm")+" x "+D("snap_width_mm")+" x "+D("snap_length_mm")+". Release slots "+D("release_slot_thickness_mm")+" x "+D("release_slot_width_mm")+".\nSnap retention and release forces not verified. No seals specified.",false);
  File.WriteAllText(Path.Combine(root,"bom.csv"),"id,description,quantity,material\nFC-001,cartridge body,1,PETG\nFC-002,cartridge lid with snap beams,1,PETG\nFC-003,inlet reference port,1,PETG\nFC-004,outlet reference port,1,PETG\nM3-SCREW,M3 x 10 thread-forming reference screw,4,steel\n");CadCore.Finish();
 }
}
