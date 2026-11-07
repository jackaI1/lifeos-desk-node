using System;
using System.IO;
using SolidWorks.Interop.sldworks;
public static class PrintBracket {
 static ISldWorks sw;
 static void Sketch(IModelDoc2 m,string plane) {
  m.ClearSelection2(true);
  if(!m.Extension.SelectByID2(plane,"PLANE",0,0,0,false,0,null,0))throw new Exception("Plane not found");
  m.SketchManager.InsertSketch(true);
 }
 static void Extrude(IModelDoc2 m,double offset,double depth,string name,bool reverse=false) {
  IFeature sketch=(IFeature)m.SketchManager.ActiveSketch;
  m.SketchManager.InsertSketch(true);sketch.Select2(false,0);
  IFeature feature=(IFeature)m.FeatureManager.FeatureExtrusion2(true,false,reverse,0,0,depth,0,false,false,false,false,0,0,false,false,false,false,true,true,true,3,offset,false);
  if(feature==null)throw new Exception("Extrusion failed "+name);
  feature.Name=name;
 }
 static void Box(IModelDoc2 m,double x,double y,double z,double a,double b,double c,string name) {
  Sketch(m,"Front Plane");m.SketchManager.CreateCornerRectangle(x,y,0,x+a,y+b,0);Extrude(m,z,c,name);
 }
 public static void Build(string output,double length,double width,double height,double before,double after) {
  if(length<30||width<15||height<20||before<=0||after<1.2||after>=height/3)throw new Exception("Invalid bracket parameters");
  Directory.CreateDirectory(output);
  sw=(ISldWorks)Activator.CreateInstance(Type.GetTypeFromProgID("SldWorks.Application"));sw.Visible=true;
  if(sw.GetDocumentCount()!=0)throw new Exception("Existing documents protected");
  using(var log=new StreamWriter(Path.Combine(output,"build-results.txt"))) {
   log.AutoFlush=true;log.WriteLine("SolidWorks "+sw.RevisionNumber()+" Student Edition; PETG bracket study, no physical tests");
   foreach(bool tuned in new[]{false,true}) {
    double l=length/1000,w=width/1000,h=height/1000,t=(tuned?after:before)/1000;
    IModelDoc2 m=(IModelDoc2)sw.NewDocument("C:\\ProgramData\\SOLIDWORKS\\SOLIDWORKS 2025\\templates\\MBD\\part 0051mm to 0250mm.prtdot",0,0,0);
    if(m==null)throw new Exception("Template failed");
    try {
     Box(m,0,-w,0,l,w,t,"Mounting_foot");
     Box(m,0,-w,t,t,w,h-t,"Upright");
     Box(m,t,-w,h-t,l*.65-t,w,t,"Cable_support_shelf");
     if(tuned) {
      // Top plane local Y is negative model Z; default extrusion points toward positive model Y.
      // A full-width sloping underside turns the elevated shelf into a printable ramp.
      Sketch(m,"Top Plane");
      double reach=l*.65;
      m.SketchManager.CreateLine(t,-t,0,reach,-h+t,0);
      m.SketchManager.CreateLine(reach,-h+t,0,t,-h+t,0);
      m.SketchManager.CreateLine(t,-h+t,0,t,-t,0);
      Extrude(m,0,w,"Continuous_support_gusset",true);
     }
     if(!m.ForceRebuild3(false))throw new Exception("Bracket rebuild failed");
     object[] bodies=(object[])((IPartDoc)m).GetBodies2(0,false);
     foreach(IBody2 debugBody in bodies)log.WriteLine("BODY_BOX "+string.Join(",",(double[])debugBody.GetBodyBox()));
     if(bodies.Length!=1)throw new Exception("Expected single merged body");
     IBody2 body=(IBody2)bodies[0];if(body.Check()!=1)throw new Exception("Body check failed");
     string id=tuned?"BR-002_after":"BR-001_before";
     m.ShowNamedView2("*Isometric",7);m.ViewZoomtofit2();
     for(int i=0;i<5;i++)typeof(IModelDoc2).GetProperty("SummaryInfo").SetValue(m,"",new object[]{i});
     foreach(string ext in new[]{"SLDPRT","stl","step","png"}) {
      int e=0,warn=0;bool saved=m.Extension.SaveAs(Path.Combine(output,id+"."+ext),0,1,null,ref e,ref warn);
      log.WriteLine(id+" "+ext+" saved="+saved+" errors="+e+" warnings="+warn);
      if(!saved||e!=0)throw new Exception("Save failed "+ext);
     }
     double[] bounds=(double[])((IPartDoc)m).GetPartBox(true);
     log.WriteLine(id+" box_m="+string.Join(",",bounds)+" volume_mm3="+((double[])body.GetMassProperties(1))[3]*1e9);
    } finally {sw.CloseDoc(m.GetTitle());}
   }
  }
  sw.ExitApp();
 }
}
