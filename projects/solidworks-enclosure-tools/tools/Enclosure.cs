using System;
using System.IO;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;

// Run inside Windows PowerShell 5.1, STA. All API geometry is in metres.
public static class Enclosure {
 public static double BeamLength=18, PostHeight=6;
 static ISldWorks sw; static string root; static StreamWriter log;
 static string templates="C:/ProgramData/SOLIDWORKS/SOLIDWORKS 2025/templates/MBD/";
 static IModelDoc2 New(string type) {
  string template=templates+(type=="part"?"part 0051mm to 0250mm.prtdot":"assembly 0250mm and smaller.asmdot");
  IModelDoc2 m=(IModelDoc2)sw.NewDocument(template.Replace('/','\\'),0,0,0);
  if(m==null) throw new Exception("NewDocument failed: "+type);
  return m;
 }
 static void Sketch(IModelDoc2 m) {
  m.ClearSelection2(true);
  if(!m.Extension.SelectByID2("Front Plane","PLANE",0,0,0,false,0,null,0)) throw new Exception("Front plane missing");
  m.SketchManager.InsertSketch(true);
 }
 static void Rect(IModelDoc2 m,double x,double y,double w,double h) {m.SketchManager.CreateCornerRectangle(x,y,0,x+w,y+h,0);}
 static void Extrude(IModelDoc2 m,double z,double d,string name) {
  IFeature sk=(IFeature)m.SketchManager.ActiveSketch;
  m.SketchManager.InsertSketch(true);sk.Select2(false,0);
  IFeature f=(IFeature)m.FeatureManager.FeatureExtrusion2(true,false,false,0,0,d,0,false,false,false,false,0,0,false,false,false,false,true,true,true,3,z,false);
  if(f==null) throw new Exception("Extrude failed: "+name); f.Name=name;
 }
 static void Box(IModelDoc2 m,double x,double y,double z,double w,double h,double d,string n) {Sketch(m);Rect(m,x,y,w,h);Extrude(m,z,d,n);}
 static string Save(IModelDoc2 m,string id) {
  for(int field=0;field<5;field++)typeof(IModelDoc2).GetProperty("SummaryInfo").SetValue(m,"",new object[]{field});
  m.ForceRebuild3(false); m.ShowNamedView2("*Isometric",7);m.ViewZoomtofit2();
  string p=Path.Combine(root,id+".SLDPRT");
  int e=m.SaveAs3(p,0,1);if(e!=0)throw new Exception("Save error "+e+": "+id);
  IPartDoc part=(IPartDoc)m; object[] bodies=(object[])part.GetBodies2(0,false);
  double volume=0;foreach(IBody2 b in bodies) {double[] mp=(double[])b.GetMassProperties(1);volume+=mp[3]; log.WriteLine("BODY_CHECK "+id+" code="+b.Check());}
  log.WriteLine("PART "+id+" bodies="+bodies.Length+" volume_mm3="+(volume*1e9).ToString("F3",System.Globalization.CultureInfo.InvariantCulture));
  int er=0,wr=0;bool ok=m.Extension.SaveAs(Path.Combine(root,id+".stl"),0,1,null,ref er,ref wr);
  log.WriteLine("STL "+id+" saved="+ok+" errors="+er+" warnings="+wr);
  m.SaveAs3(Path.Combine(root,id+".png"),0,1);
  return p;
 }
 static IComponent2 Add(IModelDoc2 model,string path,double x,double y,double z) {
  int err=0;sw.ActivateDoc3(model.GetTitle(),false,0,ref err);
  IComponent2 c=((IAssemblyDoc)model).AddComponent5(path,0,"",false,"",0,0,0);
  if(c==null) throw new Exception("Component insertion failed: "+path);
  IMathUtility math=(IMathUtility)sw.GetMathUtility();
  double[] a={1,0,0,0,1,0,0,0,1,x,y,z,1,0,0,0};c.Transform2=(MathTransform)math.CreateTransform(a);
  model.ClearSelection2(true);c.Select4(false,null,false);((IAssemblyDoc)model).FixComponent();
  return c;
 }
 public static void Build(string output) {
  root=output;Directory.CreateDirectory(root);log=new StreamWriter(Path.Combine(root,"build-results.txt"));log.AutoFlush=true;
  sw=(ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
  log.WriteLine("SOLIDWORKS "+sw.RevisionNumber());log.WriteLine("START_DOCUMENT_COUNT "+sw.GetDocumentCount());
  // Never close or mutate pre-existing documents.
  if(sw.GetDocumentCount()!=0) throw new Exception("Close project documents before regeneration; existing documents are protected.");
  var m=New("part");
  Box(m,-.04,-.03,0,.08,.06,.0024,"Floor_2p4");
  Sketch(m);Rect(m,-.04,-.03,.08,.06);Rect(m,-.0376,-.0276,.0752,.0552);Extrude(m,.0024,.0336,"Walls_2p4");
  // Interior latch ledges are below the upper edge. Beams flex toward the cavity.
  Box(m,-.0376,-.006,.021,.0008,.012,.002,"Catch_left");
  Box(m,.0368,-.006,.021,.0008,.012,.002,"Catch_right");
  string casep=Save(m,"ED-001_case_A");
  m=New("part");Sketch(m);Rect(m,-.04,-.03,.08,.06);Rect(m,-.020,-.012,.04,.024);Extrude(m,0,.0024,"Lid_frame");
  // Downward cantilevers, root attached to the lid. Physical hook has a square entry.
  Box(m,-.0365,-.004,-BeamLength/1000,.0012,.008,BeamLength/1000,"Snap_left");
  Box(m,.0353,-.004,-BeamLength/1000,.0012,.008,BeamLength/1000,"Snap_right");
  Box(m,-.0373,-.004,-.017,.0008,.008,.0015,"Hook_left");
  Box(m,.0365,-.004,-.017,.0008,.008,.0015,"Hook_right");
  string lid=Save(m,"ED-002_lid_A");
  m=New("part");Sketch(m);m.SketchManager.CreateCircleByRadius(0,0,0,.003);m.SketchManager.CreateCircleByRadius(0,0,0,.0014);Extrude(m,0,PostHeight/1000,"M2p5_clearance_post");string post=Save(m,"LIB-001_standoff_A");
  m=New("part");Box(m,-.0197,-.0117,0,.0394,.0234,.0024,"Hatch_plate");string hatch=Save(m,"ED-003_hatch_A");
  m=New("part");Sketch(m);Rect(m,-.014,-.009,.028,.018);Rect(m,-.0118,-.0064,.0236,.0128);Extrude(m,0,.004,"Servo_mount_cradle");string mount=Save(m,"LIB-002_servo_mount_A");
  m=New("part");Box(m,-.0115,-.0061,0,.023,.0122,.029,"SG90_reference_envelope");string servo=Save(m,"REF-001_SG90_A");
  m=New("part");Box(m,-.025,-.0125,0,.05,.025,.0016,"Generic_ESP32_carrier_reference");string board=Save(m,"REF-002_carrier_A");
  m=New("assembly");Add(m,casep,0,0,0);Add(m,lid,0,0,.036);Add(m,hatch,0,0,.036);
  foreach(double x in new[]{-.021,.021})foreach(double y in new[]{-.0085,.0085})Add(m,post,x,y,.0024);
  Add(m,board,0,0,.0024+PostHeight/1000);Add(m,mount,0,.0205,.0024);Add(m,servo,0,.0205,.0024);
  m.ForceRebuild3(false);m.ShowNamedView2("*Isometric",7);m.ViewZoomtofit2();
  string ass=Path.Combine(root,"ED-000_desk_device_A.SLDASM");int result=m.SaveAs3(ass,0,1);if(result!=0)throw new Exception("Assembly save "+result);
  m.SaveAs3(Path.Combine(root,"assembly.png"),0,1);
  log.WriteLine("ASSEMBLY components="+((IAssemblyDoc)m).GetComponentCount(false));
  try {object sim=sw.GetAddInObject("SldWorks.Simulation");log.WriteLine("SIMULATION_ADDIN_PRESENT "+(sim!=null)+"; run inspect.ps1 to create and solve a study.");}catch(Exception e){log.WriteLine("SIMULATION_ADDIN_QUERY_FAILED "+e.GetType().Name);}
  Drawing(casep,"ED-001_case_A","80 x 60 x 36; wall and floor 2.4 mm.\nCavity 75.2 x 55.2. Datum A is exterior floor.\nFlatness 0.30 on datum face A.\nPerpendicularity 0.40 to A on outside walls.\nDimensions in mm. General tolerance +/-0.20.\nGD&T per ASME Y14.5-2018. Inspect after printing.");
  Drawing(lid,"ED-002_lid_A","80 x 60 x 2.4 frame; aperture 40 x 24.\nSnap beam L18 x b8 x t1.2; hook projection 0.8.\nDatum A is outer top face. Flatness 0.30 on A.\nProfile of aperture 0.40 relative to A.\nHatch 39.4 x 23.4 gives 0.30 clearance per side.\nDimensions in mm. General tolerance +/-0.20.\nPrint on top face; beams point up. Round hook by hand.");
  log.Dispose();
  Upgrade(root);
 }
 public static void Upgrade(string output) {
  root=output;sw=(ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
  log=new StreamWriter(Path.Combine(root,"moving-feature.txt"));log.AutoFlush=true;
  int e=0,w=0;
  IModelDoc2 lid=(IModelDoc2)sw.OpenDoc6(Path.Combine(root,"ED-002_lid_A.SLDPRT"),1,1,"",ref e,ref w);
  sw.ActivateDoc3(lid.GetTitle(),false,0,ref e);
  // A through cut provides radial clearance around the reference output shaft.
  Sketch(lid);lid.SketchManager.CreateCircleByRadius(0,.0205,0,.0022);
  IFeature sk=(IFeature)lid.SketchManager.ActiveSketch;lid.SketchManager.InsertSketch(true);sk.Select2(false,0);
  IFeature cut=(IFeature)lid.FeatureManager.FeatureCut3(true,false,true,1,1,.01,.01,false,false,false,false,0,0,false,false,false,false,false,true,true,true,true,false,0,0,false);
  if(cut==null)throw new Exception("Shaft clearance cut failed");cut.Name="Shaft_clearance_D4p4";Save(lid,"ED-002_lid_A");
  IModelDoc2 hatch=(IModelDoc2)sw.OpenDoc6(Path.Combine(root,"ED-003_hatch_A.SLDPRT"),1,1,"",ref e,ref w);
  sw.ActivateDoc3(hatch.GetTitle(),false,0,ref e);Sketch(hatch);Rect(hatch,-.0035,.011,.007,.014);
  hatch.SketchManager.CreateCircleByRadius(0,.0205,0,.00155);Extrude(hatch,0,.0024,"Drive_arm_D3p1");Save(hatch,"ED-003_hatch_A");
  IModelDoc2 servo=(IModelDoc2)sw.OpenDoc6(Path.Combine(root,"REF-001_SG90_A.SLDPRT"),1,1,"",ref e,ref w);
  sw.ActivateDoc3(servo.GetTitle(),false,0,ref e);Sketch(servo);servo.SketchManager.CreateCircleByRadius(0,0,0,.0014);Extrude(servo,.029,.0085,"Output_axis_REFERENCE_NOT_VENDOR_GEOMETRY");Save(servo,"REF-001_SG90_A");
  IModelDoc2 ass=(IModelDoc2)sw.OpenDoc6(Path.Combine(root,"ED-000_desk_device_A.SLDASM"),2,1,"",ref e,ref w);
  sw.ActivateDoc3(ass.GetTitle(),false,0,ref e);IComponent2 moving=null;
  foreach(IComponent2 c in (object[])((IAssemblyDoc)ass).GetComponents(false))if(c.GetPathName().EndsWith("ED-003_hatch_A.SLDPRT",StringComparison.OrdinalIgnoreCase))moving=c;
  if(moving==null)throw new Exception("Hatch component missing");
  ass.ClearSelection2(true);moving.Select4(false,null,false);((IAssemblyDoc)ass).UnfixComponent();
  IMathUtility math=(IMathUtility)sw.GetMathUtility();
  double[] closed={1,0,0,0,1,0,0,0,1,0,0,.0387,1,0,0,0};moving.SetTransformAndSolve2((MathTransform)math.CreateTransform(closed));
  ass.ForceRebuild3(false);ass.ShowNamedView2("*Isometric",7);ass.ViewZoomtofit2();ass.SaveAs3(Path.Combine(root,"assembly.png"),0,1);
  ass.AddConfiguration3("Hatch_open_90","Rotary hatch about reference output axis","",0);
  double[] open={0,1,0,-1,0,0,0,0,1,.0205,.0205,.0387,1,0,0,0};moving.SetTransformAndSolve2((MathTransform)math.CreateTransform(open));
  ass.ForceRebuild3(false);ass.ViewZoomtofit2();ass.SaveAs3(Path.Combine(root,"assembly-open.png"),0,1);
  ass.ShowConfiguration2("Default");ass.Save3(1,ref e,ref w);
  log.WriteLine("Rotary hatch configurations saved. Closed standoff above lid 0.30 mm.");
  log.WriteLine("SG90 body is a vendor-sized envelope. Output extension is a design reference, not a vendor spline or horn model.");
  log.Dispose();
  FinishBoard(root);
  FinishMount(root);
  RebuildAssembly(root);
 }
 public static void FinishBoard(string output) {
  root=output;sw=(ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
  log=new StreamWriter(Path.Combine(root,"carrier-update.txt"));log.AutoFlush=true;int e=0,w=0;
  IModelDoc2 board=(IModelDoc2)sw.OpenDoc6(Path.Combine(root,"REF-002_carrier_A.SLDPRT"),1,1,"",ref e,ref w);
  sw.ActivateDoc3(board.GetTitle(),false,0,ref e);Sketch(board);
  foreach(double x in new[]{-.021,.021})foreach(double y in new[]{-.0085,.0085})board.SketchManager.CreateCircleByRadius(x,y,0,.0014);
  IFeature sk=(IFeature)board.SketchManager.ActiveSketch;board.SketchManager.InsertSketch(true);sk.Select2(false,0);
  IFeature cut=(IFeature)board.FeatureManager.FeatureCut3(true,false,true,1,1,.01,.01,false,false,false,false,0,0,false,false,false,false,false,true,true,true,true,false,0,0,false);
  if(cut==null)throw new Exception("Carrier hole cut failed");cut.Name="Four_M2p5_clearance_holes";Save(board,"REF-002_carrier_A");log.Dispose();
 }
 public static void FinishMount(string output) {
  root=output;sw=(ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
  log=new StreamWriter(Path.Combine(root,"mount-update.txt"));log.AutoFlush=true;int e=0,w=0;
  IModelDoc2 m=(IModelDoc2)sw.OpenDoc6(Path.Combine(root,"LIB-002_servo_mount_A.SLDPRT"),1,1,"",ref e,ref w);
  sw.ActivateDoc3(m.GetTitle(),false,0,ref e);Sketch(m);Rect(m,-.02,.0064,.04,.01);
  IFeature sk=(IFeature)m.SketchManager.ActiveSketch;m.SketchManager.InsertSketch(true);sk.Select2(false,0);
  IFeature cut=(IFeature)m.FeatureManager.FeatureCut3(true,false,true,1,1,.01,.01,false,false,false,false,0,0,false,false,false,false,false,true,true,true,true,false,0,0,false);
  if(cut==null)throw new Exception("Mount relief failed");cut.Name="Rear_wall_clearance_U_bracket";Save(m,"LIB-002_servo_mount_A");log.Dispose();
 }
 public static void RebuildAssembly(string output) {
  root=output;sw=(ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
  sw.CloseDoc("ED-000_desk_device_A.SLDASM");sw.CloseDoc("ED-000_desk_device_A");
  IModelDoc2 m=New("assembly");
  Add(m,Path.Combine(root,"ED-001_case_A.SLDPRT"),0,0,0);
  Add(m,Path.Combine(root,"ED-002_lid_A.SLDPRT"),0,0,.036);
  Add(m,Path.Combine(root,"ED-003_hatch_A.SLDPRT"),0,0,.0387);
  foreach(double x in new[]{-.021,.021})foreach(double y in new[]{-.0085,.0085})Add(m,Path.Combine(root,"LIB-001_standoff_A.SLDPRT"),x,y,.0024);
  Add(m,Path.Combine(root,"REF-002_carrier_A.SLDPRT"),0,0,.0024+PostHeight/1000);
  Add(m,Path.Combine(root,"LIB-002_servo_mount_A.SLDPRT"),0,.0205,.0024);
  Add(m,Path.Combine(root,"REF-001_SG90_A.SLDPRT"),0,.0205,.0024);
  if(m.SaveAs3(Path.Combine(root,"ED-000_desk_device_A.SLDASM"),0,1)!=0)throw new Exception("Assembly save failed");
  HatchStates.Setup(m,sw);
 }
 static void Drawing(string source,string id,string text) {
  string template="C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/data/templates/iso.drwdot";
  IModelDoc2 m=(IModelDoc2)sw.NewDocument(template.Replace('/','\\'),12,.420,.297);if(m==null)throw new Exception("Drawing template failed");
  IDrawingDoc d=(IDrawingDoc)m;
  d.SetupSheet5("Sheet1",12,12,1,1,false,"",.420,.297,"Default",true);
  if(d.CreateDrawViewFromModelView3(source,"*Front",.09,.18,0)==null)throw new Exception("Front view failed");
  d.CreateDrawViewFromModelView3(source,"*Top",.09,.09,0);
  d.CreateDrawViewFromModelView3(source,"*Isometric",.25,.18,0);
  m.ClearSelection2(true);INote n=(INote)m.InsertNote(id+" | REV A | PETG | PROTOTYPE\n"+text);
  ((IAnnotation)n.GetAnnotation()).SetPosition2(.21,.090,0);
  m.ViewZoomtofit2();int e=m.SaveAs3(Path.Combine(root,id+".SLDDRW"),0,1);log.WriteLine("DRAWING "+id+" save="+e);
  e=m.SaveAs3(Path.Combine(root,id+".pdf"),0,1);log.WriteLine("PDF "+id+" save="+e);
 }
}
