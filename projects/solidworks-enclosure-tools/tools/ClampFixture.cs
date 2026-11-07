using System;
using System.IO;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;
public static class ClampFixture {
 static Dictionary<string,object> p;static double D(string k){return Convert.ToDouble(p[k]);}
 static Dictionary<string,string> files;
 static void SaveClose(IModelDoc2 m,string id,string material){files[id]=CadCore.SavePart(m,id,material);CadCore.Sw.CloseDoc(m.GetTitle());}
 static IComponent2 Insert(IModelDoc2 ass,string id,double x,double y,double z,bool fixedBase){
  int e=0,w=0;CadCore.Sw.OpenDoc6(files[id],1,1,"",ref e,ref w);CadCore.Sw.ActivateDoc3(ass.GetTitle(),false,0,ref e);
  IAssemblyDoc a=(IAssemblyDoc)ass;IComponent2 c=a.AddComponent5(files[id],0,"",false,"",0,0,0);
  if(c==null)throw new Exception("Insert failed "+id);
  IMathUtility math=(IMathUtility)CadCore.Sw.GetMathUtility();
  c.Transform2=(MathTransform)math.CreateTransform(new double[]{1,0,0,0,1,0,0,0,1,x/1000,y/1000,z/1000,1,0,0,0});
  ass.ClearSelection2(true);c.Select4(false,null,false);if(fixedBase)a.FixComponent();else a.UnfixComponent();
  return c;
 }
 static void MatePlane(IModelDoc2 model,IComponent2 c,IComponent2 basis,string plane,double offset){
  model.ClearSelection2(true);string title=Path.GetFileNameWithoutExtension(model.GetTitle());
  string one=plane+"@"+c.Name2+"@"+title,two=plane+"@"+basis.Name2+"@"+title;
  bool a=model.Extension.SelectByID2(one,"PLANE",0,0,0,false,1,null,0);
  bool b=model.Extension.SelectByID2(two,"PLANE",0,0,0,true,1,null,0);
  if(!a||!b)throw new Exception("Mate selection failed "+one+" / "+two);
  int error=0;int type=Math.Abs(offset)<1e-8?(int)swMateType_e.swMateCOINCIDENT:(int)swMateType_e.swMateDISTANCE;
  object mate=((IAssemblyDoc)model).AddMate5(type,(int)swMateAlign_e.swMateAlignALIGNED,offset>0,Math.Abs(offset)/1000,0,0,0,0,0,0,0,false,false,0,out error);
  CadCore.Log.WriteLine("MATE "+c.Name2+" "+plane+" offset_mm="+offset+" status="+error+" created="+(mate!=null));
  if(mate==null||error!=(int)swAddMateError_e.swAddMateError_NoError)throw new Exception("Mate failed "+error);
 }
 static void Place(IModelDoc2 model,IComponent2 c,IComponent2 basis,double x,double y,double z,List<object> placements){
  MatePlane(model,c,basis,"Front Plane",z);MatePlane(model,c,basis,"Top Plane",y);MatePlane(model,c,basis,"Right Plane",x);
  model.ForceRebuild3(false);
  double[] matrix=(double[])c.Transform2.ArrayData;
  double error=Math.Max(Math.Abs(matrix[9]*1000-x),Math.Max(Math.Abs(matrix[10]*1000-y),Math.Abs(matrix[11]*1000-z)));
  CadCore.Log.WriteLine("PLACEMENT "+c.Name2+" actual_mm="+matrix[9]*1000+","+matrix[10]*1000+","+matrix[11]*1000+" expected_mm="+x+","+y+","+z+" error_mm="+error);
  placements.Add(new {component=c.Name2,expected_mm=new[]{x,y,z},actual_mm=new[]{matrix[9]*1000,matrix[10]*1000,matrix[11]*1000},error_mm=error});
  if(error>.001)throw new Exception("Mate placement differs from target");
 }
 public static void Run(string json,string root,bool drawings){
  p=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(json);files=new Dictionary<string,string>();
  double t=D("base_thickness_mm"),armZ=t+D("coupon_height_mm")+D("nose_depth_mm"),headZ=armZ+D("arm_thickness_mm");
  if(D("base_length_mm")<100||D("base_width_mm")<60||D("locator_hole_mm")<=D("locator_pin_mm")||D("bolt_length_mm")<=headZ+5)throw new Exception("Invalid clamp parameters");
  CadCore.Start(root);IModelDoc2 m=CadCore.NewPart();
  CadCore.Box(m,-D("base_length_mm")/2,-D("base_width_mm")/2,0,D("base_length_mm"),D("base_width_mm"),t,"Base_plate");
  CadCore.Tube(m,D("pivot_x_mm"),0,t,D("pivot_outer_mm"),0,armZ-t,"Pivot_pedestal");
  CadCore.Hole(m,D("pivot_x_mm"),0,D("pivot_hole_mm"),0,armZ,"Pivot_clearance");
  foreach(double x in new[]{-D("locator_x_mm"),D("locator_x_mm")})CadCore.Hole(m,x,D("locator_y_mm"),D("locator_hole_mm"),0,t,"Locator_clearance");
  CadCore.Hole(m,D("side_locator_x_mm"),D("side_locator_y_mm"),D("locator_hole_mm"),0,t,"Side_locator_clearance");
  foreach(double x in new[]{-D("locator_x_mm"),D("locator_x_mm")})CadCore.Hole(m,x,D("locator_y_mm"),D("locator_counterbore_mm"),t-D("locator_shoulder_thickness_mm"),D("locator_shoulder_thickness_mm"),"Locator_shoulder_counterbore");
  CadCore.Hole(m,D("side_locator_x_mm"),D("side_locator_y_mm"),D("locator_counterbore_mm"),t-D("locator_shoulder_thickness_mm"),D("locator_shoulder_thickness_mm"),"Side_shoulder_counterbore");
  foreach(double x in new[]{-D("base_length_mm")/2+10,D("base_length_mm")/2-10})foreach(double y in new[]{-D("base_width_mm")/2+10,D("base_width_mm")/2-10})CadCore.Hole(m,x,y,6.6,0,t,"Bench_mount_M6_clearance");
  SaveClose(m,"CL-001_base","6061 aluminum, design specification");
  m=CadCore.NewPart();CadCore.Tube(m,0,0,0,D("locator_pin_mm"),0,D("locator_pin_length_mm"),"Locator_shaft");CadCore.Tube(m,0,0,t-D("locator_shoulder_thickness_mm"),D("locator_shoulder_mm"),0,D("locator_shoulder_thickness_mm"),"Locator_shoulder");SaveClose(m,"CL-002_locator_pin","Steel, design specification");
  m=CadCore.NewPart();CadCore.Box(m,-D("arm_rear_mm"),-D("arm_width_mm")/2,0,D("arm_length_mm"),D("arm_width_mm"),D("arm_thickness_mm"),"Clamp_arm");
  CadCore.Hole(m,0,0,D("pivot_hole_mm"),0,D("arm_thickness_mm"),"Pivot_bolt_clearance");
  CadCore.Box(m,D("arm_length_mm")-D("arm_rear_mm")-D("nose_length_mm"),-D("nose_width_mm")/2,-D("nose_depth_mm"),D("nose_length_mm"),D("nose_width_mm"),D("nose_depth_mm"),"Contact_nose");SaveClose(m,"CL-003_arm","6061 aluminum, design specification");
  m=CadCore.NewPart();CadCore.Box(m,-D("coupon_length_mm")/2,-D("coupon_width_mm")/2,0,D("coupon_length_mm"),D("coupon_width_mm"),D("coupon_height_mm"),"Reference_coupon");SaveClose(m,"CL-004_coupon","PETG reference coupon");
  m=CadCore.NewPart();CadCore.Tube(m,0,0,0,D("bolt_diameter_mm"),0,D("bolt_length_mm"),"M5_reference_shank");CadCore.Tube(m,0,0,D("bolt_length_mm"),D("bolt_head_mm"),0,D("bolt_head_height_mm"),"Reference_head");SaveClose(m,"CL-005_M5_bolt","Steel, simplified reference hardware");
  m=CadCore.NewPart();CadCore.Tube(m,0,0,0,D("washer_outer_mm"),D("washer_bore_mm"),D("washer_thickness_mm"),"Clearance_washer");SaveClose(m,"CL-006_washer","Steel, simplified reference hardware");
  m=CadCore.NewPart();CadCore.Box(m,-D("nut_AF_mm")/2,-D("nut_AF_mm")/2,0,D("nut_AF_mm"),D("nut_AF_mm"),D("nut_thickness_mm"),"Reference_square_nut");CadCore.Hole(m,0,0,D("nut_bore_mm"),0,D("nut_thickness_mm"),"Simplified_clearance_bore");SaveClose(m,"CL-007_nut","Steel, simplified square reference nut");
  m=(IModelDoc2)CadCore.Sw.NewDocument("C:\\ProgramData\\SOLIDWORKS\\SOLIDWORKS 2025\\templates\\MBD\\assembly 0250mm and smaller.asmdot",0,0,0);
  if(m==null)throw new Exception("Assembly template failed");
  CadCore.Save(m,"CL-000_clamp","SLDASM");IComponent2 basis=Insert(m,"CL-001_base",0,0,0,true);var placements=new List<object>();
  foreach(double x in new[]{-D("locator_x_mm"),D("locator_x_mm")}){IComponent2 c=Insert(m,"CL-002_locator_pin",x,D("locator_y_mm"),0,false);Place(m,c,basis,x,D("locator_y_mm"),0,placements);}
  IComponent2 component=Insert(m,"CL-002_locator_pin",D("side_locator_x_mm"),D("side_locator_y_mm"),0,false);Place(m,component,basis,D("side_locator_x_mm"),D("side_locator_y_mm"),0,placements);
  component=Insert(m,"CL-003_arm",D("pivot_x_mm"),0,armZ,false);Place(m,component,basis,D("pivot_x_mm"),0,armZ,placements);
  component=Insert(m,"CL-004_coupon",0,0,t,false);Place(m,component,basis,0,0,t,placements);
  component=Insert(m,"CL-005_M5_bolt",D("pivot_x_mm"),0,headZ-D("bolt_length_mm"),false);Place(m,component,basis,D("pivot_x_mm"),0,headZ-D("bolt_length_mm"),placements);
  component=Insert(m,"CL-006_washer",D("pivot_x_mm"),0,-D("washer_thickness_mm"),false);Place(m,component,basis,D("pivot_x_mm"),0,-D("washer_thickness_mm"),placements);
  component=Insert(m,"CL-007_nut",D("pivot_x_mm"),0,-D("washer_thickness_mm")-D("nut_thickness_mm"),false);Place(m,component,basis,D("pivot_x_mm"),0,-D("washer_thickness_mm")-D("nut_thickness_mm"),placements);
  bool rebuilt=m.ForceRebuild3(false);if(!rebuilt)throw new Exception("Assembly rebuild failed");
  IAssemblyDoc ass=(IAssemblyDoc)m;IInterferenceDetectionMgr manager=(IInterferenceDetectionMgr)ass.InterferenceDetectionManager;manager.TreatCoincidenceAsInterference=false;
  object[] hits=(object[])manager.GetInterferences();int count=hits==null?0:hits.Length;
  CadCore.Log.WriteLine("ASSEMBLY components="+ass.GetComponentCount(false)+" mates=24 rebuild="+rebuilt+" interferences="+count);
  if(hits!=null)foreach(IInterference hit in hits){CadCore.Log.WriteLine("OVERLAP_MM3 "+hit.Volume*1e9);foreach(IComponent2 c in (object[])hit.Components)CadCore.Log.WriteLine("OVERLAP_PART "+c.Name2);}
  if(count!=0)throw new Exception("Assembly interference detected");
  m.ShowNamedView2("*Isometric",7);m.ViewZoomtofit2();CadCore.Save(m,"CL-000_clamp","SLDASM");CadCore.Save(m,"CL-000_clamp","step");CadCore.Save(m,"assembly","png");
  File.WriteAllText(Path.Combine(root,"native-assembly.json"),new JavaScriptSerializer().Serialize(new {parameters=p,components=ass.GetComponentCount(false),mates=24,rebuild=rebuilt,interferences=count,placements=placements}));
  CadCore.Sw.CloseDoc(m.GetTitle());foreach(string path in files.Values)CadCore.Sw.CloseDoc(Path.GetFileName(path));
  if(drawings){
   string common="Prototype tolerance drawing. Part-specific general +/-0.10 mm overrides sheet default. Material as specified; no load or physical test.\nSimplified clearance fasteners have no threads. Confirm catalog hardware before manufacture.\n";
   CadCore.Drawing(files["CL-001_base"],"CL-001_base",common+"6061 aluminum. Base "+D("base_length_mm")+" x "+D("base_width_mm")+" x "+t+". Pivot X"+D("pivot_x_mm")+", Y0; pedestal top Z"+armZ+".\n3 locator holes diameter "+D("locator_hole_mm")+" +/-"+D("hole_tolerance_mm")+". Back pattern X +/-"+D("locator_x_mm")+", Y"+D("locator_y_mm")+"; side X"+D("side_locator_x_mm")+", Y"+D("side_locator_y_mm")+".\nLocator counterbores diameter "+D("locator_counterbore_mm")+", depth "+D("locator_shoulder_thickness_mm")+" from top.\nDatum A base bottom; B long edge; C short edge. Flatness A0.20; hole position diameter0.40 to A/B/C design target.\n4 M6 clear holes diameter6.6, 10mm from each edge. Pivot bore diameter"+D("pivot_hole_mm")+".",true);
   CadCore.Drawing(files["CL-002_locator_pin"],"CL-002_locator_pin",common+"Steel. Shaft diameter "+D("locator_pin_mm")+" +0/-"+D("pin_lower_tolerance_mm")+"; length "+D("locator_pin_length_mm")+".\nShoulder diameter "+D("locator_shoulder_mm")+", thickness "+D("locator_shoulder_thickness_mm")+", underside Z"+(t-D("locator_shoulder_thickness_mm"))+". Deburr.",false);
   CadCore.Drawing(files["CL-003_arm"],"CL-003_arm",common+"6061 aluminum. Arm "+D("arm_length_mm")+" x "+D("arm_width_mm")+" x "+D("arm_thickness_mm")+". Pivot localX0, Y0, bore diameter"+D("pivot_hole_mm")+".\nRear overhang "+D("arm_rear_mm")+". Nose "+D("nose_length_mm")+" x "+D("nose_width_mm")+" projects "+D("nose_depth_mm")+" below arm.\nDo not infer clamp force from this geometry.",false);
   CadCore.Drawing(files["CL-004_coupon"],"CL-004_coupon",common+"PETG reference coupon "+D("coupon_length_mm")+" x "+D("coupon_width_mm")+" x "+D("coupon_height_mm")+". Generic reference coupon.",false);
   CadCore.Drawing(files["CL-005_M5_bolt"],"CL-005_M5_bolt",common+"Steel M5 x "+D("bolt_length_mm")+" reference envelope. Shank diameter"+D("bolt_diameter_mm")+". Head diameter"+D("bolt_head_mm")+", height"+D("bolt_head_height_mm")+".\nNo thread geometry. Source actual hardware before use.",false);
   CadCore.Drawing(files["CL-006_washer"],"CL-006_washer",common+"Steel washer OD"+D("washer_outer_mm")+", ID"+D("washer_bore_mm")+", thickness"+D("washer_thickness_mm")+".",false);
   CadCore.Drawing(files["CL-007_nut"],"CL-007_nut",common+"Steel square reference nut AF"+D("nut_AF_mm")+", height"+D("nut_thickness_mm")+", simplified bore"+D("nut_bore_mm")+".\nThread engagement not represented. Mount base on spacers for underside access.",false);
  }
  File.WriteAllText(Path.Combine(root,"bom.csv"),"id,description,quantity,material\nCL-001,base with pivot pedestal,1,6061 aluminum\nCL-002,locator pin,3,steel\nCL-003,clamp arm,1,6061 aluminum\nCL-004,reference coupon,1,PETG\nCL-005,M5 x "+D("bolt_length_mm")+" simplified bolt,1,steel\nCL-006,washer,1,steel\nCL-007,simplified M5 square nut,1,steel\n");
  CadCore.Finish();
 }
}
