using System;
using System.IO;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using SolidWorks.Interop.sldworks;
public static class AssemblyFixture {
 public static void Run(string json,string root){
  var p=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(json);
  Func<string,double> D=k=>Convert.ToDouble(p[k]);
  double l=D("outer_length_mm"),w=D("outer_width_mm"),f=D("floor_mm"),depth=D("nest_depth_mm"),px=D("enclosure_length_mm")+2*D("clearance_per_side_mm"),py=D("enclosure_width_mm")+2*D("clearance_per_side_mm");
  if(f<=0||depth<=0||l<=px||w<=py)throw new Exception("Invalid fixture geometry");
  CadCore.Start(root);IModelDoc2 m=CadCore.NewPart();
  CadCore.Box(m,-l/2,-w/2,0,l,w,f,"Fixture_floor");
  CadCore.Sketch(m);CadCore.Rect(m,-l/2,-w/2,l,w);CadCore.Rect(m,-px/2,-py/2,px,py);CadCore.Extrude(m,f,depth,"Enclosure_nest");
  foreach(double x in new[]{-D("hole_x_mm"),D("hole_x_mm")})foreach(double y in new[]{-D("hole_y_mm"),D("hole_y_mm")})CadCore.Hole(m,x,y,D("hole_diameter_mm"),0,f+depth,"Bench_mount_clearance");
  string source=CadCore.SavePart(m,"FX-001_enclosure_nest_B","PETG, assumed");CadCore.Sw.CloseDoc(m.GetTitle());
  CadCore.Drawing(source,"FX-001_enclosure_nest_B","PETG. Floor down for printing.\nEnvelope "+l+" x "+w+" x "+(f+depth)+"; floor "+f+"; pocket depth "+depth+".\nNest "+px+" x "+py+" +/-"+D("pocket_size_tolerance_mm")+".\n4 diameter "+D("hole_diameter_mm")+" through holes at +/-"+D("hole_x_mm")+", +/-"+D("hole_y_mm")+".\nReference enclosure "+D("enclosure_length_mm")+" x "+D("enclosure_width_mm")+".\nCheck shrinkage sweep before printing. No clamping load rating.\nGeneral +/-0.20. Deburr and verify flat seating before assembly.",false);
  File.WriteAllText(Path.Combine(root,"bom.csv"),"id,description,quantity,material\nFX-001,enclosure assembly nest,1,PETG\n");CadCore.Finish();
 }
}
