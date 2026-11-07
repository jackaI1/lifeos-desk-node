using System;
using System.IO;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;
public static class CadCore {
 public static ISldWorks Sw; public static string Root; public static StreamWriter Log;
 public static void Start(string root) {
  if(File.Exists(Path.Combine(root,"manifest.csv")))throw new Exception("Released folder protected");
  Root=root;Directory.CreateDirectory(root);
  Sw=(ISldWorks)Activator.CreateInstance(Type.GetTypeFromProgID("SldWorks.Application"));Sw.Visible=true;
  if(Sw.GetDocumentCount()!=0)throw new Exception("Existing documents protected; close before generation");
  Log=new StreamWriter(Path.Combine(root,"build-results.txt"));Log.AutoFlush=true;
  Log.WriteLine("SolidWorks "+Sw.RevisionNumber()+" Student Edition educational designation. No physical testing.");
 }
 public static void Finish(){Log.Dispose();Sw.ExitApp();}
 public static IModelDoc2 NewPart(){
  IModelDoc2 m=(IModelDoc2)Sw.NewDocument("C:\\ProgramData\\SOLIDWORKS\\SOLIDWORKS 2025\\templates\\MBD\\part 0051mm to 0250mm.prtdot",0,0,0);
  if(m==null)throw new Exception("Part template failed");m.SetUserPreferenceIntegerValue((int)swUserPreferenceIntegerValue_e.swUnitsLinear,(int)swLengthUnit_e.swMM);return m;
 }
 public static void Sketch(IModelDoc2 m){
  m.ClearSelection2(true);if(!m.Extension.SelectByID2("Front Plane","PLANE",0,0,0,false,0,null,0))throw new Exception("Plane missing");m.SketchManager.InsertSketch(true);
 }
 public static void Rect(IModelDoc2 m,double x,double y,double w,double h){m.SketchManager.CreateCornerRectangle(x/1000,y/1000,0,(x+w)/1000,(y+h)/1000,0);}
 public static void Extrude(IModelDoc2 m,double z,double depth,string name){
  IFeature sketch=(IFeature)m.SketchManager.ActiveSketch;m.SketchManager.InsertSketch(true);sketch.Select2(false,0);
  IFeature f=(IFeature)m.FeatureManager.FeatureExtrusion2(true,false,false,0,0,depth/1000,0,false,false,false,false,0,0,false,false,false,false,true,true,true,3,z/1000,false);
  if(f==null)throw new Exception("Extrude failed "+name);f.Name=name;
 }
 public static void Box(IModelDoc2 m,double x,double y,double z,double w,double h,double d,string name){Sketch(m);Rect(m,x,y,w,h);Extrude(m,z,d,name);}
 public static void Ring(IModelDoc2 m,double l,double w,double wall,double z,double d,string name){Sketch(m);Rect(m,-l/2,-w/2,l,w);Rect(m,-l/2+wall,-w/2+wall,l-2*wall,w-2*wall);Extrude(m,z,d,name);}
 public static void Tube(IModelDoc2 m,double x,double y,double z,double outer,double inner,double depth,string name){
  Sketch(m);m.SketchManager.CreateCircleByRadius(x/1000,y/1000,0,outer/2000);Extrude(m,z,depth,name);if(inner>0)Hole(m,x,y,inner,z,depth,name+"_bore");
 }
 public static void Cut(IModelDoc2 m,double z,double depth,string name){
  IFeature sk=(IFeature)m.SketchManager.ActiveSketch;m.SketchManager.InsertSketch(true);sk.Select2(false,0);
  IFeature f=(IFeature)m.FeatureManager.FeatureCut3(true,false,true,0,0,depth/1000,0,false,false,false,false,0,0,false,false,false,false,false,true,true,true,true,false,3,z/1000,false);
  if(f==null)throw new Exception("Cut failed "+name);f.Name=name;
 }
 public static void Hole(IModelDoc2 m,double x,double y,double diameter,double z,double depth,string name){Sketch(m);m.SketchManager.CreateCircleByRadius(x/1000,y/1000,0,diameter/2000);Cut(m,z,depth,name);}
 public static string SavePart(IModelDoc2 m,string id,string material){
  if(!m.ForceRebuild3(false))throw new Exception("Rebuild failed "+id);
  object[] bodies=(object[])((IPartDoc)m).GetBodies2(0,false);if(bodies==null||bodies.Length!=1)throw new Exception("Need single body "+id);
  IBody2 body=(IBody2)bodies[0];if(body.Check()!=1)throw new Exception("Body invalid "+id);
  for(int i=0;i<5;i++)typeof(IModelDoc2).GetProperty("SummaryInfo").SetValue(m,"",new object[]{i});
  m.Extension.CustomPropertyManager[""].Add3("Material",30,material,1);
  m.ShowNamedView2("*Isometric",7);m.ViewZoomtofit2();
  foreach(string ext in new[]{"SLDPRT","step","STL","png"})Save(m,id,ext);
  Log.WriteLine("PART "+id+" bodies=1 volume_mm3="+((double[])body.GetMassProperties(1))[3]*1e9+" bounds_m="+string.Join(",",(double[])((IPartDoc)m).GetPartBox(true)));
  return Path.Combine(Root,id+".SLDPRT");
 }
 public static void Save(IModelDoc2 m,string id,string ext){int e=0,w=0;bool ok=m.Extension.SaveAs(Path.Combine(Root,id+"."+ext),0,1,null,ref e,ref w);Log.WriteLine("SAVE "+id+"."+ext+" ok="+ok+" errors="+e+" warnings="+w);if(!ok||e!=0)throw new Exception("Save failed "+id+"."+ext);}
 public static void Drawing(string source,string id,string notes,bool gdt){
  int e=0,w=0;IModelDoc2 part=(IModelDoc2)Sw.OpenDoc6(source,1,1,"",ref e,ref w);
  IModelDoc2 m=(IModelDoc2)Sw.NewDocument("C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\data\\templates\\iso.drwdot",12,.420,.297);
  if(m==null)throw new Exception("Drawing template failed");m.SetUserPreferenceIntegerValue((int)swUserPreferenceIntegerValue_e.swUnitsLinear,(int)swLengthUnit_e.swMM);IDrawingDoc d=(IDrawingDoc)m;d.SetupSheet5("Sheet1",12,12,1,1,false,"",.420,.297,"Default",true);
  IView front=(IView)d.CreateDrawViewFromModelView3(source,"*Front",.095,.200,0);
  IView top=(IView)d.CreateDrawViewFromModelView3(source,"*Top",.095,.105,0);
  d.CreateDrawViewFromModelView3(source,"*Isometric",.285,.205,0);
  if(front==null||top==null)throw new Exception("Views missing");
  int dims=DimensionEdges(m,d,front,part)+DimensionEdges(m,d,top,part);
  Log.WriteLine("DRAWING "+id+" native_dimensions="+dims);
  if(dims<2)throw new Exception("Insufficient native drawing dimensions "+id);
  m.ClearSelection2(true);INote n=(INote)m.InsertNote(id+" | PROTOTYPE | Student Edition\nDimensions mm. General tolerance +/-0.20 unless specified.\n"+notes+"\nNo physical tests. Inspect printed parts and print fit coupons.");
  ((IAnnotation)n.GetAnnotation()).SetPosition2(.205,.12,0);
  if(gdt){
   AddDatum(m,d,top,part,"A",2);AddDatum(m,d,front,part,"B",1);AddDatum(m,d,front,part,"C",0);
   string[] symbols={"<IGTOL-FLAT>","<IGTOL-POSI>","<IGTOL-SPROF>"};
   for(int i=0;i<3;i++){
    m.ClearSelection2(true);IGtol g=(IGtol)m.InsertGtol();
    if(g==null)throw new Exception("GD&T insertion failed");
    g.SetFrameSymbols2(1,symbols[i],i==1,"",false,"","","","");
    g.SetFrameValues(1,i==0?"0.20":"0.40","",i==0?"":"A",i==0?"":"B",i==0?"":"C");
    ((IAnnotation)g.GetAnnotation()).SetPosition2(.23,.055-i*.012,0);
   }
  }
  m.ViewZoomtofit2();Save(m,id,"SLDDRW");Save(m,id,"pdf");Save(m,id+"-drawing","png");Sw.CloseDoc(m.GetTitle());Sw.CloseDoc(part.GetTitle());
 }
 static int DimensionEdges(IModelDoc2 m,IDrawingDoc d,IView view,IModelDoc2 part){
  object[] bodies=(object[])((IPartDoc)part).GetBodies2(0,false);object[] edges=(object[])((IBody2)bodies[0]).GetEdges();
  IMathUtility math=(IMathUtility)Sw.GetMathUtility();bool horizontal=false,vertical=false;int count=0;
  // Longest orthogonal edges first, so overall envelope edges win where visible.
  Array.Sort(edges,delegate(object a,object b){return EdgeLength((IEdge)b).CompareTo(EdgeLength((IEdge)a));});
  foreach(IEdge edge in edges){
   if(!((ICurve)edge.GetCurve()).IsLine())continue;
   IVertex a=(IVertex)edge.GetStartVertex(),b=(IVertex)edge.GetEndVertex();if(a==null||b==null)continue;
   IMathPoint pa=(IMathPoint)math.CreatePoint(a.GetPoint()),pb=(IMathPoint)math.CreatePoint(b.GetPoint());
   double[] x=(double[])((IMathPoint)pa.MultiplyTransform(view.ModelToViewTransform)).ArrayData;
   double[] y=(double[])((IMathPoint)pb.MultiplyTransform(view.ModelToViewTransform)).ArrayData;
   double dx=Math.Abs(x[0]-y[0]),dy=Math.Abs(x[1]-y[1]);bool isH=dy<1e-7&&dx>.005,isV=dx<1e-7&&dy>.005;
   if((!isH||horizontal)&&(!isV||vertical))continue;
   m.ClearSelection2(true);d.ActivateView(view.GetName2());
   if(!view.SelectEntity(edge,false))continue;
   IDisplayDimension dim=(IDisplayDimension)m.AddDimension2((x[0]+y[0])/2+(isV?-.015:0),(x[1]+y[1])/2+(isH?.015:0),0);
   if(dim==null)continue;
   count++;if(isH)horizontal=true;if(isV)vertical=true;if(horizontal&&vertical)break;
  }
  if(count<2){
   var radii=new HashSet<double>();
   foreach(IEdge edge in edges){
    ICurve curve=(ICurve)edge.GetCurve();if(!curve.IsCircle())continue;
    double[] circle=(double[])curve.CircleParams;double radius=Math.Round(circle[6],7);if(radii.Contains(radius))continue;
    m.ClearSelection2(true);d.ActivateView(view.GetName2());if(!view.SelectEntity(edge,false))continue;
    double[] pos=(double[])view.Position;
    IDisplayDimension dia=(IDisplayDimension)m.AddDimension2(pos[0]+.025+count*.015,pos[1]+.02,0);
    if(dia!=null){radii.Add(radius);count++;}if(count>=2)break;
   }
  }
  d.ActivateView("");return count;
 }
 static void AddDatum(IModelDoc2 m,IDrawingDoc d,IView view,IModelDoc2 part,string label,int axis){
  IBody2 body=(IBody2)((object[])((IPartDoc)part).GetBodies2(0,false))[0];
  double[] bounds=(double[])body.GetBodyBox();object[] edges=(object[])body.GetEdges();
  Array.Sort(edges,delegate(object a,object b){return EdgeLength((IEdge)b).CompareTo(EdgeLength((IEdge)a));});
  foreach(IEdge edge in edges){
   if(!((ICurve)edge.GetCurve()).IsLine())continue;
   IVertex a=(IVertex)edge.GetStartVertex(),b=(IVertex)edge.GetEndVertex();if(a==null||b==null)continue;
   double[] x=(double[])a.GetPoint(),y=(double[])b.GetPoint();
   if(Math.Abs(x[axis]-bounds[axis])>1e-6||Math.Abs(y[axis]-bounds[axis])>1e-6)continue;
   if(axis==2&&Math.Abs(x[0]-y[0])<.01)continue;
   m.ClearSelection2(true);d.ActivateView(view.GetName2());if(!view.SelectEntity(edge,false))continue;
   IDatumTag tag=(IDatumTag)m.InsertDatumTag2();if(tag==null)continue;
   if(!tag.SetLabel(label))throw new Exception("Datum label failed");
   IMathUtility math=(IMathUtility)Sw.GetMathUtility();IMathPoint point=(IMathPoint)math.CreatePoint(x);
   double[] q=(double[])((IMathPoint)point.MultiplyTransform(view.ModelToViewTransform)).ArrayData;
   ((IAnnotation)tag.GetAnnotation()).SetPosition2(q[0]-.012,q[1]-.012,0);
   Log.WriteLine("DATUM "+label+" attached edge, axis="+axis);d.ActivateView("");return;
  }
  throw new Exception("Datum attachment failed "+label);
 }
 static double EdgeLength(IEdge e){IVertex a=(IVertex)e.GetStartVertex(),b=(IVertex)e.GetEndVertex();if(a==null||b==null)return 0;double[] x=(double[])a.GetPoint(),y=(double[])b.GetPoint();return Math.Sqrt(Math.Pow(x[0]-y[0],2)+Math.Pow(x[1]-y[1],2)+Math.Pow(x[2]-y[2],2));}
}
